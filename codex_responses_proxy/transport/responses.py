"""Responses request admission and transport orchestration."""

from __future__ import annotations

import urllib.error
from http.server import BaseHTTPRequestHandler

from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.replay import request as replay_request
from codex_responses_proxy.runtime import admission, operational_log, telemetry
from codex_responses_proxy.transport import cooldown
from codex_responses_proxy.transport import exchange as upstream_exchange
from codex_responses_proxy.transport import relay as downstream

PROVIDERS = provider_registry.load()


def resolve_upstream(path: str) -> tuple[str, str, str] | None:
    """Resolve one configured provider namespace without provider branching."""

    resolved = PROVIDERS.resolve(path)
    return None if resolved is None else (resolved[0].name, resolved[1], resolved[2])


def _admit(exchange: upstream_exchange.Exchange) -> bool:
    if not exchange.is_responses:
        return True
    verdict, active_now = admission.admit_response(exchange.profile.name)
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
        payload = downstream.json_error(
            "local proxy overloaded: timed out waiting for a responses slot on "
            f"provider route {exchange.profile.name} "
            f"(route limit {admission.RESPONSES_MAX_PER_ROUTE}, "
            f"process limit {admission.RESPONSES_MAX_CONCURRENCY}); retry the turn",
            "server_busy",
            "local_queue_timeout",
        )
        downstream.send_payload(exchange.handler, 503, payload, retry_after="5")
        exchange.log("local_queue_timeout")
        return False
    exchange.log(
        "responses_slot_acquired",
        f"active={active_now}/{admission.RESPONSES_MAX_CONCURRENCY} ",
    )
    return True


def _cooldown_active(exchange: upstream_exchange.Exchange) -> bool:
    """Reject one Responses request while its provider policy is cooling down."""
    if not exchange.is_responses:
        return False
    policy = exchange.profile.wire_policy
    if policy is not None:
        fingerprint = policy.request_fingerprint(exchange.body)
        remaining = cooldown.remaining(fingerprint)
        if remaining > 0:
            telemetry.record_counter("wire_failure_cooldown_hits")
            telemetry.record_failure("wire_failure_cooldown_hit")
            downstream.send_wire_failure_exhausted(exchange.handler, policy, 0)
            exchange.log("wire_failure_cooldown_hit", f"remaining_seconds={remaining:.1f} ")
            return True
    remaining = cooldown.remaining(cooldown.provider_key(exchange.profile.name))
    if remaining <= 0:
        return False
    seconds = max(1, int(remaining + 0.999))
    telemetry.record_counter("provider_rate_limit_cooldown_hits")
    telemetry.record_failure("provider_rate_limit_cooldown")
    downstream.send_payload(
        exchange.handler,
        429,
        downstream.json_error(
            "provider rate limit cooldown is active; retry the turn shortly",
            "rate_limit_error",
            "provider_rate_limit_cooldown",
        ),
        retry_after=str(seconds),
    )
    exchange.log("provider_rate_limit_cooldown", f"remaining_seconds={seconds} ")
    return True


def _reject_route(
    handler: BaseHTTPRequestHandler, request_id: int, method: str | None = None
) -> None:
    """Return one local closed-route rejection without upstream I/O."""
    telemetry.record_counter("provider_route_rejected")
    telemetry.record_failure("provider_route_rejected")
    # A rejection answers before the request body is read, so the connection
    # cannot stay persistent over bytes the listener will never consume.
    if method is None:
        downstream.send_payload(
            handler,
            404,
            downstream.json_error(
                "request path is not a configured provider route",
                "invalid_request_error",
                "provider_route_not_found",
            ),
            close=True,
        )
        operational_log.log(
            f"req={request_id} event=provider_route_rejected "
            f"path={operational_log.safe_request_path(handler.path)}"
        )
        return
    downstream.send_payload(
        handler,
        404,
        downstream.json_error(
            "request method is not supported for the configured provider route",
            "invalid_request_error",
            "provider_route_method_not_allowed",
        ),
        close=True,
    )
    operational_log.log(
        f"req={request_id} event=provider_route_method_rejected "
        f"method={method} path={operational_log.safe_request_path(handler.path)}"
    )


