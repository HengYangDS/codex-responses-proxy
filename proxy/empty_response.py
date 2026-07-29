"""Fail-closed HTTP 477 empty-response compatibility policy.

This module owns classification, bounded projection, dialogue recovery, the
secret-free terminal payload, and cooldown keys for the exact DMX
``empty_response`` contract. It has no HTTP dispatch or mutable runtime state.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Mapping
from typing import cast

type ReadOnlyJsonObject = Mapping[str, object]

POLICY_VERSION = "empty-response-fallback-v4"
OPAQUE_REASONING_MARKER = "[reasoning omitted: opaque provider state cannot be replayed]"


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read one bounded integer without importing process-owned runtime state."""
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


FALLBACK_BUDGET = _bounded_env_int(
    "DMX_EMPTY_RESPONSE_FALLBACK_BUDGET", 4 * 1024 * 1024, 4 * 1024, 4 * 1024 * 1024
)
COOLDOWN_SECONDS = _bounded_env_int("DMX_EMPTY_RESPONSE_COOLDOWN_SECONDS", 30, 1, 300)
COOLDOWN_CAPACITY = 1024


def is_classified_error(code: int, error_body: bytes) -> bool:
    """Return whether ``error_body`` is the exact DMX HTTP 477 empty contract."""
    if code != 477:
        return False
    try:
        payload = json.loads(error_body)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    return (
        isinstance(error, dict)
        and error.get("type") == "dmx_api_error"
        and error.get("code") == "empty_response"
    )


def exhausted_payload(attempts: int) -> bytes:
    """Return a stable local 503 after DMX exhausts empty-response retries.

    HTTP 477 is an upstream-specific extension. Once the proxy has classified
    it and exhausted its bounded recovery budget, preserve the retryable
    semantics with standard HTTP 503 rather than exposing an unknown status to
    the client. The response contains no upstream payload or request content.
    """
    return json.dumps(
        {
            "error": {
                "message": "DMX upstream returned empty responses after bounded retries",
                "type": "upstream_unavailable",
                "code": "dmx_empty_response_exhausted",
                "attempts": attempts,
            },
        },
        separators=(",", ":"),
    ).encode()


def policy_fingerprint(raw: bytes) -> str:
    """Bind a cooldown key to both the compat policy and the exact request bytes.

    Two requests that differ only in top-level provider state (for example a
    different ``previous_response_id``) must cool down independently even when
    the fallback bodies they would build turn out identical, so the key is
    derived from the caller's own bytes rather than from the projected
    fallback. Folding in the policy version means a future change to the
    projection rules cannot collide with an older cached cooldown entry.
    """
    return hashlib.sha256(POLICY_VERSION.encode("utf-8") + raw).hexdigest()


_EMPTY_RESPONSE_VALID_ROLES = frozenset(("user", "assistant", "developer", "system"))
_EMPTY_RESPONSE_STALE_SEARCH_TYPES = frozenset(
    ("web_search_call", "tool_search_call", "tool_search_output")
)
# Fixed, closed enum: any phase this proxy has not itself observed and vetted
# is rejected rather than passed through, since an unknown phase value cannot
# be shown to be safe to replay.
_EMPTY_RESPONSE_VALID_PHASES = frozenset(("commentary", "final_answer"))
_EMPTY_RESPONSE_MESSAGE_FIELDS = frozenset(("type", "id", "status", "role", "content", "phase"))
_EMPTY_RESPONSE_AGENT_MESSAGE_FIELDS = frozenset(
    ("type", "id", "status", "author", "recipient", "phase", "content")
)
_EMPTY_RESPONSE_CALL_ARG_FIELD = {"function_call": "arguments", "custom_tool_call": "input"}
_EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT = {
    "function_call_output": "function_call",
    "custom_tool_call_output": "custom_tool_call",
}
_EMPTY_RESPONSE_CALL_FIELDS = {
    call_type: frozenset(
        ("type", "id", "status", "call_id", "name", arg_field, "namespace", "caller")
    )
    for call_type, arg_field in _EMPTY_RESPONSE_CALL_ARG_FIELD.items()
}
_EMPTY_RESPONSE_OUTPUT_FIELDS = frozenset(("type", "id", "status", "call_id", "output", "caller"))
_EMPTY_RESPONSE_REASONING_FIELDS = frozenset(
    ("type", "id", "status", "encrypted_content", "summary", "content")
)


