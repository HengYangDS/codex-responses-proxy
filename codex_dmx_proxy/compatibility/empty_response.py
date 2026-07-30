"""Fail-closed HTTP 477 empty-response compatibility policy.

This module owns classification, bounded projection, dialogue recovery, the
secret-free terminal payload, and cooldown keys for the exact DMX
``empty_response`` contract. It has no HTTP dispatch or mutable runtime state.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse

POLICY_VERSION = "empty-response-fallback-v5"
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

    The caller's exact bytes keep requests with different provider state
    independent. The policy version prevents collisions after rule changes.
    """
    return hashlib.sha256(POLICY_VERSION.encode("utf-8") + raw).hexdigest()


_EMPTY_RESPONSE_VALID_ROLES = frozenset(("user", "assistant", "developer", "system"))
_EMPTY_RESPONSE_STALE_SEARCH_TYPES = frozenset(
    ("web_search_call", "tool_search_call", "tool_search_output")
)
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


def _text_block_value(block):
    block_type = block.get("type")
    if block_type == "input_text":
        allowed = {"type", "text", "prompt_cache_breakpoint"}
    elif block_type == "output_text":
        allowed = {"type", "text", "annotations", "logprobs"}
    else:
        return None
    if set(block) - allowed or not isinstance(block.get("text"), str):
        return None
    return block["text"]


