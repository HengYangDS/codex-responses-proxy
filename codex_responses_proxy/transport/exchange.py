"""One upstream exchange and its bounded recovery state machine."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

from codex_responses_proxy.recovery import input_variant
from codex_responses_proxy.recovery import response_failed
from codex_responses_proxy.runtime import state
from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.transport import relay as downstream

UPSTREAM_TIMEOUT = runtime_config.load().upstream_timeout
INPUT_VARIANT_DIALOGUE_SLOTS = 1
_MAX_ATTEMPTS = 4
_BACKOFFS = (0.4, 1.0, 2.0)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen_direct(request: urllib.request.Request, timeout: float):
    """Open one upstream request without system or environment HTTP proxies."""
    return _DIRECT_OPENER.open(request, timeout=timeout)


def _request(url: str, body: bytes, method: str, headers: dict[str, str]) -> urllib.request.Request:
    request = urllib.request.Request(url, data=body or None, method=method)
    for name, value in headers.items():
        request.add_header(name, value)
    return request


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
class Exchange:
    """Carry one request through bounded upstream recovery attempts."""

    handler: BaseHTTPRequestHandler
    method: str
    request_id: int
    body: bytes
    url: str
    headers: dict[str, str]
    is_responses: bool
    attempt_body: bytes
    profile: provider_registry.Profile
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
        state.log(
            f"req={self.request_id} event={event} provider={self.profile.name} {detail}path={path}"
        )

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


def _classification(
    status_code: int,
    payload: bytes,
    disposition: str,
    exact: bool,
    empty: bool,
) -> str:
    lower = payload.lower()
    blocked = all(map(lower.__contains__, (b'"code":"invalid_prompt"', b"request blocked")))
    special = {
        (True, 400, "", False): "input_variant_validation_error",
        (False, 400, "full", False): "response_failed",
        (False, 400, "full", True): "blocked_invalid_prompt",
    }.get((exact, status_code, disposition, blocked))
    if empty:
        return "empty_response"
    return special or "_".join(filter(None, (f"http_{status_code}", disposition)))


def _recover_input_variant(exchange: Exchange) -> bool:
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


def _recover_response_failed(exchange: Exchange, status_code: int, disposition: str) -> bool:
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


def _exhaust_response_failed(exchange: Exchange) -> None:
    state.record_counter("response_failed_recovery_exhausted")
    state.record_failure("response_failed_recovery_exhausted")
    attempts = exchange.response_failed_stages + int(exchange.used_response_failed_dialogue) + 1
    downstream.send_payload(
        exchange.handler, 503, response_failed.exhausted_payload(attempts), retry_after="3"
    )
    exchange.log(
        "response_failed_recovery_exhausted",
        f"attempts={attempts} pair_safe_stages={exchange.response_failed_stages} "
        f"dialogue_recovery={exchange.used_response_failed_dialogue} upstream_status=400 ",
    )


def _reject_empty_response(
    exchange: Exchange, fingerprint: str, attempts: int, event: str, detail: str
) -> None:
    policy = exchange.profile.empty_response
    if policy is None:
        raise RuntimeError("empty-response recovery requires a provider policy")
    state.record_counter("empty_response_recovery_exhausted")
    state.record_failure("empty_response_recovery_exhausted")
    state.remember_empty_response_failure(
        fingerprint,
        capacity=policy.COOLDOWN_CAPACITY,
        cooldown_seconds=policy.COOLDOWN_SECONDS,
    )
    downstream.send_empty_response_exhausted(exchange.handler, policy, attempts)
    exchange.log(event, detail)


def _retry_empty_response(exchange: Exchange) -> bool:
    policy = exchange.profile.empty_response
    if policy is None:
        return False
    fingerprint = policy.policy_fingerprint(exchange.body)
    state.record_counter("empty_response_retry_attempts")
    exchange.log(
        "empty_response_retry",
        f"bytes={len(exchange.attempt_body)} policy={policy.POLICY_VERSION} ",
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
            "empty_response_retry_failed",
            f"upstream_status={status} attempts=2 ",
        )
        return True
    except Exception as error:
        _reject_empty_response(
            exchange,
            fingerprint,
            2,
            "empty_response_retry_failed",
            f"exception={state.safe_exception_label(error)} attempts=2 ",
        )
        return True
    state.record_counter("empty_response_retry_accepted")
    exchange.log("empty_response_retry_accepted")
    exchange.response = exchange_response
    return False


def _http_error(exchange: Exchange, error: urllib.error.HTTPError, attempt: int) -> str:
    try:
        payload, status_code, headers = error.read(), error.code, error.headers
    finally:
        error.close()
    portable = response_failed.retry_disposition(status_code, payload)
    policy = exchange.profile.empty_response
    empty = policy is not None and policy.is_classified_error(status_code, payload)
    disposition = "full" if empty else portable
    exact = input_variant.is_exact_validation_error(status_code, payload)
    classification = _classification(status_code, payload, disposition, exact, empty)
    state.record_upstream_classification(classification)
    if exchange.used_input_variant_dialogue:
        exchange.input_variant_exhausted(f"upstream_status={status_code} ")
        downstream.relay_error(exchange.handler, status_code, headers, payload)
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
    if empty:
        return "terminal" if _retry_empty_response(exchange) else "accepted"
    downstream.relay_error(exchange.handler, status_code, headers, payload)
    state.record_failure(classification)
    exchange.log(
        "upstream_http_terminal",
        f"status={status_code} response_bytes={len(payload)} attempts={attempt + 1} ",
    )
    return "terminal"


def _transport_error(exchange: Exchange, error: Exception, attempt: int) -> str:
    if exchange.used_input_variant_dialogue:
        exchange.input_variant_exhausted(f"exception={state.safe_exception_label(error)} ")
        downstream.send_payload(
            exchange.handler,
            502,
            downstream.json_error(
                "Upstream input-variant recovery transport failed; retry the turn",
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
    downstream.send_payload(
        exchange.handler,
        502,
        downstream.json_error(
            "Upstream transport failed after bounded retries; retry the turn",
            "upstream_unavailable",
            "upstream_transport_error",
        ),
    )
    exchange.log(
        "upstream_transport_exhausted",
        f"exception={state.safe_exception_label(error)} ",
    )
    return "terminal"


def open_upstream(exchange: Exchange):
    """Open an upstream response or emit the bounded terminal error."""
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
    downstream.send_payload(
        exchange.handler,
        502,
        downstream.json_error(
            "Upstream transport failed after bounded retries; retry the turn",
            "upstream_unavailable",
            "upstream_transport_error",
        ),
    )
    return None
