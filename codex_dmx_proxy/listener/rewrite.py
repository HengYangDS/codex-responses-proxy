#!/usr/bin/env python3
"""Project Responses replay onto one provider-portable network form.

The local Codex conversation remains authoritative and untouched. This module
owns only request-local replay normalization and downstream event sanitization.
Unknown replay structures fail closed before upstream I/O; diagnostics contain
only bounded structural reason codes and counters.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import cast

type JsonObject = dict[str, object]

OPAQUE_CONTENT_MARKER = "[opaque provider content omitted: not portable across providers]"

_PROVIDER_BINDINGS = ("previous_response_id", "conversation", "prompt_cache_key")
_VALID_ROLES = frozenset(("user", "assistant", "developer", "system"))
_VALID_PHASES = frozenset(("commentary", "final_answer"))
_DROP_ITEM_TYPES = frozenset(
    (
        "reasoning",
        "item_reference",
        "web_search_call",
        "tool_search_call",
        "tool_search_output",
        "compaction",
    )
)
_SEARCH_ITEM_TYPES = frozenset(("web_search_call", "tool_search_call", "tool_search_output"))
_CALL_ARGUMENT_FIELD = {"function_call": "arguments", "custom_tool_call": "input"}
_OUTPUT_CALL_TYPE = {
    "function_call_output": "function_call",
    "custom_tool_call_output": "custom_tool_call",
}
_MESSAGE_FIELDS = frozenset(
    (
        "type",
        "id",
        "status",
        "role",
        "content",
        "phase",
        "name",
        "internal_chat_message_metadata_passthrough",
    )
)
_AGENT_FIELDS = frozenset(
    (
        "type",
        "id",
        "status",
        "author",
        "recipient",
        "phase",
        "content",
        "encrypted_content",
        "internal_chat_message_metadata_passthrough",
    )
)
_CALL_FIELDS = {
    item_type: frozenset(
        (
            "type",
            "id",
            "status",
            "call_id",
            "name",
            argument_field,
            "namespace",
            "caller",
            "internal_chat_message_metadata_passthrough",
        )
    )
    for item_type, argument_field in _CALL_ARGUMENT_FIELD.items()
}
_OUTPUT_FIELDS = frozenset(
    (
        "type",
        "id",
        "status",
        "call_id",
        "name",
        "output",
        "caller",
        "encrypted_content",
        "internal_chat_message_metadata_passthrough",
    )
)


class ProjectionRejected(ValueError):
    """A replay structure has no proved provider-portable representation."""


def _reject(reason: str) -> None:
    raise ProjectionRejected(reason)


def _unknown_fields(item: JsonObject, allowed: frozenset[str], reason: str) -> None:
    if set(item) - allowed:
        _reject(reason)


def _valid_caller(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("type") == "direct":
        return set(value) == {"type"}
    caller_id = value.get("caller_id")
    return (
        value.get("type") == "program"
        and set(value) == {"type", "caller_id"}
        and isinstance(caller_id, str)
        and bool(caller_id)
    )


def _is_replayable_remote_image_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        _ = parsed.port
    except ValueError:
        return False
    return True


def _project_content(
    value: object,
    *,
    allow_images: bool,
    encrypted_marker: bool,
) -> tuple[object, bool, int, int, int]:
    """Return content, change flag, ciphertext removals, markers, and local images."""
    if isinstance(value, str):
        if not value:
            _reject("empty_text_content")
        return value, False, 0, 0, 0
    if not isinstance(value, list):
        _reject("invalid_content")
    blocks = cast("list[object]", value)

    projected: list[JsonObject] = []
    changed = False
    encrypted = 0
    local_images = 0
    for block in blocks:
        if not isinstance(block, dict):
            _reject("invalid_content_block")
        typed = cast(JsonObject, block)
        block_type = typed.get("type")
        if block_type in ("input_text", "output_text"):
            if set(typed) != {"type", "text"} or not isinstance(typed.get("text"), str):
                _reject("invalid_text_block")
            projected.append({"type": "input_text", "text": typed["text"]})
            changed = changed or block_type == "output_text"
        elif block_type == "refusal":
            if set(typed) != {"type", "refusal"} or not isinstance(typed.get("refusal"), str):
                _reject("invalid_refusal_block")
            projected.append({"type": "input_text", "text": typed["refusal"]})
            changed = True
        elif block_type == "encrypted_content":
            encrypted += 1
            changed = True
        elif block_type == "input_image" and allow_images:
            allowed = {"type", "image_url", "detail"}
            if set(typed) - allowed:
                _reject("invalid_image_block")
            if not _is_replayable_remote_image_url(typed.get("image_url")):
                local_images += 1
                changed = True
                continue
            image = {"type": "input_image", "image_url": typed["image_url"]}
            detail = typed.get("detail")
            if detail is not None:
                if detail not in ("low", "high", "auto", "original"):
                    _reject("invalid_image_detail")
                image["detail"] = detail
            projected.append(image)
        else:
            _reject("unknown_content_type")

    markers = 0
    if not projected and encrypted and encrypted_marker:
        projected.append({"type": "input_text", "text": OPAQUE_CONTENT_MARKER})
        markers = 1
    if not projected:
        _reject("empty_portable_content")
    return projected, changed, encrypted, markers, local_images


def _project_message(item: JsonObject) -> tuple[JsonObject, dict[str, int]]:
    _unknown_fields(item, _MESSAGE_FIELDS, "unknown_message_field")
    role = item.get("role")
    phase = item.get("phase")
    if role not in _VALID_ROLES:
        _reject("invalid_message_role")
    if phase is not None and (role != "assistant" or phase not in _VALID_PHASES):
        _reject("invalid_message_phase")
    content, changed, encrypted, markers, local_images = _project_content(
        item.get("content"), allow_images=True, encrypted_marker=False
    )
    projected: JsonObject = {"type": "message", "role": role, "content": content}
    if phase is not None:
        projected["phase"] = phase
    return projected, {
        "changed": int(changed or projected != item),
        "item_ids": int("id" in item),
        "encrypted_blocks": encrypted,
        "omission_markers": markers,
        "local_image_items": local_images,
    }


def _project_agent_message(item: JsonObject) -> tuple[JsonObject, dict[str, int]]:
    _unknown_fields(item, _AGENT_FIELDS, "unknown_agent_message_field")
    author, recipient = item.get("author"), item.get("recipient")
    phase = item.get("phase", "commentary")
    if not all(isinstance(value, str) and value for value in (author, recipient)):
        _reject("invalid_agent_message")
    if phase not in _VALID_PHASES:
        _reject("invalid_agent_phase")
    content, _changed, encrypted, markers, local_images = _project_content(
        item.get("content"), allow_images=False, encrypted_marker=True
    )
    assert isinstance(content, list)
    root_ciphertext = int(isinstance(item.get("encrypted_content"), str))
    header = json.dumps(
        {"type": "agent_message", "author": author, "recipient": recipient},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "type": "message",
        "role": "assistant",
        "phase": phase,
        "content": [{"type": "input_text", "text": header}, *content],
    }, {
        "changed": 1,
        "item_ids": int("id" in item),
        "encrypted_blocks": encrypted + root_ciphertext,
        "omission_markers": markers,
        "local_image_items": local_images,
    }


def _project_call(item: JsonObject, calls: dict[str, str]) -> tuple[JsonObject, dict[str, int]]:
    item_type = cast(str, item.get("type"))
    _unknown_fields(item, _CALL_FIELDS[item_type], "unknown_call_field")
    call_id, name = item.get("call_id"), item.get("name")
    argument_field = _CALL_ARGUMENT_FIELD[item_type]
    argument = item.get(argument_field)
    namespace, caller = item.get("namespace"), item.get("caller")
    if not isinstance(call_id, str) or not call_id or call_id in calls:
        _reject("invalid_call_id")
    valid_call_id = cast(str, call_id)
    if not isinstance(name, str) or not name or not isinstance(argument, str):
        _reject("invalid_call")
    if namespace is not None and (not isinstance(namespace, str) or not namespace):
        _reject("invalid_namespace")
    if not _valid_caller(caller):
        _reject("invalid_caller")
    calls[valid_call_id] = item_type
    projected: JsonObject = {
        "type": item_type,
        "call_id": valid_call_id,
        "name": name,
        argument_field: argument,
    }
    if namespace is not None:
        projected["namespace"] = namespace
    if caller is not None:
        projected["caller"] = caller
    return projected, {
        "changed": int(projected != item),
        "item_ids": int("id" in item),
        "encrypted_blocks": 0,
        "omission_markers": 0,
        "local_image_items": 0,
    }


def _project_output(
    item: JsonObject,
    calls: dict[str, str],
    outputs: set[str],
) -> tuple[JsonObject, dict[str, int]]:
    item_type = cast(str, item.get("type"))
    _unknown_fields(item, _OUTPUT_FIELDS, "unknown_output_field")
    call_id, caller = item.get("call_id"), item.get("caller")
    if not isinstance(call_id, str) or not call_id or call_id not in calls:
        _reject("orphan_output")
    valid_call_id = cast(str, call_id)
    if calls[valid_call_id] != _OUTPUT_CALL_TYPE[item_type]:
        _reject("mismatched_output")
    if valid_call_id in outputs:
        _reject("duplicate_output")
    if not _valid_caller(caller):
        _reject("invalid_caller")
    raw_output = item.get("output")
    root_ciphertext = int(isinstance(item.get("encrypted_content"), str))
    if raw_output is None and root_ciphertext:
        output: object = [{"type": "input_text", "text": OPAQUE_CONTENT_MARKER}]
        changed, encrypted, markers = True, root_ciphertext, 1
    else:
        output, changed, encrypted, markers, local_images = _project_content(
            raw_output, allow_images=True, encrypted_marker=True
        )
        encrypted += root_ciphertext
    if raw_output is None and root_ciphertext:
        local_images = 0
    outputs.add(valid_call_id)
    projected: JsonObject = {"type": item_type, "call_id": valid_call_id, "output": output}
    if caller is not None:
        projected["caller"] = caller
    return projected, {
        "changed": int(changed or projected != item),
        "item_ids": int("id" in item),
        "encrypted_blocks": encrypted,
        "omission_markers": markers,
        "local_image_items": local_images,
    }


def _project_input(items: list[object]) -> tuple[list[object], dict[str, int]]:
    calls: dict[str, str] = {}
    outputs: set[str] = set()
    projected: list[object] = []
    metrics = {
        "reasoning_items": 0,
        "reference_items": 0,
        "search_items": 0,
        "item_ids": 0,
        "encrypted_blocks": 0,
        "omission_markers": 0,
        "local_image_items": 0,
        "changed_items": 0,
    }
    for raw_item in items:
        if not isinstance(raw_item, dict):
            _reject("invalid_item")
        item = cast(JsonObject, raw_item)
        item_type = item.get("type")
        if item_type in _DROP_ITEM_TYPES:
            metrics["reasoning_items"] += int(item_type == "reasoning")
            metrics["reference_items"] += int(item_type in ("item_reference", "compaction"))
            metrics["search_items"] += int(item_type in _SEARCH_ITEM_TYPES)
            metrics["item_ids"] += int("id" in item)
            continue
        if item_type == "message":
            value, item_metrics = _project_message(item)
        elif item_type == "agent_message":
            value, item_metrics = _project_agent_message(item)
        elif item_type in _CALL_ARGUMENT_FIELD:
            value, item_metrics = _project_call(item, calls)
        elif item_type in _OUTPUT_CALL_TYPE:
            value, item_metrics = _project_output(item, calls, outputs)
        else:
            _reject("unknown_item_type")
        projected.append(value)
        for key, value_count in item_metrics.items():
            metrics["changed_items" if key == "changed" else key] += value_count
    if not projected and items:
        _reject("empty_portable_input")
    return projected, metrics


def sanitize_responses_body(raw: bytes) -> tuple[bytes | None, str]:
    """Return portable request bytes or one bounded fail-closed reason."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "rejected invalid_json"
    if not isinstance(payload, dict):
        return None, "rejected request_not_object"

    candidate = cast(JsonObject, dict(payload))
    provider_bindings = sum(field in candidate for field in _PROVIDER_BINDINGS)
    for field in _PROVIDER_BINDINGS:
        candidate.pop(field, None)

    include_trimmed = False
    include = candidate.get("include")
    if include is not None:
        if not isinstance(include, list) or any(not isinstance(value, str) for value in include):
            return None, "rejected invalid_include"
        trimmed = [value for value in include if value != "reasoning.encrypted_content"]
        include_trimmed = len(trimmed) != len(include)
        candidate["include"] = trimmed

    raw_input = candidate.get("input")
    metrics = {
        "reasoning_items": 0,
        "reference_items": 0,
        "search_items": 0,
        "item_ids": 0,
        "encrypted_blocks": 0,
        "omission_markers": 0,
        "local_image_items": 0,
        "changed_items": 0,
    }
    try:
        if isinstance(raw_input, str):
            if not raw_input:
                _reject("empty_input")
        elif isinstance(raw_input, list):
            candidate["input"], metrics = _project_input(cast("list[object]", raw_input))
        else:
            _reject("invalid_input")
    except (ProjectionRejected, RecursionError) as exc:
        reason = "projection_depth_exceeded" if isinstance(exc, RecursionError) else str(exc)
        return None, f"rejected {reason}"

    changed = bool(
        provider_bindings or include_trimmed or any(metrics.values()) or candidate != payload
    )
    if not changed:
        return raw, "clean portable_replay"
    try:
        encoded = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return None, "rejected serialization_failed"
    return encoded, (
        f"projected provider_bindings={provider_bindings} "
        f"reasoning_items={metrics['reasoning_items']} "
        f"reference_items={metrics['reference_items']} "
        f"search_items={metrics['search_items']} "
        f"item_ids={metrics['item_ids']} "
        f"encrypted_blocks={metrics['encrypted_blocks']} "
        f"omission_markers={metrics['omission_markers']} "
        f"local_image_items={metrics['local_image_items']} "
        f"include_trimmed={include_trimmed}"
    )