def project_text_only(value):
    """Return a lossless text projection, or ``None`` for unrepresentable content.

    Plain strings and exact ``input_text`` blocks already conform to the
    request-side Responses shape. Exact ``output_text`` blocks are standard
    replayed assistant history, and their sole visible ``text`` value has the
    same semantics when represented as ``input_text``. Any additional field or
    non-text block remains unrepresentable and fails closed rather than being
    silently discarded.
    """
    if isinstance(value, str):
        return value, False
    if isinstance(value, list):
        projected = []
        changed = False
        for block in value:
            if not isinstance(block, dict):
                return None, False
            if set(block.keys()) != {"type", "text"}:
                return None, False
            if not isinstance(block.get("text"), str):
                return None, False
            if block.get("type") == "input_text":
                projected.append(block)
                continue
            if block.get("type") == "output_text":
                projected.append({"type": "input_text", "text": block["text"]})
                changed = True
                continue
            return None, False
        return projected, changed
    return None, False


def recover_dialogue(raw: bytes, budget: int | None = None, *, rejection_reason: str | None = None):
    """Build a strict current-instruction/current-user fallback for HTTP 477.

    This is used only when exact stale search items make the semantic-preserving
    empty-response projection reject an otherwise representable replay. It keeps
    every preceding system/developer instruction in original order and the final
    user message. No later state, arbitrary unknown item, or unrepresentable
    historical content may be silently discarded.
    """
    if rejection_reason is not None and rejection_reason != "unknown_item_type":
        return None, None
    if budget is None:
        budget = FALLBACK_BUDGET
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        return None, None
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or not original_items:
        return None, None

    latest_user_index = max(
        (
            index
            for index, item in enumerate(original_items)
            if isinstance(item, dict)
            and cast(ReadOnlyJsonObject, item).get("type") == "message"
            and cast(ReadOnlyJsonObject, item).get("role") == "user"
        ),
        default=-1,
    )
    if latest_user_index < 0 or latest_user_index != len(original_items) - 1:
        return None, None

    stale_search_indexes = {
        index
        for index, item in enumerate(original_items[:latest_user_index])
        if isinstance(item, dict) and item.get("type") in _EMPTY_RESPONSE_STALE_SEARCH_TYPES
    }
    if not stale_search_indexes:
        return None, None

    validation_payload = dict(payload)
    validation_payload["input"] = [
        item for index, item in enumerate(original_items) if index not in stale_search_indexes
    ]
    try:
        validation_raw = json.dumps(
            validation_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except Exception:
        return None, None
    validated, _validation_detail = build_fallback(validation_raw, budget)
    if validated is None:
        return None, None

    selected_indexes = [
        index
        for index, item in enumerate(original_items[:latest_user_index])
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") in ("system", "developer")
        )
    ]
    selected_indexes.append(latest_user_index)

    dialogue = []
    for index in selected_indexes:
        item = original_items[index]
        if set(item.keys()) - _EMPTY_RESPONSE_MESSAGE_FIELDS:
            return None, None
        role = item.get("role")
        if role not in _EMPTY_RESPONSE_VALID_ROLES:
            return None, None
        phase = item.get("phase")
        if phase is not None and (role != "assistant" or phase not in _EMPTY_RESPONSE_VALID_PHASES):
            return None, None
        content, _changed = project_text_only(item.get("content"))
        if content is None:
            return None, None
        kept = {"type": "message", "role": role, "content": content}
        if phase is not None:
            kept["phase"] = phase
        dialogue.append(kept)

    candidate = dict(payload)
    candidate["input"] = dialogue
    for field in ("previous_response_id", "conversation", "prompt_cache_key"):
        candidate.pop(field, None)
    if "include" in candidate:
        include = candidate["include"]
        if not isinstance(include, list) or any(not isinstance(value, str) for value in include):
            return None, None
        candidate["include"] = [
            value for value in include if value != "reasoning.encrypted_content"
        ]
    try:
        recovery = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except Exception:
        return None, None
    if len(recovery) > budget or len(recovery) >= len(raw):
        return None, None
    return recovery, {
        "original_bytes": len(raw),
        "recovery_bytes": len(recovery),
        "retained_messages": len(dialogue),
        "dropped_input_items": len(original_items) - len(dialogue),
    }


