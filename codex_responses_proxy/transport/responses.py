"""Responses request admission and transport orchestration."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.replay import request as replay_request
from codex_responses_proxy.runtime import admission, logging, telemetry
from codex_responses_proxy.transport import cooldown
from codex_responses_proxy.transport import exchange as upstream_exchange
from codex_responses_proxy.transport import relay as downstream

PROVIDERS = provider_registry.load()


def resolve_upstream(path: str) -> tuple[str, str] | None:
    """Resolve one configured provider namespace without provider branching."""

    resolved = PROVIDERS.resolve(path)
    return None if resolved is None else (resolved[0].name, resolved[1])


def _admit(exchange: upstream_exchange.Exchange) -> bool:
    if not exchange.is_responses:
        return True
    verdict, active_now = admission.admit_response()
    if verdict == "draining":
        telemetry.record_counter("responses_rejected_while_draining")
        telemetry.record_failure("draining")
        downstream.send_payload(
            exchange.handler,
            503,
            downstream.json_error(
                "Proxy is draining active Responses; retry the turn shortly",
                "server_busy",
                "proxy_draining",
            ),
            retry_after="1",
        )
        exchange.log("responses_rejected_while_draining")
        return False
    if verdict == "timeout":
        telemetry.record_counter("responses_local_queue_timeouts")
        telemetry.record_failure("local_queue_timeout")
        payload = json.dumps(
            {
                "error": {
                    "message": (
                        "local proxy overloaded: timed out waiting for "
                        f"responses concurrency slot ({admission.RESPONSES_MAX_CONCURRENCY})"
                    )
                }
            }
        ).encode()
        downstream.send_payload(exchange.handler, 503, payload)
        exchange.log("local_queue_timeout")
        return False
    exchange.log(
        "responses_slot_acquired",
        f"active={active_now}/{admission.RESPONSES_MAX_CONCURRENCY} ",
    )
    return True


def relay(handler: BaseHTTPRequestHandler, method: str) -> None:
    """Relay one downstream request through bounded compatibility policies."""
    request_id = admission.next_request_id()
    resolved = resolve_upstream(handler.path)
    if resolved is None:
        telemetry.record_counter("provider_route_rejected")
        telemetry.record_failure("provider_route_rejected")
        downstream.send_payload(
            handler,
            404,
            downstream.json_error(
                "request path is not a configured provider route",
                "invalid_request_error",
                "provider_route_not_found",
            ),
        )
        logging.log(
            f"req={request_id} event=provider_route_rejected "
            f"path={logging.safe_request_path(handler.path)}"
        )
        return
    route, upstream_url = resolved
    profile = PROVIDERS.profiles[route]
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length) if length else b""
    is_responses = method == "POST"
    note = ""
    if is_responses:
        projection = replay_request.sanitize_responses_body(body)
        note = projection.diagnostic()
        telemetry.record_sanitization(projection.metrics)
        if projection.body is None:
            reason = projection.reason or "unknown"
            telemetry.record_counter("provider_portable_projection_rejected")
            telemetry.record_failure("provider_portable_projection_rejected")
            downstream.send_payload(
                handler,
                400,
                downstream.json_error(
                    "Responses replay contains an unproved provider-portable structure",
                    "invalid_request_error",
                    "provider_portable_projection_rejected",
                    reason=reason,
                ),
            )
            logging.log(
                f"req={request_id} event=provider_portable_projection_rejected "
                f"provider={profile.name} reason={reason} "
                f"path={logging.safe_request_path(handler.path)}"
            )
            return
        body = projection.body
        if len(body) >= 400_000:
            path = logging.safe_request_path(handler.path)
            logging.log(
                f"req={request_id} event=large_request provider={profile.name} "
                f"bytes={len(body)} path={path}"
            )
    headers = {
        name: value
        for name, value in handler.headers.items()
        if name.lower() not in downstream.HOP_BY_HOP
    }
    headers["Accept-Encoding"] = "identity"
    if note:
        path = logging.safe_request_path(handler.path)
        logging.log(
            f"req={request_id} event=request_sanitized provider={profile.name} "
            f"method={method} {note} path={path}"
        )
    if is_responses:
        telemetry.record_counter("responses_received")
    exchange = upstream_exchange.Exchange(
        handler,
        method,
        request_id,
        body,
        upstream_url,
        headers,
        is_responses,
        body,
        profile,
    )
    if not _admit(exchange):
        return
    acquired = is_responses
    try:
        policy = profile.wire_policy
        if is_responses and policy is not None:
            fingerprint = policy.request_fingerprint(body)
            remaining = cooldown.remaining(
                fingerprint, cooldown_seconds=policy.FAILURE_COOLDOWN_SECONDS
            )
            if remaining > 0:
                telemetry.record_counter("wire_failure_cooldown_hits")
                telemetry.record_failure("wire_failure_cooldown_hit")
                downstream.send_wire_failure_exhausted(handler, policy, 0)
                exchange.log("wire_failure_cooldown_hit", f"remaining_seconds={remaining:.1f} ")
                return
        response = upstream_exchange.open_upstream(exchange)
        if response is None:
            return
        content_type = response.headers.get("Content-Type", "")
        if is_responses and "text/event-stream" in content_type.lower():
            downstream.relay_sse(exchange, response)
        elif is_responses:
            downstream.relay_responses_json(exchange, response)
        else:
            downstream.relay_body(exchange, response)
    finally:
        if acquired:
            active_now = admission.release_response_slot()
            exchange.log(
                "responses_slot_released",
                f"active={active_now}/{admission.RESPONSES_MAX_CONCURRENCY} ",
            )
