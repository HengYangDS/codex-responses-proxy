"""Sanitized Server-Sent Events relay for Codex Responses Proxy.

The module owns SSE framing, lazy downstream commitment, bounded pre-content
reconnects, and stream outcome accounting. JSON event mutation is delegated to
:mod:`codex_responses_proxy.protocol.response`; request admission and upstream
orchestration remain in :mod:`codex_responses_proxy.relay.responses`.
"""

from __future__ import annotations

import http.client
import json
import socket
import time
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler
from typing import Any, Protocol, TypedDict

from codex_responses_proxy.protocol import response as replay_response
from codex_responses_proxy.relay import operational_log, telemetry
from codex_responses_proxy.runtime import config as runtime_config


UPSTREAM_READ_TIMEOUT = runtime_config.load().upstream_read_timeout
UPSTREAM_TIMEOUT = runtime_config.load().upstream_timeout
_HELD_TYPES = (
    b'"type":"response.created"',
    b'"type": "response.created"',
    b'"type":"response.in_progress"',
    b'"type": "response.in_progress"',
    b'"type":"response.failed"',
    b'"type": "response.failed"',
)
_TERMINALS = ("completed", "failed", "incomplete")
_CLEAN_TERMINALS = {"response.completed", "response.incomplete"}


class ResponseLike(Protocol):
    """Minimum upstream response surface consumed by the SSE reader."""

    fp: Any

    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


class StreamResult(TypedDict):
    """Outcome of reading one upstream SSE response."""

    terminal: str | None
    events: int
    wrote_downstream: bool
    detail: str
    error: BaseException | None


class RelayResult(TypedDict):
    """Outcome of the bounded pre-content reconnect policy."""

    pre_content_exhausted: bool
    attempts: int
    result: StreamResult | None


def exhausted_payload(attempts: int) -> bytes:
    """Return a retryable local failure after pre-content SSE exhaustion."""
    return json.dumps(
        {
            "error": {
                "message": (
                    "Upstream stream ended before content after bounded reconnects; retry the turn"
                ),
                "type": "upstream_unavailable",
                "code": "stream_pre_content_exhausted",
                "attempts": attempts,
            },
        },
        separators=(",", ":"),
    ).encode()


def _set_read_timeout(response: ResponseLike, timeout: float) -> None:
    try:
        response.fp.raw._sock.settimeout(timeout)
    except Exception:
        try:
            response.fp.raw._fp.fp.raw._sock.settimeout(timeout)
        except Exception:
            pass


def _terminal_type(event: bytes) -> str | None:
    return next(
        (
            f"response.{terminal}"
            for terminal in _TERMINALS
            if f'"type":"response.{terminal}"'.encode() in event
            or f'"type": "response.{terminal}"'.encode() in event
        ),
        None,
    )


def _release_upstream(response: ResponseLike) -> None:
    """Release one upstream connection the relay will never read from again.

    A stream abandoned at its deadline, or replaced by a pre-content reconnect,
    would otherwise hold its socket until garbage collection.
    """
    with suppress(Exception):
        response.close()