def _strip_encrypted_blocks(item: JsonObject, field: str) -> int:
    value = item.get(field)
    if not isinstance(value, list):
        return 0
    kept = [
        block
        for block in value
        if not (isinstance(block, dict) and block.get("type") == "encrypted_content")
    ]
    removed = len(value) - len(kept)
    if removed:
        item[field] = kept or [{"type": "input_text", "text": OPAQUE_CONTENT_MARKER}]
    return removed


def _strip_provider_ciphertext(obj: object) -> int:
    removed = 0
    if isinstance(obj, dict):
        item = cast(JsonObject, obj)
        item_type = item.get("type")
        if item_type == "reasoning" and "encrypted_content" in item:
            del item["encrypted_content"]
            removed += 1
        if item_type == "agent_message":
            removed += _strip_encrypted_blocks(item, "content")
            if "encrypted_content" in item:
                del item["encrypted_content"]
                removed += 1
        if item_type in _OUTPUT_CALL_TYPE:
            removed += _strip_encrypted_blocks(item, "output")
            if "encrypted_content" in item:
                del item["encrypted_content"]
                removed += 1
        for value in tuple(item.values()):
            removed += _strip_provider_ciphertext(value)
    elif isinstance(obj, list):
        for value in obj:
            removed += _strip_provider_ciphertext(value)
    return removed


def sanitize_sse_event(raw_event: bytes) -> tuple[bytes, int]:
    """Remove provider ciphertext atomically from one complete SSE event."""
    if b"encrypted_content" not in raw_event:
        return raw_event, 0

    out_lines: list[bytes] = []
    removed_total = 0
    for line in raw_event.splitlines(keepends=True):
        if line.startswith(b"data: "):
            prefix = b"data: "
            suffix = b"\n" if line.endswith(b"\n") else b""
            data = line[len(prefix) : -1] if suffix else line[len(prefix) :]
            try:
                obj = json.loads(data)
                removed = _strip_provider_ciphertext(obj)
                if removed:
                    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
                    line = prefix + data + suffix
                    removed_total += removed
            except (TypeError, ValueError, RecursionError, UnicodeError):
                return raw_event, 0
        out_lines.append(line)
    return b"".join(out_lines), removed_total
