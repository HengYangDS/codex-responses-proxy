"""HTTP upstream orchestration for the DMX Responses proxy.

This module owns request admission, direct upstream I/O, classified recovery
selection, and HTTP response relay. Pure compatibility projections and SSE
framing remain in their dedicated owner modules.
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

from codex_dmx_proxy.compatibility import empty_response
from codex_dmx_proxy.compatibility import input_variant
from codex_dmx_proxy.compatibility import response_failed
from codex_dmx_proxy.listener import rewrite
from codex_dmx_proxy.listener import sse
from codex_dmx_proxy.listener import state

UPSTREAM = os.environ.get("DMX_UPSTREAM", "https://www.dmxapi.cn").rstrip("/")
UPSTREAM_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_TIMEOUT", "900"))
INPUT_VARIANT_DIALOGUE_SLOTS = 1
_MAX_ATTEMPTS = 4
_BACKOFFS = (0.4, 1.0, 2.0)

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "accept-encoding",
}
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen_direct(request: urllib.request.Request, timeout: float):
    """Open one upstream request without system or environment HTTP proxies."""
    return _DIRECT_OPENER.open(request, timeout=timeout)


def _send_payload(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: bytes,
    *,
    content_type: str = "application/json",
    retry_after: str | None = None,
) -> None:
    """Send one length-delimited local response."""
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    if retry_after:
        handler.send_header("Retry-After", retry_after)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _json_error(message: str, error_type: str, code: str) -> bytes:
    return json.dumps(
        {"error": {"message": message, "type": error_type, "code": code}},
        separators=(",", ":"),
    ).encode()


def _send_empty_response_exhausted(handler: BaseHTTPRequestHandler, attempts: int) -> None:
    _send_payload(handler, 503, empty_response.exhausted_payload(attempts), retry_after="3")


def _request(url: str, body: bytes, method: str, headers: dict[str, str]) -> urllib.request.Request:
    request = urllib.request.Request(url, data=body or None, method=method)
    for name, value in headers.items():
        request.add_header(name, value)
    return request


def _relay_error(handler: BaseHTTPRequestHandler, status: int, headers, payload: bytes) -> None:
    handler.send_response(status)
    for name, value in headers.items():
        if name.lower() not in _HOP_BY_HOP:
            handler.send_header(name, value)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _input_variant_recovery(raw: bytes) -> tuple[bytes | None, dict[str, object] | None]:
    recovery, metrics = input_variant.build_recovery(raw, response_failed.COMPACTION_BUDGET)
    if metrics is None:
        return recovery, None
    return recovery, {
        "original_bytes": metrics.original_bytes,
        "recovery_bytes": metrics.recovery_bytes,
        "retained_messages": metrics.retained_messages,
        "dropped_input_items": metrics.dropped_input_items,
        "prompt_cache_key_removed": metrics.prompt_cache_key_removed,
    }


@dataclass(slots=True)
class _Exchange:
    handler: BaseHTTPRequestHandler
    method: str
    request_id: int
    body: bytes
    url: str
    headers: dict[str, str]
    is_responses: bool
    attempt_body: bytes
    response_failed_stages: int = 0
    used_response_failed_compaction: bool = False
    compact_metrics: dict[str, Any] | None = None
    used_response_failed_dialogue: bool = False
    dialogue_metrics: dict[str, Any] | None = None
    used_input_variant_dialogue: bool = False
    input_variant_metrics: dict[str, object] | None = None
    response: Any = None

    def upstream(self, body: bytes | None = None):
        return urlopen_direct(
            _request(
                self.url, self.attempt_body if body is None else body, self.method, self.headers
            ),
            timeout=UPSTREAM_TIMEOUT,
        )

    def log(self, event: str, detail: str = "") -> None:
        path = state.safe_request_path(self.handler.path)
        state.log(f"req={self.request_id} event={event} {detail}path={path}")

    def accepted_recovery(self) -> None:
        if (
            not self.used_input_variant_dialogue
            and self.used_response_failed_dialogue
            and self.dialogue_metrics
        ):
            state.record_counter("response_failed_dialogue_recovery_accepted")
            m = self.dialogue_metrics
            self.log(
                "response_failed_dialogue_recovery_accepted",
                f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                f"retained_messages={m['retained_messages']} "
                f"dropped_input_items={m['dropped_input_items']} "
                f"pair_safe_stages={self.response_failed_stages} ",
            )
        elif self.used_response_failed_compaction and self.compact_metrics:
            state.record_counter("response_failed_compaction_accepted")
            m = self.compact_metrics
            self.log(
                "response_failed_compact_recovery_accepted",
                f"bytes={m['original_bytes']}->{m['compact_bytes']} "
                f"removed_inputs={m['removed_inputs']} retained_inputs={m['retained_inputs']} ",
            )

    def input_variant_accepted(self) -> None:
        if not (self.used_input_variant_dialogue and self.input_variant_metrics):
            return
        state.record_counter("input_variant_dialogue_recovery_accepted")
        m = self.input_variant_metrics
        self.log(
            "input_variant_dialogue_recovery_accepted",
            f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
            f"retained_messages={m['retained_messages']} "
            f"dropped_input_items={m['dropped_input_items']} ",
        )

    def input_variant_exhausted(self, detail: str) -> None:
        state.record_counter("input_variant_dialogue_recovery_exhausted")
        state.record_failure("input_variant_dialogue_recovery_exhausted")
        self.log("input_variant_dialogue_recovery_exhausted", detail)


def _classification(status_code: int, payload: bytes, disposition: str, exact: bool) -> str:
    lower = payload.lower()
    blocked = all(map(lower.__contains__, (b'"code":"invalid_prompt"', b"request blocked")))
    special = {
        (True, 400, "", False): "input_variant_validation_error",
        (False, 400, "full", False): "response_failed",
        (False, 400, "full", True): "blocked_invalid_prompt",
        (False, 477, "full", False): "empty_response",
    }.get((exact, status_code, disposition, blocked))
    return special or "_".join(filter(None, (f"http_{status_code}", disposition)))


def _recover_input_variant(exchange: _Exchange) -> bool:
    diagnostic = input_variant.diagnostic_dict(input_variant.diagnose(exchange.attempt_body))
    exchange.log(
        "input_variant_validation_error",
        f"{input_variant.format_diagnostic(diagnostic)} ",
    )
    recovery, metrics = _input_variant_recovery(exchange.body)
    if recovery is None or metrics is None:
        return False
    state.record_counter("input_variant_dialogue_recovery_attempts")
    exchange.used_input_variant_dialogue = True
    exchange.input_variant_metrics = metrics
    previous_bytes = len(exchange.attempt_body)
    exchange.attempt_body = recovery
    exchange.log(
        "input_variant_dialogue_recovery",
        f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
        f"retained_messages={metrics['retained_messages']} "
        f"dropped_input_items={metrics['dropped_input_items']} "
        f"cache_key_removed={metrics['prompt_cache_key_removed']} ",
    )
    return True


def _recover_response_failed(exchange: _Exchange, status_code: int, disposition: str) -> bool:
    if not (exchange.is_responses and status_code == 400 and disposition == "full"):
        return False
    if exchange.response_failed_stages < response_failed.MAX_STAGES:
        compact, metrics = response_failed.compact_request(exchange.attempt_body)
        if compact is not None and metrics is not None:
            state.record_counter("response_failed_compaction_attempts")
            exchange.response_failed_stages += 1
            metrics["stage"] = exchange.response_failed_stages
            exchange.compact_metrics = metrics
            exchange.used_response_failed_compaction = True
            previous_bytes = len(exchange.attempt_body)
            exchange.attempt_body = compact
            exchange.log(
                "response_failed_compact_recovery",
                f"stage={exchange.response_failed_stages}/{response_failed.MAX_STAGES} "
                f"bytes={previous_bytes}->{metrics['compact_bytes']} budget={metrics['budget_bytes']} "
                f"removed_inputs={metrics['removed_inputs']} retained_inputs={metrics['retained_inputs']} "
                f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                f"budget_met={metrics.get('budget_met', True)} ",
            )
            return True
    if exchange.used_response_failed_dialogue:
        return False
    recovery, metrics = response_failed.recover_dialogue(exchange.body)
    if recovery is None or metrics is None:
        return False
    state.record_counter("response_failed_dialogue_recovery_attempts")
    exchange.used_response_failed_dialogue = True
    exchange.dialogue_metrics = metrics
    previous_bytes = len(exchange.attempt_body)
    exchange.attempt_body = recovery
    exchange.log(
        "response_failed_dialogue_recovery",
        f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
        f"retained_messages={metrics['retained_messages']} "
        f"dropped_input_items={metrics['dropped_input_items']} "
        f"cache_key_removed={metrics['prompt_cache_key_removed']} ",
    )
    return True


def _exhaust_response_failed(exchange: _Exchange) -> None:
    state.record_counter("response_failed_recovery_exhausted")
    state.record_failure("response_failed_recovery_exhausted")
    attempts = exchange.response_failed_stages + int(exchange.used_response_failed_dialogue) + 1
    _send_payload(
        exchange.handler, 503, response_failed.exhausted_payload(attempts), retry_after="3"
    )
    exchange.log(
        "response_failed_recovery_exhausted",
        f"attempts={attempts} pair_safe_stages={exchange.response_failed_stages} "
        f"dialogue_recovery={exchange.used_response_failed_dialogue} upstream_status=400 ",
    )


def _reject_empty_response(
    exchange: _Exchange, fingerprint: str, attempts: int, event: str, detail: str
) -> None:
    state.record_counter("empty_response_recovery_exhausted")
    state.record_failure("empty_response_recovery_exhausted")
    state.remember_empty_response_failure(
        fingerprint,
        capacity=empty_response.COOLDOWN_CAPACITY,
        cooldown_seconds=empty_response.COOLDOWN_SECONDS,
    )
    _send_empty_response_exhausted(exchange.handler, attempts)
    exchange.log(event, detail)


def _recover_empty_response(exchange: _Exchange) -> bool:
    fingerprint = empty_response.policy_fingerprint(exchange.body)
    fallback, detail = empty_response.build_fallback(exchange.body)
    if fallback is None:
        rejection_reason = detail.get("reason", "unknown")
        fallback, dialogue_metrics = empty_response.recover_dialogue(
            exchange.body, rejection_reason=rejection_reason
        )
        if fallback is None:
            state.record_counter("empty_response_fallback_rejected")
            state.record_failure("empty_response_fallback_rejected")
            state.remember_empty_response_failure(
                fingerprint,
                capacity=empty_response.COOLDOWN_CAPACITY,
                cooldown_seconds=empty_response.COOLDOWN_SECONDS,
            )
            _send_empty_response_exhausted(exchange.handler, 1)
            exchange.log(
                "empty_response_fallback_rejected",
                f"reason={detail.get('reason', 'unknown')} attempts=1 ",
            )
            return True
        detail = {"projected": True, "dialogue_recovery": True}
        exchange.log(
            "empty_response_dialogue_recovery",
            f"bytes={dialogue_metrics['original_bytes']}->{dialogue_metrics['recovery_bytes']} "
            f"retained_messages={dialogue_metrics['retained_messages']} "
            f"dropped_input_items={dialogue_metrics['dropped_input_items']} "
            f"reason={rejection_reason} ",
        )
    state.record_counter("empty_response_fallback_attempts")
    previous_bytes = len(exchange.attempt_body)
    exchange.attempt_body = fallback
    exchange.log(
        "empty_response_fallback",
        f"projected={detail.get('projected', False)} bytes={previous_bytes}->{len(fallback)} "
        f"policy={empty_response.POLICY_VERSION} ",
    )
    try:
        exchange_response = exchange.upstream()
    except urllib.error.HTTPError as error:
        try:
            error.read()
            status = error.code
        finally:
            error.close()
        _reject_empty_response(
            exchange,
            fingerprint,
            2,
            "empty_response_fallback_failed",
            f"upstream_status={status} attempts=2 ",
        )
        return True
    except Exception as error:
        _reject_empty_response(
            exchange,
            fingerprint,
            2,
            "empty_response_fallback_failed",
            f"exception={state.safe_exception_label(error)} attempts=2 ",
        )
        return True
    state.record_counter("empty_response_fallback_accepted")
    exchange.log("empty_response_fallback_accepted")
    exchange.response = exchange_response
    return False


def _http_error(exchange: _Exchange, error: urllib.error.HTTPError, attempt: int) -> str:
    try:
        payload, status_code, headers = error.read(), error.code, error.headers
    finally:
        error.close()
    disposition = response_failed.retry_disposition(status_code, payload)
    exact = input_variant.is_exact_validation_error(status_code, payload)
    classification = _classification(status_code, payload, disposition, exact)
    state.record_upstream_classification(classification)
    if exchange.used_input_variant_dialogue:
        exchange.input_variant_exhausted(f"upstream_status={status_code} ")
        _relay_error(exchange.handler, status_code, headers, payload)
        return "terminal"
    if exact and _recover_input_variant(exchange):
        return "retry"
    if _recover_response_failed(exchange, status_code, disposition):
        return "retry"
    if exchange.is_responses and status_code == 400 and disposition == "full":
        _exhaust_response_failed(exchange)
        return "terminal"
    retry_ceiling = 1 if disposition == "once" else _MAX_ATTEMPTS - 1
    transient_retries_used = attempt - exchange.response_failed_stages
    if disposition and transient_retries_used < retry_ceiling and status_code not in (400, 477):
        delay = 3.0 if disposition == "once" else _BACKOFFS[min(attempt, len(_BACKOFFS) - 1)]
        exchange.log(
            "upstream_retry",
            f"status={status_code} disposition={disposition} attempt={attempt + 1}/{retry_ceiling} "
            f"delay_seconds={delay} ",
        )
        time.sleep(delay)
        return "retry"
    if status_code == 477 and disposition == "full":
        return "terminal" if _recover_empty_response(exchange) else "accepted"
    _relay_error(exchange.handler, status_code, headers, payload)
    state.record_failure(classification)
    exchange.log(
        "upstream_http_terminal",
        f"status={status_code} response_bytes={len(payload)} attempts={attempt + 1} ",
    )
    return "terminal"


def _transport_error(exchange: _Exchange, error: Exception, attempt: int) -> str:
    if exchange.used_input_variant_dialogue:
        exchange.input_variant_exhausted(f"exception={state.safe_exception_label(error)} ")
        _send_payload(
            exchange.handler,
            502,
            _json_error(
                "DMX input-variant recovery transport failed; retry the turn",
                "upstream_unavailable",
                "input_variant_recovery_transport_error",
            ),
        )
        return "terminal"
    if attempt < _MAX_ATTEMPTS - 1:
        exchange.log(
            "upstream_transport_retry",
            f"attempt={attempt + 1} exception={state.safe_exception_label(error)} ",
        )
        time.sleep(_BACKOFFS[min(attempt, len(_BACKOFFS) - 1)])
        return "retry"
    state.record_failure("upstream_transport_error")
    _send_payload(
        exchange.handler,
        502,
        _json_error(
            "DMX upstream transport failed after bounded retries; retry the turn",
            "upstream_unavailable",
            "upstream_transport_error",
        ),
    )
    exchange.log(
        "upstream_transport_exhausted",
        f"exception={state.safe_exception_label(error)} ",
    )
    return "terminal"


def _open(exchange: _Exchange):
    stages = response_failed.MAX_STAGES if exchange.is_responses else 0
    dialogue_slots = response_failed.DIALOGUE_SLOTS if exchange.is_responses else 0
    input_slots = INPUT_VARIANT_DIALOGUE_SLOTS if exchange.is_responses else 0
    for attempt in range(
        (_MAX_ATTEMPTS if exchange.is_responses else 1) + stages + dialogue_slots + input_slots
    ):
        try:
            response = exchange.upstream()
        except urllib.error.HTTPError as error:
            outcome = _http_error(exchange, error, attempt)
            if outcome == "retry":
                continue
            return exchange.response if outcome == "accepted" else None
        except Exception as error:
            if _transport_error(exchange, error, attempt) == "retry":
                continue
            return None
        exchange.accepted_recovery()
        return response
    state.record_failure("upstream_transport_error")
    _send_payload(
        exchange.handler,
        502,
        _json_error(
            "DMX upstream transport failed after bounded retries; retry the turn",
            "upstream_unavailable",
            "upstream_transport_error",
        ),
    )
    return None


def _admit(exchange: _Exchange) -> bool:
    if not exchange.is_responses:
        return True
    admission, active_now = state.admit_response()
    if admission == "draining":
        state.record_counter("responses_rejected_while_draining")
        state.record_failure("draining")
        _send_payload(
            exchange.handler,
            503,
            _json_error(
                "DMX proxy is draining active Responses; retry the turn shortly",
                "server_busy",
                "proxy_draining",
            ),
            retry_after="1",
        )
        exchange.log("responses_rejected_while_draining")
        return False
    if admission == "timeout":
        state.record_counter("responses_local_queue_timeouts")
        state.record_failure("local_queue_timeout")
        payload = json.dumps(
            {
                "error": {
                    "message": (
                        "dmx local proxy overloaded: timed out waiting for "
                        f"responses concurrency slot ({state.RESPONSES_MAX_CONCURRENCY})"
                    )
                }
            }
        ).encode()
        _send_payload(exchange.handler, 503, payload)
        exchange.log("local_queue_timeout")
        return False
    exchange.log(
        "responses_slot_acquired",
        f"active={active_now}/{state.RESPONSES_MAX_CONCURRENCY} ",
    )
    return True


def _send_stream_headers(handler: BaseHTTPRequestHandler, response) -> None:
    handler.send_response(response.status)
    for name, value in response.headers.items():
        if name.lower() not in _HOP_BY_HOP and name.lower() != "content-length":
            handler.send_header(name, value)
    handler.send_header("Transfer-Encoding", "chunked")
    handler.end_headers()


def _relay_sse(exchange: _Exchange, response) -> None:
    def reopen():
        return exchange.upstream()

    try:
        result = sse.relay(
            exchange.handler,
            response,
            exchange.handler.path,
            exchange.request_id,
            reopen=None if exchange.used_input_variant_dialogue else reopen,
            send_headers=lambda: _send_stream_headers(exchange.handler, response),
        )
        if result["pre_content_exhausted"]:
            if exchange.used_input_variant_dialogue:
                exchange.input_variant_exhausted("")
            _send_payload(
                exchange.handler, 503, sse.exhausted_payload(result["attempts"]), retry_after="3"
            )
            exchange.log("sse_pre_content_exhausted", f"attempts={result['attempts']} ")
        else:
            exchange.input_variant_accepted()
    except (BrokenPipeError, ConnectionResetError):
        exchange.log("downstream_client_closed")
    except Exception as error:
        exchange.log("stream_handler_exception", f"exception={state.safe_exception_label(error)} ")


def _read_chunk(response) -> tuple[bytes, bool]:
    try:
        return response.read(8192), False
    except http.client.IncompleteRead as error:
        return error.partial, True


def _relay_body(exchange: _Exchange, response) -> None:
    _send_stream_headers(exchange.handler, response)
    try:
        while True:
            chunk, terminal = _read_chunk(response)
            if chunk:
                exchange.handler.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
            if not chunk or terminal:
                break
        exchange.handler.wfile.write(b"0\r\n\r\n")
        if exchange.is_responses:
            state.record_counter("responses_completed")
        exchange.input_variant_accepted()
    except (BrokenPipeError, ConnectionResetError):
        exchange.log("downstream_client_closed")
    except Exception as error:
        exchange.log("stream_handler_exception", f"exception={state.safe_exception_label(error)} ")


def relay(handler: BaseHTTPRequestHandler, method: str) -> None:
    """Relay one downstream request through bounded compatibility policies."""
    request_id = state.next_request_id()
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length) if length else b""
    is_responses = method == "POST" and "/responses" in handler.path
    note = ""
    if body and is_responses:
        body, note = rewrite.sanitize_responses_body(body)
        state.record_sanitization(note)
        if len(body) >= 400_000:
            path = state.safe_request_path(handler.path)
            state.log(f"req={request_id} event=large_request bytes={len(body)} path={path}")
    headers = {
        name: value for name, value in handler.headers.items() if name.lower() not in _HOP_BY_HOP
    }
    headers["Accept-Encoding"] = "identity"
    if note:
        path = state.safe_request_path(handler.path)
        state.log(f"req={request_id} event=request_sanitized method={method} {note} path={path}")
    if is_responses:
        state.record_counter("responses_received")
    exchange = _Exchange(
        handler, method, request_id, body, UPSTREAM + handler.path, headers, is_responses, body
    )
    if not _admit(exchange):
        return
    acquired = is_responses
    try:
        if is_responses:
            fingerprint = empty_response.policy_fingerprint(body)
            remaining = state.empty_response_cooldown_remaining(
                fingerprint, cooldown_seconds=empty_response.COOLDOWN_SECONDS
            )
            if remaining > 0:
                state.record_counter("empty_response_cooldown_hits")
                state.record_failure("empty_response_cooldown_hit")
                _send_empty_response_exhausted(handler, 0)
                exchange.log("empty_response_cooldown_hit", f"remaining_seconds={remaining:.1f} ")
                return
        response = _open(exchange)
        if response is None:
            return
        content_type = response.headers.get("Content-Type", "")
        if is_responses and "text/event-stream" in content_type.lower():
            _relay_sse(exchange, response)
        else:
            _relay_body(exchange, response)
    finally:
        if acquired:
            active_now = state.release_response_slot()
            exchange.log(
                "responses_slot_released",
                f"active={active_now}/{state.RESPONSES_MAX_CONCURRENCY} ",
            )
