"""Classify and recover bounded upstream Responses execution failures.

This owner admits recovery only for explicit provider execution failures. It
never edits stored history: each fallback is a strictly smaller request-local
projection that preserves the latest user request and, when possible, complete
tool call/output relationships.
"""

from __future__ import annotations

import json
from typing import cast

type JsonObject = dict[str, object]
type Request = tuple[JsonObject, list[object], int]
type RecoveryMetrics = dict[str, int | bool]
type Recovery = tuple[bytes | None, RecoveryMetrics | None]

COMPACTION_RATIO_DENOMINATOR = 2

_TOOL_PAIR_TYPES = {
    "custom_tool_call": "custom_tool_call_output",
    "function_call": "function_call_output",
}
_TOOL_CALL_TYPES = frozenset(_TOOL_PAIR_TYPES)
_TOOL_OUTPUT_TYPES = frozenset(_TOOL_PAIR_TYPES.values())


def _request(raw: bytes, minimum_items: int = 1) -> Request | None:
    """Decode a request with enough input items and return its latest user index."""
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("input")
    if not isinstance(items, list) or len(items) < minimum_items:
        return None
    latest_user = next(
        (
            index
            for index in range(len(items) - 1, -1, -1)
            if isinstance(items[index], dict)
            and items[index].get("type") == "message"
            and items[index].get("role") == "user"
        ),
        -1,
    )
    return (payload, items, latest_user) if latest_user >= 0 else None


def _budget(raw: bytes, budget: int) -> int | None:
    """Bound a positive caller budget by the required compaction ratio."""
    if not isinstance(budget, int) or budget <= 0:
        return None
    return min(budget, max(1, len(raw) // COMPACTION_RATIO_DENOMINATOR))


def retry_disposition(code: int, err_body: bytes) -> str:
    """Return ``full``, ``once``, or an empty non-retry disposition."""
    if code in (500, 502, 503, 504, 524):
        return "full"
    if code != 400:
        return ""
    try:
        document = json.loads(err_body)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return ""
    error = document.get("error") if isinstance(document, dict) else None
    if not isinstance(error, dict):
        return ""
    error_type = error.get("type")
    error_code = error.get("code")
    if error_code == "response_failed" and isinstance(error_type, str) and error_type:
        return "full"
    message = error.get("message")
    if (
        error_code == "invalid_prompt"
        and error_type == "invalid_request_error"
        and isinstance(message, str)
        and message.startswith("Request blocked.")
    ):
        return "full"
    if error_code == "invalid_payload":
        return "once"
    return ""


def exhausted_payload(attempts: int) -> bytes:
    """Return the retryable terminal payload after all bounded recovery fails."""
    return json.dumps(
        {
            "error": {
                "message": "Upstream rejected bounded Responses recovery; retry the turn",
                "type": "upstream_unavailable",
                "code": "response_failed_recovery_exhausted",
                "attempts": attempts,
            },
        },
        separators=(",", ":"),
    ).encode()


def tool_pair_boundary_is_safe(items: list[object], start: int) -> bool:
    """Return whether a retained suffix contains no orphaned tool output."""
    calls = set()
    for item in items[start:]:
        if not isinstance(item, dict):
            continue
        item = cast(JsonObject, item)
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        item_type = item.get("type")
        if item_type in _TOOL_CALL_TYPES:
            calls.add(call_id)
        elif item_type in _TOOL_OUTPUT_TYPES and call_id not in calls:
            return False
    return True


def compact_request(raw: bytes, budget: int) -> Recovery:
    """Build the oldest-prefix-only, pair-safe fallback for one failed request."""
    bounded_budget = _budget(raw, budget)
    request = _request(raw, minimum_items=2)
    if bounded_budget is None or request is None:
        return None, None
    payload, input_items, latest_user_index = request

    smallest = None
    for start in range(1, latest_user_index + 1):
        if not tool_pair_boundary_is_safe(input_items, start):
            continue
        candidate = dict(payload)
        candidate["input"] = input_items[start:]
        candidate["store"] = False
        candidate.pop("prompt_cache_key", None)
        compact = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
        metrics = {
            "original_bytes": len(raw),
            "budget_bytes": bounded_budget,
            "compact_bytes": len(compact),
            "removed_inputs": start,
            "retained_inputs": len(input_items) - start,
            "prompt_cache_key_removed": "prompt_cache_key" in payload,
        }
        if len(compact) <= bounded_budget:
            return compact, metrics
        if len(compact) < len(raw) and (smallest is None or len(compact) < len(smallest[0])):
            smallest = (compact, metrics)
    if smallest is not None:
        compact, metrics = smallest
        metrics["budget_met"] = False
        return compact, metrics
    return None, None


def recover_dialogue(raw: bytes, budget: int) -> Recovery:
    """Build the final instruction-and-user-only recovery request."""
    bounded_budget = _budget(raw, budget)
    request = _request(raw)
    if bounded_budget is None or request is None:
        return None, None
    payload, input_items, latest_user_index = request

    start = latest_user_index
    for index in range(latest_user_index, -1, -1):
        item = input_items[index]
        if (
            isinstance(item, dict)
            and cast(JsonObject, item).get("type") == "message"
            and cast(JsonObject, item).get("role") in ("developer", "system")
        ):
            start = index
            break

    dialogue = []
    if start != latest_user_index:
        dialogue.append(input_items[start])
    dialogue.append(input_items[latest_user_index])

    candidate = dict(payload)
    candidate["input"] = dialogue
    candidate["store"] = False
    candidate.pop("prompt_cache_key", None)
    recovery = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
    if len(recovery) > bounded_budget or len(recovery) >= len(raw):
        return None, None
    return recovery, {
        "original_bytes": len(raw),
        "recovery_bytes": len(recovery),
        "budget_bytes": bounded_budget,
        "retained_messages": len(dialogue),
        "dropped_input_items": len(input_items) - len(dialogue),
        "prompt_cache_key_removed": "prompt_cache_key" in payload,
    }
