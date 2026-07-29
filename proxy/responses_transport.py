"""HTTP upstream orchestration for the DMX Responses proxy.

This module owns request admission, direct upstream I/O, classified recovery
selection, and HTTP response relay.  Pure compatibility projections and SSE
framing remain in their dedicated owner modules.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

import empty_response
import input_compatibility
import response_failed
import responses_rewrite
import runtime_state
import sse_transport

UPSTREAM = os.environ.get("DMX_UPSTREAM", "https://www.dmxapi.cn").rstrip("/")
UPSTREAM_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_TIMEOUT", "900"))
INPUT_VARIANT_DIALOGUE_SLOTS = 1
RESPONSES_MAX_CONCURRENCY = runtime_state.RESPONSES_MAX_CONCURRENCY

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


def _send_empty_response_exhausted(handler: BaseHTTPRequestHandler, attempts: int) -> None:
    payload = empty_response.exhausted_payload(attempts)
    handler.send_response(503)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Retry-After", "3")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _input_variant_recovery(raw: bytes) -> tuple[bytes | None, dict[str, object] | None]:
    recovery, metrics = input_compatibility.build_recovery(raw, response_failed.COMPACTION_BUDGET)
    if metrics is None:
        return recovery, None
    return recovery, {
        "original_bytes": metrics.original_bytes,
        "recovery_bytes": metrics.recovery_bytes,
        "retained_messages": metrics.retained_messages,
        "dropped_input_items": metrics.dropped_input_items,
        "provider_bindings_removed": metrics.provider_bindings_removed,
        "reasoning_include_removed": metrics.reasoning_include_removed,
        "prompt_cache_key_removed": metrics.prompt_cache_key_removed,
    }


def relay(handler: BaseHTTPRequestHandler, method: str) -> None:
    """Relay one downstream request through bounded compatibility policies."""
    request_id = runtime_state.next_request_id()
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length) if length else b""

    note = ""
    if body and method == "POST" and "/responses" in handler.path:
        body, note = responses_rewrite.sanitize_responses_body(body)
        runtime_state.record_sanitization(note)
        # Payloads may contain conversation data and credentials. Keep runtime
        # evidence aggregate-only: this proxy never persists request bodies.
        if len(body) >= 400_000:
            runtime_state.log(
                f"req={request_id} event=large_request bytes={len(body)} "
                f"path={runtime_state.safe_request_path(handler.path)}"
            )

    url = UPSTREAM + handler.path
    out_headers = {k: v for k, v in handler.headers.items() if k.lower() not in _HOP_BY_HOP}
    out_headers["Accept-Encoding"] = "identity"

    if note:
        runtime_state.log(
            f"req={request_id} event=request_sanitized method={method} "
            f"path={runtime_state.safe_request_path(handler.path)} {note}"
        )

    # dmxapi intermittently returns 400 invalid_payload / 5xx / 429 for
    # provably-valid requests (~6% observed; identical replay succeeds).
    # Transparently retry the identical request a few times before giving up,
    # so this server-side flakiness never reaches Codex. An explicit 400
    # ``response_failed`` receives one *additional*, pair-safe compact
    # fallback: some large replay contexts are deterministically rejected.
    # Non-retryable 4xx are relayed immediately.
    is_responses = method == "POST" and "/responses" in handler.path
    if is_responses:
        runtime_state.record_counter("responses_received")
    max_attempts = 4 if is_responses else 1
    backoffs = [0.4, 1.0, 2.0]

    acquired = False
    if is_responses:
        admission, active_now = runtime_state.admit_response()
        if admission == "draining":
            runtime_state.record_counter("responses_rejected_while_draining")
            runtime_state.record_failure("draining")
            msg = json.dumps(
                {
                    "error": {
                        "message": "DMX proxy is draining active Responses; retry the turn shortly",
                        "type": "server_busy",
                        "code": "proxy_draining",
                    }
                },
                separators=(",", ":"),
            ).encode()
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Retry-After", "1")
            handler.send_header("Content-Length", str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
            runtime_state.log(
                f"req={request_id} event=responses_rejected_while_draining "
                f"path={runtime_state.safe_request_path(handler.path)}"
            )
            return
        if admission == "timeout":
            runtime_state.record_counter("responses_local_queue_timeouts")
            runtime_state.record_failure("local_queue_timeout")
            msg = json.dumps(
                {
                    "error": {
                        "message": (
                            "dmx local proxy overloaded: timed out waiting for "
                            f"responses concurrency slot ({RESPONSES_MAX_CONCURRENCY})"
                        )
                    }
                }
            ).encode()
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
            runtime_state.log(
                f"req={request_id} event=local_queue_timeout "
                f"path={runtime_state.safe_request_path(handler.path)}"
            )
            return
        acquired = True
        runtime_state.log(
            f"req={request_id} event=responses_slot_acquired "
            f"active={active_now}/{RESPONSES_MAX_CONCURRENCY} "
            f"path={runtime_state.safe_request_path(handler.path)}"
        )

    try:
        resp = None
        compact_response_failed_metrics = None
        used_response_failed_compaction = False
        response_failed_stages = 0
        max_response_failed_stages = response_failed.MAX_STAGES if is_responses else 0
        # Reserved independently of ``max_response_failed_stages`` so the
        # dialogue-only recovery continuation still gets its one bounded
        # attempt even when ``DMX_RESPONSE_FAILED_MAX_STAGES=0``. It never
        # widens the ordinary retry ceiling below, which is computed from
        # ``max_attempts`` alone. The classified-477 fallback itself is
        # dispatched immediately, as an independent nested request (see
        # below), and deliberately does *not* add to this range.
        dialogue_slots = response_failed.DIALOGUE_SLOTS if is_responses else 0
        input_variant_slots = INPUT_VARIANT_DIALOGUE_SLOTS if is_responses else 0
        attempt_body = body
        used_response_failed_dialogue_recovery = False
        dialogue_recovery_metrics = None
        used_input_variant_dialogue_recovery = False
        input_variant_dialogue_metrics = None
        # A classified 477 gets exactly one dedicated fallback slot per
        # request. Before spending any upstream attempt, honor a bounded
        # local cooldown recorded by a prior exhausted recovery for this
        # exact (policy-versioned) request, so a client that retries an
        # unrecoverable request in a tight loop cannot hammer upstream.
        if is_responses:
            cooldown_fingerprint = empty_response.policy_fingerprint(body)
            cooldown_remaining = runtime_state.empty_response_cooldown_remaining(
                cooldown_fingerprint, cooldown_seconds=empty_response.COOLDOWN_SECONDS
            )
            if cooldown_remaining > 0:
                runtime_state.record_counter("empty_response_cooldown_hits")
                runtime_state.record_failure("empty_response_cooldown_hit")
                _send_empty_response_exhausted(handler, 0)
                runtime_state.log(
                    f"req={request_id} event=empty_response_cooldown_hit "
                    f"remaining_seconds={cooldown_remaining:.1f} path={runtime_state.safe_request_path(handler.path)}"
                )
                return
        # Ordinary transient retries retain their previous bounded policy.
        # Explicit ``response_failed`` has its own staged, pair-safe
        # compaction path and must never loop the same bytes.
        for attempt in range(
            max_attempts + max_response_failed_stages + dialogue_slots + input_variant_slots
        ):
            req = urllib.request.Request(
                url, data=attempt_body if attempt_body else None, method=method
            )
            for k, v in out_headers.items():
                req.add_header(k, v)
            try:
                resp = urlopen_direct(req, timeout=UPSTREAM_TIMEOUT)
                # The dedicated classified-477 fallback is dispatched as its
                # own immediate nested request below and never reaches this
                # normal loop success path, so only the ordinary
                # ``response_failed`` recovery branches need crediting here.
                if (
                    not used_input_variant_dialogue_recovery
                    and used_response_failed_dialogue_recovery
                    and dialogue_recovery_metrics
                ):
                    runtime_state.record_counter("response_failed_dialogue_recovery_accepted")
                    m = dialogue_recovery_metrics
                    runtime_state.log(
                        f"req={request_id} event=response_failed_dialogue_recovery_accepted "
                        f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                        f"retained_messages={m['retained_messages']} "
                        f"dropped_input_items={m['dropped_input_items']} "
                        f"pair_safe_stages={response_failed_stages} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                elif used_response_failed_compaction and compact_response_failed_metrics:
                    runtime_state.record_counter("response_failed_compaction_accepted")
                    m = compact_response_failed_metrics
                    runtime_state.log(
                        f"req={request_id} event=response_failed_compact_recovery_accepted "
                        f"bytes={m['original_bytes']}->{m['compact_bytes']} "
                        f"removed_inputs={m['removed_inputs']} "
                        f"retained_inputs={m['retained_inputs']} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                break
            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read()
                    status_code = e.code
                    error_headers = e.headers
                finally:
                    e.close()
                disp = response_failed.retry_disposition(status_code, err_body)
                input_variant_validation = input_compatibility.is_exact_validation_error(
                    status_code, err_body
                )
                blocked_invalid_prompt = (
                    status_code == 400
                    and b'"code":"invalid_prompt"' in err_body.lower()
                    and b"request blocked" in err_body.lower()
                )
                classification = (
                    "input_variant_validation_error"
                    if input_variant_validation
                    else (
                        "blocked_invalid_prompt"
                        if blocked_invalid_prompt
                        else (
                            "response_failed"
                            if status_code == 400 and disp == "full"
                            else (
                                "empty_response"
                                if status_code == 477 and disp == "full"
                                else (
                                    f"http_{status_code}_{disp}" if disp else f"http_{status_code}"
                                )
                            )
                        )
                    )
                )
                runtime_state.record_upstream_classification(classification)
                if used_input_variant_dialogue_recovery:
                    runtime_state.record_counter("input_variant_dialogue_recovery_exhausted")
                    runtime_state.record_failure("input_variant_dialogue_recovery_exhausted")
                    handler.send_response(status_code)
                    for k, v in error_headers.items():
                        if k.lower() not in _HOP_BY_HOP and k.lower() != "content-length":
                            handler.send_header(k, v)
                    handler.send_header("Content-Length", str(len(err_body)))
                    handler.end_headers()
                    handler.wfile.write(err_body)
                    runtime_state.log(
                        f"req={request_id} event=input_variant_dialogue_recovery_exhausted "
                        f"upstream_status={status_code} path={runtime_state.safe_request_path(handler.path)}"
                    )
                    return
                if input_variant_validation:
                    diagnostic = input_compatibility.diagnostic_dict(
                        input_compatibility.diagnose(attempt_body)
                    )
                    runtime_state.log(
                        f"req={request_id} event=input_variant_validation_error "
                        f"{input_compatibility.format_diagnostic(diagnostic)} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                    if not used_input_variant_dialogue_recovery:
                        recovery, metrics = _input_variant_recovery(body)
                        if (
                            recovery is not None
                            and metrics is not None
                            and len(recovery) < len(attempt_body)
                        ):
                            runtime_state.record_counter("input_variant_dialogue_recovery_attempts")
                            used_input_variant_dialogue_recovery = True
                            input_variant_dialogue_metrics = metrics
                            previous_bytes = len(attempt_body)
                            attempt_body = recovery
                            runtime_state.log(
                                f"req={request_id} event=input_variant_dialogue_recovery "
                                f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
                                f"retained_messages={metrics['retained_messages']} "
                                f"dropped_input_items={metrics['dropped_input_items']} "
                                f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                                f"path={runtime_state.safe_request_path(handler.path)}"
                            )
                            continue
                # A deterministic replay failure cannot be fixed by retrying
                # the same bytes. After the upstream has *explicitly* named
                # ``response_failed``, make up to three strictly smaller,
                # pair-safe suffix attempts. Each retains the latest user
                # context and complete call/output pairs. This precedes
                # ordinary retries so users do not wait through known-identical
                # rejections.
                if (
                    is_responses
                    and status_code == 400
                    and disp == "full"
                    and response_failed_stages < max_response_failed_stages
                ):
                    compact, metrics = response_failed.compact_request(attempt_body)
                    if (
                        compact is not None
                        and metrics is not None
                        and len(compact) < len(attempt_body)
                    ):
                        runtime_state.record_counter("response_failed_compaction_attempts")
                        response_failed_stages += 1
                        metrics["stage"] = response_failed_stages
                        compact_response_failed_metrics = metrics
                        used_response_failed_compaction = True
                        previous_bytes = len(attempt_body)
                        attempt_body = compact
                        runtime_state.log(
                            f"req={request_id} event=response_failed_compact_recovery "
                            f"stage={response_failed_stages}/{max_response_failed_stages} "
                            f"bytes={previous_bytes}->{metrics['compact_bytes']} budget={metrics['budget_bytes']} "
                            f"removed_inputs={metrics['removed_inputs']} "
                            f"retained_inputs={metrics['retained_inputs']} "
                            f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                            f"budget_met={metrics.get('budget_met', True)} "
                            f"path={runtime_state.safe_request_path(handler.path)}"
                        )
                        continue
                # If pair-safe suffixes have exhausted their useful range, make
                # one final dialogue-only recovery attempt.  This is deliberately
                # after pair-safe compaction: tool call/output replay is retained
                # whenever it is accepted, and only an explicitly rejected replay
                # can reach this bounded last resort.
                if (
                    is_responses
                    and status_code == 400
                    and disp == "full"
                    and not used_response_failed_dialogue_recovery
                ):
                    # Recover from the original request rather than the latest
                    # pair-safe suffix: a suffix may already have discarded the
                    # newest developer instruction to preserve a later tool pair.
                    # The dialogue-only recovery can safely retain that current
                    # instruction because it omits the rejected tool replay.
                    recovery, metrics = response_failed.recover_dialogue(body)
                    if (
                        recovery is not None
                        and metrics is not None
                        and len(recovery) < len(attempt_body)
                    ):
                        runtime_state.record_counter("response_failed_dialogue_recovery_attempts")
                        used_response_failed_dialogue_recovery = True
                        dialogue_recovery_metrics = metrics
                        previous_bytes = len(attempt_body)
                        attempt_body = recovery
                        runtime_state.log(
                            f"req={request_id} event=response_failed_dialogue_recovery "
                            f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
                            f"retained_messages={metrics['retained_messages']} "
                            f"dropped_input_items={metrics['dropped_input_items']} "
                            f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                            f"path={runtime_state.safe_request_path(handler.path)}"
                        )
                        continue
                # ``invalid_payload`` is a classified upstream transient, not a
                # body rewrite signal. Retry the exact sanitized bytes once with a
                # bounded delay; 429 and 5xx retain the full retry budget.
                # ``response_failed`` has already consumed this response in
                # the staged compaction branch above. Never let it fall
                # through to the ordinary transient retry policy.
                if is_responses and status_code == 400 and disp == "full":
                    runtime_state.record_counter("response_failed_recovery_exhausted")
                    runtime_state.record_failure("response_failed_recovery_exhausted")
                    attempts = (
                        response_failed_stages + int(used_response_failed_dialogue_recovery) + 1
                    )
                    msg = response_failed.exhausted_payload(attempts)
                    handler.send_response(503)
                    handler.send_header("Content-Type", "application/json")
                    handler.send_header("Retry-After", "3")
                    handler.send_header("Content-Length", str(len(msg)))
                    handler.end_headers()
                    handler.wfile.write(msg)
                    runtime_state.log(
                        f"req={request_id} event=response_failed_recovery_exhausted "
                        f"attempts={attempts} pair_safe_stages={response_failed_stages} "
                        f"dialogue_recovery={used_response_failed_dialogue_recovery} "
                        f"upstream_status={status_code} path={runtime_state.safe_request_path(handler.path)}"
                    )
                    return
                retry_ceiling = 1 if disp == "once" else max_attempts - 1
                transient_retries_used = attempt - response_failed_stages
                if (
                    disp
                    and transient_retries_used < retry_ceiling
                    and not (status_code == 400 and disp == "full")
                    and not (status_code == 477 and disp == "full")
                ):
                    delay = 3.0 if disp == "once" else backoffs[min(attempt, len(backoffs) - 1)]
                    runtime_state.log(
                        f"req={request_id} event=upstream_retry status={status_code} "
                        f"disposition={disp} attempt={attempt + 1}/{retry_ceiling} "
                        f"delay_seconds={delay} path={runtime_state.safe_request_path(handler.path)}"
                    )
                    time.sleep(delay)
                    continue
                if status_code == 477 and disp == "full":
                    # DMX's empty-response extension gets exactly one bounded,
                    # semantics-preserving fallback attempt instead of the
                    # ordinary identical-bytes retry budget. A projection
                    # rejected only by exact stale search history may use a
                    # stricter current-dialogue fallback; every other unsafe
                    # projection rejects without spending a second upstream
                    # attempt. A safe fallback is dispatched right here as
                    # its own immediate, nested
                    # upstream request -- the same URL/method/headers/timeout
                    # -- independent of the outer attempt/iteration budget
                    # above, so it always fires exactly once even when this
                    # classified 477 arrives on the outer loop's very last
                    # iteration.
                    fingerprint = empty_response.policy_fingerprint(body)
                    fallback, detail = empty_response.build_fallback(body)
                    if fallback is None:
                        rejection_reason = detail.get("reason", "unknown")
                        fallback, dialogue_metrics = empty_response.recover_dialogue(
                            body, rejection_reason=rejection_reason
                        )
                        if fallback is None:
                            runtime_state.record_counter("empty_response_fallback_rejected")
                            runtime_state.record_counter("empty_response_recovery_exhausted")
                            runtime_state.record_failure("empty_response_fallback_rejected")
                            runtime_state.remember_empty_response_failure(
                                fingerprint,
                                capacity=empty_response.COOLDOWN_CAPACITY,
                                cooldown_seconds=empty_response.COOLDOWN_SECONDS,
                            )
                            _send_empty_response_exhausted(handler, 1)
                            runtime_state.log(
                                f"req={request_id} event=empty_response_fallback_rejected "
                                f"reason={detail.get('reason', 'unknown')} attempts=1 "
                                f"path={runtime_state.safe_request_path(handler.path)}"
                            )
                            return
                        detail = {"projected": True, "dialogue_recovery": True}
                        runtime_state.log(
                            f"req={request_id} event=empty_response_dialogue_recovery "
                            f"bytes={dialogue_metrics['original_bytes']}->{dialogue_metrics['recovery_bytes']} "
                            f"retained_messages={dialogue_metrics['retained_messages']} "
                            f"dropped_input_items={dialogue_metrics['dropped_input_items']} "
                            f"reason={rejection_reason} "
                            f"path={runtime_state.safe_request_path(handler.path)}"
                        )
                    runtime_state.record_counter("empty_response_fallback_attempts")
                    previous_bytes = len(attempt_body)
                    attempt_body = fallback
                    runtime_state.log(
                        f"req={request_id} event=empty_response_fallback "
                        f"projected={detail.get('projected', False)} "
                        f"bytes={previous_bytes}->{len(fallback)} "
                        f"policy={empty_response.POLICY_VERSION} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                    fallback_req = urllib.request.Request(
                        url, data=attempt_body if attempt_body else None, method=method
                    )
                    for k, v in out_headers.items():
                        fallback_req.add_header(k, v)
                    try:
                        resp = urlopen_direct(fallback_req, timeout=UPSTREAM_TIMEOUT)
                    except urllib.error.HTTPError as fallback_error:
                        try:
                            fallback_error.read()
                            fallback_status = fallback_error.code
                        finally:
                            fallback_error.close()
                        runtime_state.record_counter("empty_response_recovery_exhausted")
                        runtime_state.record_failure("empty_response_recovery_exhausted")
                        runtime_state.remember_empty_response_failure(
                            fingerprint,
                            capacity=empty_response.COOLDOWN_CAPACITY,
                            cooldown_seconds=empty_response.COOLDOWN_SECONDS,
                        )
                        _send_empty_response_exhausted(handler, 2)
                        runtime_state.log(
                            f"req={request_id} event=empty_response_fallback_failed "
                            f"upstream_status={fallback_status} attempts=2 "
                            f"path={runtime_state.safe_request_path(handler.path)}"
                        )
                        return
                    except Exception as fallback_exc:
                        runtime_state.record_counter("empty_response_recovery_exhausted")
                        runtime_state.record_failure("empty_response_recovery_exhausted")
                        runtime_state.remember_empty_response_failure(
                            fingerprint,
                            capacity=empty_response.COOLDOWN_CAPACITY,
                            cooldown_seconds=empty_response.COOLDOWN_SECONDS,
                        )
                        _send_empty_response_exhausted(handler, 2)
                        runtime_state.log(
                            f"req={request_id} event=empty_response_fallback_failed "
                            f"exception={runtime_state.safe_exception_label(fallback_exc)} attempts=2 "
                            f"path={runtime_state.safe_request_path(handler.path)}"
                        )
                        return
                    runtime_state.record_counter("empty_response_fallback_accepted")
                    runtime_state.log(
                        f"req={request_id} event=empty_response_fallback_accepted "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                    break
                handler.send_response(status_code)
                for k, v in error_headers.items():
                    if k.lower() not in _HOP_BY_HOP:
                        handler.send_header(k, v)
                handler.send_header("Content-Length", str(len(err_body)))
                handler.end_headers()
                handler.wfile.write(err_body)
                runtime_state.record_failure(classification)
                runtime_state.log(
                    f"req={request_id} event=upstream_http_terminal status={status_code} "
                    f"response_bytes={len(err_body)} attempts={attempt + 1} "
                    f"path={runtime_state.safe_request_path(handler.path)}"
                )
                return
            except Exception as e:
                # The classified-477 fallback is dispatched as its own
                # immediate nested request above, with its own HTTPError
                # and transport-exception handling; a transport failure
                # there never reaches this ordinary per-iteration handler.
                if used_input_variant_dialogue_recovery:
                    runtime_state.record_counter("input_variant_dialogue_recovery_exhausted")
                    runtime_state.record_failure("input_variant_dialogue_recovery_exhausted")
                    msg = json.dumps(
                        {
                            "error": {
                                "message": (
                                    "DMX input-variant recovery transport failed; retry the turn"
                                ),
                                "type": "upstream_unavailable",
                                "code": "input_variant_recovery_transport_error",
                            }
                        },
                        separators=(",", ":"),
                    ).encode()
                    handler.send_response(502)
                    handler.send_header("Content-Type", "application/json")
                    handler.send_header("Content-Length", str(len(msg)))
                    handler.end_headers()
                    handler.wfile.write(msg)
                    runtime_state.log(
                        f"req={request_id} event=input_variant_dialogue_recovery_exhausted "
                        f"exception={runtime_state.safe_exception_label(e)} path={runtime_state.safe_request_path(handler.path)}"
                    )
                    return
                if attempt < max_attempts - 1:
                    runtime_state.log(
                        f"req={request_id} event=upstream_transport_retry "
                        f"attempt={attempt + 1} exception={runtime_state.safe_exception_label(e)} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
                    time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue
                msg = json.dumps(
                    {
                        "error": {
                            "message": "DMX upstream transport failed after bounded retries; retry the turn",
                            "type": "upstream_unavailable",
                            "code": "upstream_transport_error",
                        }
                    },
                    separators=(",", ":"),
                ).encode()
                runtime_state.record_failure("upstream_transport_error")
                handler.send_response(502)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(msg)))
                handler.end_headers()
                handler.wfile.write(msg)
                runtime_state.log(
                    f"req={request_id} event=upstream_transport_exhausted "
                    f"exception={runtime_state.safe_exception_label(e)} path={runtime_state.safe_request_path(handler.path)}"
                )
                return

        if resp is None:
            msg = json.dumps(
                {
                    "error": {
                        "message": "DMX upstream transport failed after bounded retries; retry the turn",
                        "type": "upstream_unavailable",
                        "code": "upstream_transport_error",
                    }
                },
                separators=(",", ":"),
            ).encode()
            runtime_state.record_failure("upstream_transport_error")
            handler.send_response(502)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
            return

        # Stream the response back. Use chunked so we don't need a length up-front.
        ctype = resp.headers.get("Content-Type", "")
        is_sse = is_responses and "text/event-stream" in ctype.lower()

        def _send_stream_headers(r):
            handler.send_response(r.status)
            for k, v in r.headers.items():
                if k.lower() in _HOP_BY_HOP or k.lower() == "content-length":
                    continue
                handler.send_header(k, v)
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()

        if is_sse:
            # SSE: send headers lazily (on first downstream byte) so a stream
            # that dies before producing content can be transparently retried.
            def _reopen():
                # Preserve the exact request that produced this upstream SSE.
                # A recovered ``response_failed`` may be using a compact
                # suffix; reopening the original oversized history would
                # regress the repair during a pre-content reconnect.
                req2 = urllib.request.Request(
                    url, data=attempt_body if attempt_body else None, method=method
                )
                for k, v in out_headers.items():
                    req2.add_header(k, v)
                return urlopen_direct(req2, timeout=UPSTREAM_TIMEOUT)

            try:
                stream_result = sse_transport.relay(
                    handler,
                    resp,
                    handler.path,
                    request_id,
                    reopen=None if used_input_variant_dialogue_recovery else _reopen,
                    send_headers=lambda: _send_stream_headers(resp),
                )
                if stream_result["pre_content_exhausted"]:
                    if used_input_variant_dialogue_recovery:
                        runtime_state.record_counter("input_variant_dialogue_recovery_exhausted")
                        runtime_state.record_failure("input_variant_dialogue_recovery_exhausted")
                    msg = sse_transport.exhausted_payload(stream_result["attempts"])
                    handler.send_response(503)
                    handler.send_header("Content-Type", "application/json")
                    handler.send_header("Retry-After", "3")
                    handler.send_header("Content-Length", str(len(msg)))
                    handler.end_headers()
                    handler.wfile.write(msg)
                    runtime_state.log(
                        f"req={request_id} event=sse_pre_content_exhausted "
                        f"attempts={stream_result['attempts']} path={runtime_state.safe_request_path(handler.path)}"
                    )
                elif used_input_variant_dialogue_recovery and input_variant_dialogue_metrics:
                    runtime_state.record_counter("input_variant_dialogue_recovery_accepted")
                    m = input_variant_dialogue_metrics
                    runtime_state.log(
                        f"req={request_id} event=input_variant_dialogue_recovery_accepted "
                        f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                        f"retained_messages={m['retained_messages']} "
                        f"dropped_input_items={m['dropped_input_items']} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
            except (BrokenPipeError, ConnectionResetError):
                runtime_state.log(
                    f"req={request_id} event=downstream_client_closed path={runtime_state.safe_request_path(handler.path)}"
                )
            except Exception as e:
                runtime_state.log(
                    f"req={request_id} event=stream_handler_exception "
                    f"exception={runtime_state.safe_exception_label(e)} path={runtime_state.safe_request_path(handler.path)}"
                )
        else:
            _send_stream_headers(resp)
            try:
                import http.client

                while True:
                    try:
                        chunk = resp.read(8192)
                    except http.client.IncompleteRead as ir:
                        chunk = ir.partial  # flush whatever arrived, then finish cleanly
                        if chunk:
                            handler.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                        break
                    if not chunk:
                        break
                    handler.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                handler.wfile.write(b"0\r\n\r\n")
                if is_responses:
                    runtime_state.record_counter("responses_completed")
                if used_input_variant_dialogue_recovery and input_variant_dialogue_metrics:
                    runtime_state.record_counter("input_variant_dialogue_recovery_accepted")
                    m = input_variant_dialogue_metrics
                    runtime_state.log(
                        f"req={request_id} event=input_variant_dialogue_recovery_accepted "
                        f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                        f"retained_messages={m['retained_messages']} "
                        f"dropped_input_items={m['dropped_input_items']} "
                        f"path={runtime_state.safe_request_path(handler.path)}"
                    )
            except (BrokenPipeError, ConnectionResetError):
                # Client (Codex) closed the stream early — normal at turn end.
                runtime_state.log(
                    f"req={request_id} event=downstream_client_closed path={runtime_state.safe_request_path(handler.path)}"
                )
            except Exception as e:
                runtime_state.log(
                    f"req={request_id} event=stream_handler_exception "
                    f"exception={runtime_state.safe_exception_label(e)} path={runtime_state.safe_request_path(handler.path)}"
                )
    finally:
        if acquired:
            active_now = runtime_state.release_response_slot()
            runtime_state.log(
                f"req={request_id} event=responses_slot_released "
                f"active={active_now}/{RESPONSES_MAX_CONCURRENCY} path={runtime_state.safe_request_path(handler.path)}"
            )
