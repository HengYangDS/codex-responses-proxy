#!/usr/bin/env python3
"""Classify and recover bounded upstream Responses execution failures.

This owner admits recovery only for explicit provider execution failures. It
never edits stored history: each fallback is a strictly smaller request-local
projection that preserves the latest user request and, when possible, complete
tool call/output relationships.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import cast

import empty_response

type JsonObject = dict[str, object]

COMPACTION_BUDGET = int(os.environ.get("DMX_RESPONSE_FAILED_COMPACTION_BUDGET", 512 * 1024))
COMPACTION_RATIO_DENOMINATOR = 2
MAX_STAGES = max(0, int(os.environ.get("DMX_RESPONSE_FAILED_MAX_STAGES", "3")))
DIALOGUE_SLOTS = 1

_TOOL_PAIR_TYPES = {
    "custom_tool_call": "custom_tool_call_output",
    "function_call": "function_call_output",
}
_TOOL_CALL_TYPES = frozenset(_TOOL_PAIR_TYPES)
_TOOL_OUTPUT_TYPES = frozenset(_TOOL_PAIR_TYPES.values())


def retry_disposition(code: int, err_body: bytes) -> str:
    """Return ``full``, ``once``, or an empty non-retry disposition."""
    if code in (429, 500, 502, 503, 504, 524):
        return "full"
    if code == 477:
        return "full" if empty_response.is_classified_error(code, err_body) else ""
    if code != 400:
        return ""
    try:
        lower_body = err_body.lower()
    except Exception:
        return ""
    if b"invalid_encrypted_content" in lower_body or b"could not be verified" in lower_body:
        return ""
    if b"response_failed" in lower_body or b"openai responses stream failed" in lower_body:
        return "full"
    if b'"code":"invalid_prompt"' in lower_body and b"request blocked" in lower_body:
        return "full"
    if b"invalid_payload" in lower_body or b"does not match the expected schema" in lower_body:
        return "once"
    return ""


def exhausted_payload(attempts: int) -> bytes:
    """Return the retryable terminal payload after all bounded recovery fails."""
    return json.dumps(
        {
            "error": {
                "message": "DMX upstream rejected bounded Responses recovery; retry the turn",
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


def compact_request(raw: bytes, budget: int | None = None):
    """Build the oldest-prefix-only, pair-safe fallback for one failed request."""
    if budget is None:
        budget = COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    budget = min(budget, max(1, len(raw) // COMPACTION_RATIO_DENOMINATOR))
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or len(original_items) < 2:
        return None, None
    input_items = cast(list[object], original_items)

    latest_user_index = max(
        (
            index
            for index, item in enumerate(input_items)
            if (
                isinstance(item, dict)
                and cast(Mapping[str, object], item).get("type") == "message"
                and cast(Mapping[str, object], item).get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    smallest = None
    for start in range(1, latest_user_index + 1):
        if not tool_pair_boundary_is_safe(input_items, start):
            continue
        candidate = dict(payload)
        candidate["input"] = original_items[start:]
        candidate.pop("prompt_cache_key", None)
        try:
            compact = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
        except Exception:
            return None, None
        metrics = {
            "original_bytes": len(raw),
            "budget_bytes": budget,
            "compact_bytes": len(compact),
            "removed_inputs": start,
            "retained_inputs": len(original_items) - start,
            "prompt_cache_key_removed": "prompt_cache_key" in payload,
        }
        if len(compact) <= budget:
            return compact, metrics
        if len(compact) < len(raw) and (smallest is None or len(compact) < len(smallest[0])):
            smallest = (compact, metrics)
    if smallest is not None:
        compact, metrics = smallest
        metrics["budget_met"] = False
        return compact, metrics
    return None, None


def recover_dialogue(raw: bytes, budget: int | None = None):
    """Build the final instruction-and-user-only recovery request."""
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or not original_items:
        return None, None
    input_items = cast(list[object], original_items)

    latest_user_index = max(
        (
            index
            for index, item in enumerate(input_items)
            if (
                isinstance(item, dict)
                and cast(Mapping[str, object], item).get("type") == "message"
                and cast(Mapping[str, object], item).get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    start = latest_user_index
    for index in range(latest_user_index, -1, -1):
        item = original_items[index]
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") in ("developer", "system")
        ):
            start = index
            break

    dialogue = []
    if start != latest_user_index:
        dialogue.append(original_items[start])
    dialogue.append(original_items[latest_user_index])

    candidate = dict(payload)
    candidate["input"] = dialogue
    candidate.pop("prompt_cache_key", None)
    try:
        recovery = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
    except Exception:
        return None, None

    if budget is None:
        budget = COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    budget = min(budget, max(1, len(raw) // COMPACTION_RATIO_DENOMINATOR))
    if len(recovery) > budget or len(recovery) >= len(raw):
        return None, None
    return recovery, {
        "original_bytes": len(raw),
        "recovery_bytes": len(recovery),
        "budget_bytes": budget,
        "retained_messages": len(dialogue),
        "dropped_input_items": len(original_items) - len(dialogue),
        "prompt_cache_key_removed": "prompt_cache_key" in payload,
    }