def _valid_caller(caller) -> bool:
    """A caller marker must be omitted, ``{"type":"direct"}``, or a well-formed program caller.

    Only these two closed shapes can be shown to be losslessly representable:
    ``{"type": "direct"}`` with no other keys, or
    ``{"type": "program", "caller_id": <non-empty str>}`` with no other keys.
    Any other ``type`` value, a ``program`` caller missing or with an empty
    ``caller_id``, or any extra key is rejected rather than copied through
    unexamined.
    """
    if caller is None:
        return True
    if not isinstance(caller, dict):
        return False
    caller_type = caller.get("type")
    if caller_type == "direct":
        return set(caller.keys()) == {"type"}
    if caller_type == "program":
        return (
            set(caller.keys()) == {"type", "caller_id"}
            and isinstance(caller.get("caller_id"), str)
            and caller["caller_id"] != ""
        )
    return False


def _valid_namespace(namespace) -> bool:
    """A namespace marker must be omitted or a non-empty string."""
    return namespace is None or (isinstance(namespace, str) and namespace != "")


def build_fallback(raw: bytes, budget: int | None = None):
    """Build the single bounded, text-only fallback for a classified 477.

    This is a fail-closed projector, not a general history rewriter: every
    item type is matched against an explicit allow-list of semantic fields --
    never copied through with an exclude-list -- so an unknown or additional
    field on an otherwise-known item rejects the whole fallback instead of
    being silently forwarded or silently dropped. The same applies to any
    unknown item, invalid role/phase, malformed call/output/caller/namespace,
    non-text content, orphaned/mismatched/duplicate tool output, or otherwise
    unrepresentable shape: the caller stays free to expose the original
    upstream response rather than receive a guessed projection. Only known
    provider-owned state is removed: top-level ``previous_response_id`` /
    ``conversation`` / ``prompt_cache_key``, the ``reasoning.encrypted_content``
    include hint, and each known item's own ``id`` and ``status``. A string
    ``input`` (rather than a list of items) is preserved losslessly since it
    carries no items to project. A ``reasoning`` item maps to a fixed opaque
    marker only when its own visible ``summary``/``content`` is empty -- a
    reasoning item that also carries visible summary or content text cannot
    be losslessly represented by the fixed marker and is rejected instead of
    silently discarding that text. An ``agent_message`` maps to a plain
    assistant message with a deterministic, JSON-escaped author/recipient
    header so that quoted or newline-bearing values can never break the fixed
    envelope; both keep their position in ``input``. Returns ``(raw, detail)``
    unchanged when no projection is needed at all, so a caller can retry the
    identical bytes exactly once. Returns ``(None, detail)`` when the request
    cannot be safely projected, with ``detail["status"] == "rejected"``.
    """
    if budget is None:
        budget = FALLBACK_BUDGET
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        return None, {"status": "rejected", "reason": "invalid_budget"}
    try:
        payload = json.loads(raw)
    except Exception:
        return None, {"status": "rejected", "reason": "invalid_json"}
    if not isinstance(payload, dict):
        return None, {"status": "rejected", "reason": "not_object"}

    original_input = payload.get("input", [])
    if isinstance(original_input, str):
        original_items = None
    elif isinstance(original_input, list):
        original_items = original_input
    else:
        return None, {"status": "rejected", "reason": "invalid_input"}

    changed = False
    new_payload = dict(payload)
    for field in ("previous_response_id", "conversation", "prompt_cache_key"):
        if field in new_payload:
            del new_payload[field]
            changed = True

    if "include" in new_payload:
        include = new_payload["include"]
        if not isinstance(include, list) or any(not isinstance(value, str) for value in include):
            return None, {"status": "rejected", "reason": "invalid_include"}
        trimmed_include = [value for value in include if value != "reasoning.encrypted_content"]
        if len(trimmed_include) != len(include):
            new_payload["include"] = trimmed_include
            changed = True

    if original_items is None:
        # A string ``input`` carries no items to project; only the top-level
        # provider bindings stripped above could have required any change.
        projected_input = original_input
    else:
        calls: dict[str, str] = {}
        outputs_seen: set[str] = set()
        projected_items = []

        for item in original_items:
            if not isinstance(item, dict):
                return None, {"status": "rejected", "reason": "invalid_item"}
            item_type = item.get("type")

            if item_type == "reasoning":
                if set(item.keys()) - _EMPTY_RESPONSE_REASONING_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_reasoning_field"}
                if item.get("summary") not in (None, []):
                    return None, {"status": "rejected", "reason": "malformed_reasoning"}
                if item.get("content") not in (None, []):
                    return None, {"status": "rejected", "reason": "malformed_reasoning"}
                projected_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": [
                            {"type": "input_text", "text": OPAQUE_REASONING_MARKER},
                        ],
                    }
                )
                changed = True
                continue

            if item_type == "agent_message":
                if set(item.keys()) - _EMPTY_RESPONSE_AGENT_MESSAGE_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_agent_message_field"}
                author = item.get("author")
                recipient = item.get("recipient")
                content = item.get("content")
                phase = item.get("phase", "commentary")
                if not isinstance(author, str) or author == "":
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                if not isinstance(recipient, str) or recipient == "":
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                if phase not in _EMPTY_RESPONSE_VALID_PHASES:
                    return None, {"status": "rejected", "reason": "invalid_phase"}
                if not isinstance(content, list):
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                projected_content, content_changed = project_text_only(content)
                if projected_content is None:
                    return None, {"status": "rejected", "reason": "non_text_agent_content"}
                header_text = json.dumps(
                    {"type": "agent_message", "author": author, "recipient": recipient},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                header = {"type": "input_text", "text": header_text}
                projected_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": phase,
                        "content": [header, *projected_content],
                    }
                )
                changed = True
                continue

            if item_type == "message":
                if set(item.keys()) - _EMPTY_RESPONSE_MESSAGE_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_message_field"}
                role = item.get("role")
                if role not in _EMPTY_RESPONSE_VALID_ROLES:
                    return None, {"status": "rejected", "reason": "invalid_role"}
                phase = item.get("phase")
                if phase is not None and (
                    role != "assistant" or phase not in _EMPTY_RESPONSE_VALID_PHASES
                ):
                    return None, {"status": "rejected", "reason": "invalid_phase"}
                content = item.get("content")
                projected_content, content_changed = project_text_only(content)
                if projected_content is None:
                    return None, {"status": "rejected", "reason": "non_text_message_content"}
                kept = {"type": "message", "role": role, "content": projected_content}
                if phase is not None:
                    kept["phase"] = phase
                if content_changed or kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            if item_type in _EMPTY_RESPONSE_CALL_ARG_FIELD:
                if set(item.keys()) - _EMPTY_RESPONSE_CALL_FIELDS[item_type]:
                    return None, {"status": "rejected", "reason": "unknown_call_field"}
                call_id = item.get("call_id")
                name = item.get("name")
                arg_field = _EMPTY_RESPONSE_CALL_ARG_FIELD[item_type]
                arguments = item.get(arg_field)
                namespace = item.get("namespace")
                caller = item.get("caller")
                if not isinstance(call_id, str) or call_id == "" or call_id in calls:
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not isinstance(name, str) or name == "":
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not isinstance(arguments, str):
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not _valid_namespace(namespace):
                    return None, {"status": "rejected", "reason": "malformed_namespace"}
                if not _valid_caller(caller):
                    return None, {"status": "rejected", "reason": "malformed_caller"}
                calls[call_id] = item_type
                kept = {"type": item_type, "call_id": call_id, "name": name, arg_field: arguments}
                if namespace is not None:
                    kept["namespace"] = namespace
                if caller is not None:
                    kept["caller"] = caller
                if kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            if item_type in _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT:
                if set(item.keys()) - _EMPTY_RESPONSE_OUTPUT_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_output_field"}
                call_id = item.get("call_id")
                output = item.get("output")
                caller = item.get("caller")
                if not isinstance(call_id, str) or call_id == "" or call_id not in calls:
                    return None, {"status": "rejected", "reason": "orphan_output"}
                if calls[call_id] != _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT[item_type]:
                    return None, {"status": "rejected", "reason": "mismatched_output"}
                if call_id in outputs_seen:
                    return None, {"status": "rejected", "reason": "duplicate_output"}
                projected_output, output_changed = project_text_only(output)
                if projected_output is None:
                    return None, {"status": "rejected", "reason": "non_text_output"}
                if not _valid_caller(caller):
                    return None, {"status": "rejected", "reason": "malformed_caller"}
                outputs_seen.add(call_id)
                kept = {"type": item_type, "call_id": call_id, "output": projected_output}
                if caller is not None:
                    kept["caller"] = caller
                if output_changed or kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            return None, {"status": "rejected", "reason": "unknown_item_type"}

        projected_input = projected_items

    if not changed:
        return raw, {"projected": False, "status": "accepted"}

    new_payload["input"] = projected_input
    try:
        fallback = json.dumps(new_payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except Exception:
        return None, {"status": "rejected", "reason": "serialize_failed"}

    if len(fallback) > budget:
        return None, {"status": "rejected", "reason": "budget_exceeded"}

    return fallback, {
        "projected": True,
        "status": "accepted",
        "original_bytes": len(raw),
        "fallback_bytes": len(fallback),
    }