def _arm_read_budget(response: ResponseLike, deadline: float, armed: float | None) -> float | None:
    """Clamp the per-read socket timeout to the remaining total-stream budget.

    Returns the armed budget, or ``None`` once the total deadline has passed.
    Re-arming as the deadline nears is what keeps a blocked read from
    outliving it by a whole idle-read interval.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    budget = min(UPSTREAM_READ_TIMEOUT, remaining)
    if armed is None or budget < armed:
        _set_read_timeout(response, budget)
    return budget


def _read_one_stream(
    handler: BaseHTTPRequestHandler,
    response: ResponseLike,
    path: str,
    request_id: int,
    on_first_write: Callable[[], None],
    deadline: float | None = None,
) -> StreamResult:
    """Relay one upstream stream while withholding retry-safe prelude events."""
    if deadline is None:
        deadline = time.monotonic() + UPSTREAM_TIMEOUT
    buffer = b""
    stripped_events = stripped_keys = event_count = 0
    terminal_event = None
    upstream_detail = "eof"
    upstream_error: BaseException | None = None
    wrote_downstream = prelude_flushed = False
    prelude: list[bytes] = []

    def raw_write(data: bytes) -> None:
        nonlocal wrote_downstream
        if not wrote_downstream:
            on_first_write()
            wrote_downstream = True
        handler.wfile.write(b"%X\r\n%s\r\n" % (len(data), data))

    def flush_prelude() -> None:
        nonlocal prelude_flushed
        if prelude_flushed:
            return
        for event in prelude:
            raw_write(event)
        prelude.clear()
        prelude_flushed = True

    def emit(data: bytes) -> None:
        if not prelude_flushed and any(marker in data for marker in _HELD_TYPES):
            prelude.append(data)
            return
        flush_prelude()
        raw_write(data)

    def process_event(event: bytes) -> None:
        nonlocal stripped_events, stripped_keys, event_count, terminal_event
        nonlocal upstream_detail, upstream_error
        try:
            sanitized, removed = replay_response.sanitize_sse_event(event)
        except ValueError as error:
            upstream_detail = "projection_failed"
            upstream_error = error
            return
        if removed:
            stripped_events += 1
            stripped_keys += removed
        event_count += 1
        terminal_event = _terminal_type(sanitized) or terminal_event
        emit(sanitized)

    armed: float | None = None
    while True:
        armed = _arm_read_budget(response, deadline, armed)
        if armed is None:
            upstream_detail = "deadline"
            break
        try:
            chunk = response.read(8192)
        except http.client.IncompleteRead as error:
            chunk = error.partial
            upstream_detail = "incomplete_read"
        except (socket.timeout, TimeoutError) as error:
            upstream_detail, upstream_error = "timeout", error
            if time.monotonic() >= deadline:
                upstream_detail = "deadline"
            break
        except Exception as error:
            upstream_error = error
            break
        if not chunk:
            break
        buffer += chunk
        while True:
            separators = tuple(
                (index, len(marker))
                for marker in (b"\n\n", b"\r\n\r\n")
                if (index := buffer.find(marker)) >= 0
            )
            if not separators:
                break
            index, separator_length = min(separators)
            event = buffer[: index + separator_length]
            buffer = buffer[index + separator_length :]
            process_event(event)
            if upstream_detail == "projection_failed":
                buffer = b""
                break
        if upstream_detail == "projection_failed":
            break
    if buffer:
        process_event(buffer)
    if terminal_event in _CLEAN_TERMINALS:
        flush_prelude()
    if stripped_keys:
        telemetry.record_counter("encrypted_sse_keys_stripped", stripped_keys)
        operational_log.log(
            f"req={request_id} event=sse_sanitized encrypted_events={stripped_events} "
            f"encrypted_keys={stripped_keys} path={operational_log.safe_request_path(path)}"
        )
    detail = terminal_event.rpartition(".")[2] if terminal_event else upstream_detail
    return {
        "terminal": terminal_event,
        "events": event_count,
        "wrote_downstream": wrote_downstream,
        "detail": detail,
        "error": upstream_error,
    }


def relay(
    handler: BaseHTTPRequestHandler,
    response: ResponseLike,
    path: str,
    request_id: int,
    reopen: Callable[[], ResponseLike] | None = None,
    send_headers: Callable[[], None] | None = None,
) -> RelayResult:
    """Relay sanitized SSE with retries only before downstream commitment."""
    headers_sent = False
    send_headers = send_headers or (lambda: None)

    def on_first_write() -> None:
        nonlocal headers_sent
        send_headers()
        headers_sent = True

    max_attempts = 6 if reopen is not None else 1
    backoffs = (1.0, 2.0, 4.0, 6.0, 8.0)
    deadline = time.monotonic() + UPSTREAM_TIMEOUT
    current = response
    result: StreamResult | None = None
    attempt = 0
    for attempt in range(max_attempts):
        result = _read_one_stream(handler, current, path, request_id, on_first_write, deadline)
        _release_upstream(current)
        terminal = result["terminal"]
        if (
            result["wrote_downstream"]
            or terminal in _CLEAN_TERMINALS
            or result["detail"] == "projection_failed"
        ):
            break
        if attempt == max_attempts - 1 or time.monotonic() >= deadline:
            break
        telemetry.record_counter("streams_pre_content_reconnect_attempts")
        why = terminal or result["detail"]
        operational_log.log(
            f"req={request_id} event=sse_pre_content_reconnect reason={why} "
            f"events={result['events']} attempt={attempt + 1}/{max_attempts - 1} "
            f"path={operational_log.safe_request_path(path)}"
        )
        time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
        assert reopen is not None
        try:
            current = reopen()
        except Exception as error:
            operational_log.log(
                f"req={request_id} event=sse_reconnect_failed "
                f"exception={operational_log.safe_exception_label(error)} "
                f"path={operational_log.safe_request_path(path)}"
            )
            break
    pre_content_exhausted = not headers_sent
    if headers_sent:
        handler.wfile.write(b"0\r\n\r\n")
    assert result is not None
    if result["terminal"] == "response.completed":
        telemetry.record_counter("streams_completed")
        telemetry.record_counter("responses_completed")
    elif result["terminal"] == "response.incomplete":
        telemetry.record_counter("streams_incomplete")
        telemetry.record_failure("stream_response_incomplete")
    else:
        telemetry.record_counter("streams_failed")
        detail = result["detail"]
        if detail == "projection_failed":
            telemetry.record_counter("stream_projection_failures")
            telemetry.record_failure("stream_projection_failed")
        elif pre_content_exhausted:
            telemetry.record_counter("streams_pre_content_exhausted")
            telemetry.record_failure("stream_pre_content_exhausted")
        else:
            telemetry.record_failure(f"stream_{detail}")
    safe_path = operational_log.safe_request_path(path)
    if result["terminal"]:
        operational_log.log(
            f"req={request_id} event=sse_terminal terminal={result['terminal']} "
            f"events={result['events']} path={safe_path}"
        )
    else:
        detail = result["detail"]
        error = result["error"]
        operational_log.log(
            f"req={request_id} event=sse_end_without_terminal detail={detail} "
            f"exception={operational_log.safe_exception_label(error) if error else 'none'} "
            f"events={result['events']} path={safe_path}"
        )
    return {
        "pre_content_exhausted": pre_content_exhausted,
        "attempts": attempt + 1,
        "result": result,
    }