def _request_headers(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    """Return one upstream header projection shared by the closed routes."""
    headers = {
        name: value
        for name, value in handler.headers.items()
        if name.lower() not in downstream.HOP_BY_HOP
    }
    headers["Accept-Encoding"] = "identity"
    return headers


def _project_responses_request(
    handler: BaseHTTPRequestHandler,
    request_id: int,
    profile: provider_registry.Profile,
    method: str,
) -> bytes | None:
    """Read and validate one Responses body before compatibility transport."""
    length = int(handler.headers.get("Content-Length") or 0)
    projection = replay_request.sanitize_responses_body(
        handler.rfile.read(length) if length else b""
    )
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
        operational_log.log(
            f"req={request_id} event=provider_portable_projection_rejected "
            f"provider={profile.name} reason={reason} "
            f"path={operational_log.safe_request_path(handler.path)}"
        )
        return None
    body, note = projection.body, projection.diagnostic()
    if len(body) >= 400_000:
        operational_log.log(
            f"req={request_id} event=large_request provider={profile.name} "
            f"bytes={len(body)} path={operational_log.safe_request_path(handler.path)}"
        )
    if note:
        operational_log.log(
            f"req={request_id} event=request_sanitized provider={profile.name} "
            f"method={method} {note} path={operational_log.safe_request_path(handler.path)}"
        )
    return body


def _relay_catalog(
    handler: BaseHTTPRequestHandler,
    request_id: int,
    profile: provider_registry.Profile,
    upstream_url: str,
    headers: dict[str, str],
) -> None:
    """Relay one model catalog read exactly once without Responses policy."""
    try:
        response = upstream_exchange.open_readonly(upstream_url, "GET", headers)
    except urllib.error.HTTPError as error:
        try:
            payload, status, upstream_headers = error.read(), error.code, error.headers
        finally:
            error.close()
        downstream.relay_error(handler, status, upstream_headers, payload)
        telemetry.record_failure(f"catalog_http_{status}")
        detail = f"status={status} response_bytes={len(payload)} "
        operational_log.log(
            f"req={request_id} event=catalog_http_terminal provider={profile.name} {detail}"
            f"path={operational_log.safe_request_path(handler.path)}"
        )
        return
    except Exception as error:
        telemetry.record_failure("catalog_transport_error")
        downstream.send_payload(
            handler,
            502,
            downstream.json_error(
                "Upstream model catalog transport failed; retry discovery shortly",
                "upstream_unavailable",
                "catalog_transport_error",
            ),
        )
        operational_log.log(
            f"req={request_id} event=catalog_transport_error provider={profile.name} "
            f"exception={operational_log.safe_exception_label(error)} "
            f"path={operational_log.safe_request_path(handler.path)}"
        )
        return
    downstream.relay_readonly_body(handler, response)


def _relay_responses(
    handler: BaseHTTPRequestHandler,
    method: str,
    request_id: int,
    profile: provider_registry.Profile,
    upstream_url: str,
    headers: dict[str, str],
) -> None:
    """Project and relay one Responses request through its bounded policy."""
    body = _project_responses_request(handler, request_id, profile, method)
    if body is None:
        return
    telemetry.record_counter("responses_received")
    exchange = upstream_exchange.Exchange(
        handler,
        method,
        request_id,
        body,
        upstream_url,
        headers,
        True,
        body,
        profile,
    )
    if _cooldown_active(exchange) or not _admit(exchange):
        return
    try:
        if _cooldown_active(exchange):
            return
        response = upstream_exchange.open_upstream(exchange)
        if response is None:
            return
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type.lower():
            downstream.relay_sse(exchange, response)
        else:
            downstream.relay_responses_json(exchange, response)
    finally:
        active_now = admission.release_response_slot(exchange.profile.name)
        exchange.log(
            "responses_slot_released",
            f"active={active_now}/{admission.RESPONSES_MAX_CONCURRENCY} ",
        )


def relay(handler: BaseHTTPRequestHandler, method: str) -> None:
    """Relay one request through one exact provider-scoped compatibility route."""
    request_id = admission.next_request_id()
    resolved = resolve_upstream(handler.path)
    if resolved is None:
        _reject_route(handler, request_id)
        return
    route, resource, upstream_url = resolved
    is_responses, is_catalog = (
        method == "POST" and resource == "responses",
        method == "GET" and resource == "models",
    )
    if not (is_responses or is_catalog):
        _reject_route(handler, request_id, method)
        return
    profile, headers = PROVIDERS.profiles[route], _request_headers(handler)
    if is_catalog:
        _relay_catalog(handler, request_id, profile, upstream_url, headers)
        return
    _relay_responses(handler, method, request_id, profile, upstream_url, headers)
