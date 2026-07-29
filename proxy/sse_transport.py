"""Sanitized Server-Sent Events relay for the DMX Responses proxy.

The module owns SSE framing, lazy downstream commitment, bounded pre-content
reconnects, and stream outcome accounting.  JSON event mutation is delegated to
``responses_rewrite``; HTTP request selection remains outside this module.
"""

from __future__ import annotations

import http.client
import os
import socket
import time
from collections.abc import Callable
from typing import Any
from typing import Protocol
from typing import TypedDict
from http.server import BaseHTTPRequestHandler

import responses_rewrite
import runtime_state


UPSTREAM_READ_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_READ_TIMEOUT", "240"))
_PRELUDE_TYPES = (
    b'"type":"response.created"',
    b'"type": "response.created"',
    b'"type":"response.in_progress"',
    b'"type": "response.in_progress"',
)


class ResponseLike(Protocol):
    """Minimum upstream response surface consumed by the SSE reader."""

    fp: Any

    def read(self, amount: int = -1) -> bytes: ...


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
    import json

    return json.dumps(
        {
            "error": {
                "message": (
                    "DMX upstream stream ended before content after bounded reconnects; "
                    "retry the turn"
                ),
                "type": "upstream_unavailable",
                "code": "stream_pre_content_exhausted",
                "attempts": attempts,
            },
        },
        separators=(",", ":"),
    ).encode()


def _set_read_timeout(response: ResponseLike) -> None:
    try:
        response.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
    except Exception:
        try:
            response.fp.raw._fp.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
        except Exception:
            pass


def _terminal_type(event: bytes) -> str | None:
    for terminal in ("completed", "failed", "incomplete"):
        marker = f'"type":"response.{terminal}"'.encode()
        spaced_marker = f'"type": "response.{terminal}"'.encode()
        if marker in event or spaced_marker in event:
            return f"response.{terminal}"
    return None


def _read_one_stream(
    handler: BaseHTTPRequestHandler,
    response: ResponseLike,
    path: str,
    request_id: int,
    on_first_write: Callable[[], None],
) -> StreamResult:
    """Relay one upstream stream while withholding retry-safe prelude events."""
    buffer = b""
    stripped_events = 0
    stripped_keys = 0
    event_count = 0
    terminal_event = None
    upstream_incomplete = False
    upstream_timeout = False
    upstream_error: BaseException | None = None
    wrote_downstream = False
    prelude: list[bytes] = []
    prelude_flushed = False

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
        if not prelude_flushed:
            held = (
                any(marker in data for marker in _PRELUDE_TYPES)
                or b'"type":"response.failed"' in data
                or b'"type": "response.failed"' in data
            )
            if held:
                prelude.append(data)
                return
        flush_prelude()
        raw_write(data)

    def process_event(event: bytes) -> None:
        nonlocal stripped_events, stripped_keys, event_count, terminal_event
        sanitized, removed = responses_rewrite.sanitize_sse_event(event)
        if removed:
            stripped_events += 1
            stripped_keys += removed
        if b"event:" in sanitized or b"data:" in sanitized:
            event_count += 1
            terminal_event = _terminal_type(sanitized) or terminal_event
        emit(sanitized)

    _set_read_timeout(response)
    while True:
        try:
            chunk = response.read(8192)
        except http.client.IncompleteRead as error:
            chunk = error.partial
            upstream_incomplete = True
        except (socket.timeout, TimeoutError) as error:
            upstream_timeout = True
            upstream_error = error
            break
        except Exception as error:
            upstream_error = error
            break
        if not chunk:
            break
        buffer += chunk
        while True:
            lf_index = buffer.find(b"\n\n")
            crlf_index = buffer.find(b"\r\n\r\n")
            candidates = [index for index in (lf_index, crlf_index) if index != -1]
            if not candidates:
                break
            index = min(candidates)
            separator_length = 4 if index == crlf_index else 2
            event = buffer[: index + separator_length]
            buffer = buffer[index + separator_length :]
            process_event(event)
    if buffer:
        process_event(buffer)
    if terminal_event in ("response.completed", "response.incomplete") and not prelude_flushed:
        flush_prelude()
    if stripped_keys:
        runtime_state.record_counter("encrypted_sse_keys_stripped", stripped_keys)
        runtime_state.log(
            f"req={request_id} event=sse_sanitized encrypted_events={stripped_events} "
            f"encrypted_keys={stripped_keys} path={runtime_state.safe_request_path(path)}"
        )
    detail = (
        terminal_event.split(".")[-1]
        if terminal_event
        else (
            "timeout" if upstream_timeout else ("incomplete_read" if upstream_incomplete else "eof")
        )
    )
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

    def on_first_write() -> None:
        nonlocal headers_sent
        if send_headers is not None and not headers_sent:
            send_headers()
            headers_sent = True

    max_attempts = 6 if reopen is not None else 1
    backoffs = (1.0, 2.0, 4.0, 6.0, 8.0)
    current = response
    result: StreamResult | None = None
    attempt = 0
    for attempt in range(max_attempts):
        result = _read_one_stream(handler, current, path, request_id, on_first_write)
        committed = result["wrote_downstream"]
        terminal = result["terminal"]
        clean_end = terminal in ("response.completed", "response.incomplete")
        retryable = not committed and (terminal is None or terminal == "response.failed")
        if committed or clean_end or not retryable:
            break
        if attempt < max_attempts - 1 and reopen is not None:
            runtime_state.record_counter("streams_pre_content_reconnect_attempts")
            why = terminal or result["detail"]
            runtime_state.log(
                f"req={request_id} event=sse_pre_content_reconnect reason={why} "
                f"events={result['events']} attempt={attempt + 1}/{max_attempts - 1} "
                f"path={runtime_state.safe_request_path(path)}"
            )
            time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
            try:
                current = reopen()
            except Exception as error:
                runtime_state.log(
                    f"req={request_id} event=sse_reconnect_failed "
                    f"exception={runtime_state.safe_exception_label(error)} "
                    f"path={runtime_state.safe_request_path(path)}"
                )
                break
            continue
        break
    pre_content_exhausted = not headers_sent
    if headers_sent:
        handler.wfile.write(b"0\r\n\r\n")
    if result and result["terminal"] == "response.completed":
        runtime_state.record_counter("streams_completed")
        runtime_state.record_counter("responses_completed")
    elif result and result["terminal"] == "response.incomplete":
        runtime_state.record_counter("streams_incomplete")
        runtime_state.record_failure("stream_response_incomplete")
    else:
        runtime_state.record_counter("streams_failed")
        detail = result["detail"] if result else "eof"
        if pre_content_exhausted:
            runtime_state.record_counter("streams_pre_content_exhausted")
            runtime_state.record_failure("stream_pre_content_exhausted")
        else:
            runtime_state.record_failure(f"stream_{detail}")
    safe_path = runtime_state.safe_request_path(path)
    if result and result["terminal"]:
        runtime_state.log(
            f"req={request_id} event=sse_terminal terminal={result['terminal']} "
            f"events={result['events']} path={safe_path}"
        )
    else:
        detail = result["detail"] if result else "eof"
        error = result["error"] if result else None
        runtime_state.log(
            f"req={request_id} event=sse_end_without_terminal detail={detail} "
            f"exception={runtime_state.safe_exception_label(error) if error else 'none'} "
            f"events={result['events'] if result else 0} path={safe_path}"
        )
    return {
        "pre_content_exhausted": pre_content_exhausted,
        "attempts": attempt + 1,
        "result": result,
    }