def _portable_input_image(block):
    if set(block) - {"type", "image_url", "detail"}:
        return None
    image_url = block.get("image_url")
    if not isinstance(image_url, str) or not image_url or any(ch.isspace() for ch in image_url):
        return None
    try:
        parsed = urllib.parse.urlsplit(image_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        _ = parsed.port
    except ValueError:
        return None
    image = {"type": "input_image", "image_url": image_url}
    detail = block.get("detail")
    if detail is not None:
        if detail not in ("low", "high", "auto", "original"):
            return None
        image["detail"] = detail
    return image


def project_input_text(value):
    """Project validated input-owned text and remote images onto input grammar."""
    if isinstance(value, str):
        return value, False
    if isinstance(value, list):
        projected = []
        changed = False
        for block in value:
            if not isinstance(block, dict):
                return None, False
            text = _text_block_value(block)
            if text is not None:
                projected.append({"type": "input_text", "text": text})
                changed = changed or set(block) != {"type", "text"} or block["type"] != "input_text"
                continue
            if block.get("type") == "input_image":
                image = _portable_input_image(block)
                if image is None:
                    return None, False
                projected.append(image)
                changed = changed or image != block
                continue
            return None, False
        return projected, changed
    return None, False


def project_assistant_text(value):
    """Project textual assistant history onto the easy-message string carrier."""
    if isinstance(value, str):
        return (value, False) if value else (None, False)
    if not isinstance(value, list):
        return None, False
    text_parts = []
    for block in value:
        if not isinstance(block, dict):
            return None, False
        text = _text_block_value(block)
        if text is not None:
            text_parts.append(text)
            continue
        if set(block) == {"type", "refusal"} and isinstance(block.get("refusal"), str):
            text_parts.append(block["refusal"])
            continue
        return None, False
    text = "".join(text_parts)
    return (text, True) if text else (None, False)


def recover_dialogue(raw: bytes, budget: int | None = None, *, rejection_reason: str | None = None):
    """Drop stale search history while retaining instructions and the final user message."""
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
            and item.get("type") == "message"
            and item.get("role") == "user"
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
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return None, None
    validated, _validation_detail = build_fallback(validation_raw, budget)
    if validated is None:
        return None, None

    dialogue = []
    selected_items = [
        item
        for item in original_items[:latest_user_index]
        if isinstance(item, dict)
        and item.get("type") == "message"
        and item.get("role") in ("system", "developer")
    ]
    selected_items.append(original_items[latest_user_index])
    for item in selected_items:
        if set(item.keys()) - _EMPTY_RESPONSE_MESSAGE_FIELDS:
            return None, None
        if item.get("phase") is not None:
            return None, None
        content, _changed = project_input_text(item.get("content"))
        if content is None:
            return None, None
        dialogue.append({"type": "message", "role": item["role"], "content": content})

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
    except (TypeError, ValueError, RecursionError, UnicodeError):
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
    """Accept only omitted, exact direct, or exact identified program callers."""
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


def _reject(reason: str):
    return None, {"status": "rejected", "reason": reason}


def _project_reasoning(item):
    if set(item) - _EMPTY_RESPONSE_REASONING_FIELDS:
        return _reject("unknown_reasoning_field")
    if item.get("summary") not in (None, []) or item.get("content") not in (None, []):
        return _reject("malformed_reasoning")
    return {
        "type": "message",
        "role": "assistant",
        "phase": "commentary",
        "content": OPAQUE_REASONING_MARKER,
    }, None


def _project_agent_message(item):
    if set(item) - _EMPTY_RESPONSE_AGENT_MESSAGE_FIELDS:
        return _reject("unknown_agent_message_field")
    author, recipient = item.get("author"), item.get("recipient")
    content, phase = item.get("content"), item.get("phase", "commentary")
    if not all(isinstance(value, str) and value for value in (author, recipient)):
        return _reject("malformed_agent_message")
    if phase not in _EMPTY_RESPONSE_VALID_PHASES:
        return _reject("invalid_phase")
    if not isinstance(content, list):
        return _reject("malformed_agent_message")
    projected, _ = project_assistant_text(content)
    if projected is None:
        return _reject("non_text_agent_content")
    header = json.dumps(
        {"type": "agent_message", "author": author, "recipient": recipient},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "type": "message",
        "role": "assistant",
        "phase": phase,
        "content": header + "\n" + projected,
    }, None


def _project_message(item):
    if set(item) - _EMPTY_RESPONSE_MESSAGE_FIELDS:
        return _reject("unknown_message_field")
    role, phase = item.get("role"), item.get("phase")
    if role not in _EMPTY_RESPONSE_VALID_ROLES:
        return _reject("invalid_role")
    if phase is not None and (role != "assistant" or phase not in _EMPTY_RESPONSE_VALID_PHASES):
        return _reject("invalid_phase")
    projector = project_assistant_text if role == "assistant" else project_input_text
    content, changed = projector(item.get("content"))
    if content is None:
        return _reject("non_text_message_content")
    projected = {"type": "message", "role": role, "content": content}
    if phase is not None:
        projected["phase"] = phase
    return projected, changed or projected != item


def _project_call(item, calls):
    item_type = item.get("type")
    if set(item) - _EMPTY_RESPONSE_CALL_FIELDS[item_type]:
        return _reject("unknown_call_field")
    call_id, name = item.get("call_id"), item.get("name")
    arg_field = _EMPTY_RESPONSE_CALL_ARG_FIELD[item_type]
    arguments, namespace, caller = item.get(arg_field), item.get("namespace"), item.get("caller")
    if not isinstance(call_id, str) or not call_id or call_id in calls:
        return _reject("malformed_call")
    if not isinstance(name, str) or not name or not isinstance(arguments, str):
        return _reject("malformed_call")
    if not _valid_namespace(namespace):
        return _reject("malformed_namespace")
    if not _valid_caller(caller):
        return _reject("malformed_caller")
    calls[call_id] = item_type
    projected = {"type": item_type, "call_id": call_id, "name": name, arg_field: arguments}
    projected.update(
        {
            key: value
            for key, value in (("namespace", namespace), ("caller", caller))
            if value is not None
        }
    )
    return projected, projected != item


def _project_output(item, calls, outputs_seen):
    item_type = item.get("type")
    if set(item) - _EMPTY_RESPONSE_OUTPUT_FIELDS:
        return _reject("unknown_output_field")
    call_id, caller = item.get("call_id"), item.get("caller")
    if not isinstance(call_id, str) or not call_id or call_id not in calls:
        return _reject("orphan_output")
    if calls[call_id] != _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT[item_type]:
        return _reject("mismatched_output")
    if call_id in outputs_seen:
        return _reject("duplicate_output")
    output, changed = project_input_text(item.get("output"))
    if output is None:
        return _reject("non_text_output")
    if not _valid_caller(caller):
        return _reject("malformed_caller")
    outputs_seen.add(call_id)
    projected = {"type": item_type, "call_id": call_id, "output": output}
    if caller is not None:
        projected["caller"] = caller
    return projected, changed or projected != item


def _project_items(items):
    calls: dict[str, str] = {}
    outputs_seen: set[str] = set()
    projected, changed = [], False
    for item in items:
        if not isinstance(item, dict):
            return _reject("invalid_item")
        item_type = item.get("type")
        if item_type == "reasoning":
            value, detail = _project_reasoning(item)
            item_changed = True
        elif item_type == "agent_message":
            value, detail = _project_agent_message(item)
            item_changed = True
        elif item_type == "message":
            value, detail = _project_message(item)
            item_changed = detail
        elif item_type in _EMPTY_RESPONSE_CALL_ARG_FIELD:
            value, detail = _project_call(item, calls)
            item_changed = detail
        elif item_type in _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT:
            value, detail = _project_output(item, calls, outputs_seen)
            item_changed = detail
        else:
            return _reject("unknown_item_type")
        if value is None:
            return value, detail
        projected.append(value)
        changed = changed or item_changed
    return projected, changed


def build_fallback(raw: bytes, budget: int | None = None):
    """Build one bounded provider-portable fallback, rejecting every unknown shape."""
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

    projected_input, projected = (
        (original_input, False) if original_items is None else _project_items(original_items)
    )
    if projected_input is None:
        return projected_input, projected
    changed = changed or projected

    if not changed:
        return raw, {"projected": False, "status": "accepted"}

    new_payload["input"] = projected_input
    try:
        fallback = json.dumps(new_payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return None, {"status": "rejected", "reason": "serialization_failed"}

    if len(fallback) > budget:
        return None, {"status": "rejected", "reason": "budget_exceeded"}

    return fallback, {
        "projected": True,
        "status": "accepted",
        "original_bytes": len(raw),
        "fallback_bytes": len(fallback),
    }
