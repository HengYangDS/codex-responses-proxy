"""Bounded compatibility policy for Responses ``input`` validation failures.

This module owns the only recovery admitted for the observed third-party
``validation_error`` contract.  It is pure request policy: no network, process,
logging, metrics, or conversation storage access belongs here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final
from typing import Mapping
from typing import cast

type JsonObject = dict[str, object]
type ReadOnlyJsonObject = Mapping[str, object]

_ERROR_MESSAGE: Final = (
    "invalid request body: Invalid 'input': value did not match any expected variant"
)
_KNOWN_ITEM_TYPES: Final = frozenset(
    {
        "message",
        "agent_message",
        "reasoning",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "web_search_call",
        "tool_search_call",
        "tool_search_output",
        "file_search_call",
        "computer_call",
        "computer_call_output",
        "code_interpreter_call",
        "image_generation_call",
        "local_shell_call",
        "local_shell_call_output",
        "shell_call",
        "shell_call_output",
        "apply_patch_call",
        "apply_patch_call_output",
        "mcp_list_tools",
        "mcp_approval_request",
        "mcp_approval_response",
        "mcp_call",
        "compaction",
        "compaction_trigger",
        "item_reference",
        "additional_tools",
        "program",
        "program_output",
    }
)
_KNOWN_CONTENT_TYPES: Final = frozenset(
    {
        "input_text",
        "output_text",
        "input_image",
        "input_file",
        "input_audio",
        "refusal",
        "encrypted_content",
    }
)
_PAIR_TYPES: Final = {
    "custom_tool_call": "custom_tool_call_output",
    "function_call": "function_call_output",
    "tool_search_call": "tool_search_output",
}
_CALL_TYPES: Final = frozenset(_PAIR_TYPES)
_OUTPUT_TYPES: Final = frozenset(_PAIR_TYPES.values())
_ROLES: Final = ("system", "developer", "user")


@dataclass(frozen=True, slots=True)
class InputDiagnostic:
    """Content-free structural facts about one rejected Responses input."""

    input_items_bucket: str
    item_types: dict[str, str]
    content_types: dict[str, str]
    matched_pairs: bool
    unmatched_calls: bool
    unmatched_outputs: bool
    outputs_before_calls: bool
    duplicate_calls: bool
    duplicate_outputs: bool
    missing_call_ids: bool
    mismatched_output_types: bool
    first_incompatible_reason: str
    shape_sha256: str

    def log_fragment(self) -> str:
        """Render a bounded value-free fragment for the structured runtime log."""

        def counts(values: dict[str, str]) -> str:
            return ",".join(f"{key}:{values[key]}" for key in sorted(values)) or "-"

        rendered = (
            f"input_items_bucket={self.input_items_bucket} "
            f"item_types={counts(self.item_types)} "
            f"content_types={counts(self.content_types)} "
            f"matched_pairs={_presence(self.matched_pairs)} "
            f"unmatched_calls={_presence(self.unmatched_calls)} "
            f"unmatched_outputs={_presence(self.unmatched_outputs)} "
            f"outputs_before_calls={_presence(self.outputs_before_calls)} "
            f"duplicate_calls={_presence(self.duplicate_calls)} "
            f"duplicate_outputs={_presence(self.duplicate_outputs)} "
            f"missing_call_ids={_presence(self.missing_call_ids)} "
            f"mismatched_output_types={_presence(self.mismatched_output_types)} "
            f"first_incompatible_reason={self.first_incompatible_reason or '-'} "
            f"shape_sha256={self.shape_sha256}"
        )
        return rendered.encode()[:768].decode(errors="ignore")


@dataclass(frozen=True, slots=True)
class RecoveryMetrics:
    """Non-content facts proving that a recovery request is materially smaller."""

    original_bytes: int
    recovery_bytes: int
    retained_messages: int
    dropped_input_items: int
    provider_bindings_removed: int
    reasoning_include_removed: bool
    prompt_cache_key_removed: bool


def is_exact_validation_error(status_code: int, error_body: bytes) -> bool:
    """Return whether an upstream response is the complete observed error contract."""

    if status_code != 400:
        return False
    try:
        payload = json.loads(error_body)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    return isinstance(error, dict) and error == {
        "message": _ERROR_MESSAGE,
        "type": "invalid_request_error",
        "param": "",
        "code": "validation_error",
    }


def diagnose(raw: bytes) -> InputDiagnostic:
    """Describe request structure without retaining values or high-cardinality sizes."""

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _diagnostic(first_reason="invalid_json", shape="invalid-json")
    shape = _shape(payload)
    shape_sha256 = hashlib.sha256(
        json.dumps(shape, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not isinstance(payload, dict):
        return _diagnostic(first_reason="request_not_object", shape=shape_sha256)
    items = payload.get("input")
    if not isinstance(items, list):
        return _diagnostic(first_reason="input_not_list", shape=shape_sha256)
    return _diagnose_items(items, shape_sha256)


def diagnostic_dict(diagnostic: InputDiagnostic) -> dict[str, object]:
    """Project an immutable diagnostic to the stable runtime mapping contract."""

    return {
        "input_items_bucket": diagnostic.input_items_bucket,
        "item_types": dict(diagnostic.item_types),
        "content_types": dict(diagnostic.content_types),
        "matched_pairs": diagnostic.matched_pairs,
        "unmatched_calls": diagnostic.unmatched_calls,
        "unmatched_outputs": diagnostic.unmatched_outputs,
        "outputs_before_calls": diagnostic.outputs_before_calls,
        "duplicate_calls": diagnostic.duplicate_calls,
        "duplicate_outputs": diagnostic.duplicate_outputs,
        "missing_call_ids": diagnostic.missing_call_ids,
        "mismatched_output_types": diagnostic.mismatched_output_types,
        "first_incompatible_reason": diagnostic.first_incompatible_reason,
        "shape_sha256": diagnostic.shape_sha256,
    }


def format_diagnostic(diagnostic: InputDiagnostic | dict[str, object]) -> str:
    """Render either the policy value or its stable mapping projection."""

    if isinstance(diagnostic, InputDiagnostic):
        return diagnostic.log_fragment()
    item = InputDiagnostic(
        input_items_bucket=_size_bucket_value(diagnostic.get("input_items_bucket")),
        item_types=_bucket_counts(diagnostic.get("item_types")),
        content_types=_bucket_counts(diagnostic.get("content_types")),
        matched_pairs=_presence_value(diagnostic.get("matched_pairs")),
        unmatched_calls=_presence_value(diagnostic.get("unmatched_calls")),
        unmatched_outputs=_presence_value(diagnostic.get("unmatched_outputs")),
        outputs_before_calls=_presence_value(diagnostic.get("outputs_before_calls")),
        duplicate_calls=_presence_value(diagnostic.get("duplicate_calls")),
        duplicate_outputs=_presence_value(diagnostic.get("duplicate_outputs")),
        missing_call_ids=_presence_value(diagnostic.get("missing_call_ids")),
        mismatched_output_types=_presence_value(diagnostic.get("mismatched_output_types")),
        first_incompatible_reason=str(diagnostic.get("first_incompatible_reason", "")),
        shape_sha256=str(diagnostic.get("shape_sha256", "-")),
    )
    return item.log_fragment()


def structure_shape(value: object, depth: int = 0) -> object:
    """Expose the bounded categorical shape for deterministic policy tests."""

    return _shape(value, depth)


def build_recovery(raw: bytes, budget: int) -> tuple[bytes | None, RecoveryMetrics | None]:
    """Build one instructions-plus-current-dialogue request, or reject safely."""

    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        return None, None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or not original_items:
        return None, None
    dialogue = _current_dialogue(original_items)
    if dialogue is None:
        return None, None
    candidate = dict(payload)
    candidate["input"] = dialogue
    removed_bindings = sum(key in candidate for key in _PROVIDER_BINDINGS)
    for key in _PROVIDER_BINDINGS:
        candidate.pop(key, None)
    include_removed = _remove_reasoning_include(candidate)
    try:
        recovery = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return None, None
    dropped_items = len(original_items) - len(dialogue)
    materially_changed = dropped_items > 0 or removed_bindings > 0 or include_removed
    if not materially_changed or len(recovery) > budget or len(recovery) >= len(raw):
        return None, None
    return recovery, RecoveryMetrics(
        original_bytes=len(raw),
        recovery_bytes=len(recovery),
        retained_messages=len(dialogue),
        dropped_input_items=dropped_items,
        provider_bindings_removed=removed_bindings,
        reasoning_include_removed=include_removed,
        prompt_cache_key_removed="prompt_cache_key" in payload,
    )


_PROVIDER_BINDINGS: Final = ("previous_response_id", "conversation", "prompt_cache_key")


def _current_dialogue(items: list[object]) -> list[JsonObject] | None:
    indexes: list[int] = []
    for role in _ROLES:
        candidates = [
            index
            for index, item in enumerate(items)
            if isinstance(item, dict)
            and cast(ReadOnlyJsonObject, item).get("type") == "message"
            and cast(ReadOnlyJsonObject, item).get("role") == role
        ]
        if candidates:
            indexes.append(candidates[-1])
        elif role == "user":
            return None
    dialogue: list[JsonObject] = []
    for index in sorted(indexes):
        item = items[index]
        if not isinstance(item, dict):
            return None
        typed_item = cast(ReadOnlyJsonObject, item)
        content = _text_content(typed_item.get("content"))
        role = typed_item.get("role")
        if content is None or not isinstance(role, str):
            return None
        dialogue.append({"type": "message", "role": role, "content": content})
    return dialogue


def _text_content(value: object) -> str | list[JsonObject] | None:
    if isinstance(value, str) and value:
        return value
    if not isinstance(value, list):
        return None
    projected: list[JsonObject] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        typed_block = cast(ReadOnlyJsonObject, block)
        if typed_block.get("type") not in {"input_text", "output_text"}:
            continue
        text = typed_block.get("text")
        if isinstance(text, str) and text:
            projected.append({"type": "input_text", "text": text})
    return projected or None


def _remove_reasoning_include(candidate: JsonObject) -> bool:
    include = candidate.get("include")
    if not isinstance(include, list):
        return False
    filtered = [value for value in include if value != "reasoning.encrypted_content"]
    candidate["include"] = filtered
    return len(filtered) != len(include)


def _shape(value: object, depth: int = 0) -> object:
    """Return a capped categorical shape; cardinalities and unknown names are erased."""

    if depth >= 6:
        return {"kind": "truncated", "type": _value_kind(value)}
    if isinstance(value, dict):
        entries: set[str] = set()
        known_fields = 0
        for key, item in value.items():
            if key == "type":
                known_fields += 1
                entry: object = (
                    "type",
                    _closed_label(item, _KNOWN_ITEM_TYPES | _KNOWN_CONTENT_TYPES),
                )
            elif key == "role":
                known_fields += 1
                entry = ("role", item if item in (*_ROLES, "assistant") else "unknown")
            else:
                entry = ("field", _shape(item, depth + 1))
            entries.add(json.dumps(entry, sort_keys=True, separators=(",", ":")))
        unknown_fields = len(value) - known_fields
        return {
            "kind": "dict",
            "known_fields": _size_bucket(known_fields),
            "unknown_fields": _presence(unknown_fields > 0),
            "items": [json.loads(entry) for entry in sorted(entries)[:32]],
            "truncated": _presence(len(entries) > 32),
        }
    if isinstance(value, list):
        entries = {
            json.dumps(_shape(item, depth + 1), sort_keys=True, separators=(",", ":"))
            for item in value
        }
        return {
            "kind": "list",
            "size": _size_bucket(len(value)),
            "items": [json.loads(entry) for entry in sorted(entries)[:32]],
            "truncated": _presence(len(entries) > 32),
        }
    return _value_kind(value)


def _closed_label(value: object, known: frozenset[str]) -> str:
    if not isinstance(value, str):
        return _value_kind(value)
    return value if value in known else "unknown"


def _value_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "other"


def _size_bucket(size: int) -> str:
    if size == 0:
        return "0"
    if size == 1:
        return "1"
    if size <= 4:
        return "2-4"
    if size <= 16:
        return "5-16"
    return "17+"


def _bucketed_counts(values: dict[str, int]) -> dict[str, str]:
    return {key: _size_bucket(count) for key, count in values.items()}


def _presence(value: bool) -> str:
    return "present" if value else "absent"


def _diagnostic(*, first_reason: str, shape: str) -> InputDiagnostic:
    return InputDiagnostic(
        input_items_bucket="0",
        item_types={},
        content_types={},
        matched_pairs=False,
        unmatched_calls=False,
        unmatched_outputs=False,
        outputs_before_calls=False,
        duplicate_calls=False,
        duplicate_outputs=False,
        missing_call_ids=False,
        mismatched_output_types=False,
        first_incompatible_reason=first_reason,
        shape_sha256=shape,
    )


def _diagnose_items(items: list[object], shape_sha256: str) -> InputDiagnostic:
    state = _DiagnosticState(shape_sha256=shape_sha256, input_items=len(items))
    for index, item in enumerate(items):
        state.observe(index, item)
    return state.finish()


class _DiagnosticState:
    """Mutable reducer used only while constructing an immutable diagnostic."""

    def __init__(self, *, shape_sha256: str, input_items: int) -> None:
        self.shape_sha256 = shape_sha256
        self.input_items = input_items
        self.item_types: dict[str, int] = {}
        self.content_types: dict[str, int] = {}
        self.calls: dict[str, tuple[int, str]] = {}
        self.outputs: dict[str, tuple[int, str]] = {}
        self.matched_pairs = 0
        self.outputs_before_calls = 0
        self.duplicate_calls = 0
        self.duplicate_outputs = 0
        self.missing_call_ids = 0
        self.mismatched_output_types = 0
        self.first_index: int | None = None
        self.first_reason = ""

    def observe(self, index: int, item: object) -> None:
        if not isinstance(item, dict):
            self._fail(index, "item_not_object")
            self._count(self.item_types, _value_kind(item))
            return
        typed_item = cast(ReadOnlyJsonObject, item)
        raw_type = typed_item.get("type")
        item_type = _closed_label(raw_type, _KNOWN_ITEM_TYPES)
        if not isinstance(raw_type, str):
            self._fail(index, "missing_item_type")
        elif raw_type not in _KNOWN_ITEM_TYPES:
            self._fail(index, "unknown_item_type")
        self._count(self.item_types, item_type)
        self._validate_item(index, typed_item, raw_type)
        self._observe_content(index, typed_item.get("content"))
        self._observe_pair(index, typed_item, raw_type)

    def _validate_item(self, index: int, item: ReadOnlyJsonObject, item_type: object) -> None:
        if not isinstance(item_type, str):
            return
        if item_type == "message":
            if item.get("role") not in (*_ROLES, "assistant"):
                self._fail(index, "invalid_message_role")
            content = item.get("content")
            if not isinstance(content, (str, list)):
                self._fail(index, "invalid_message_content")
            elif isinstance(content, list) and not content:
                self._fail(index, "empty_message_content")
        elif item_type == "function_call" and not _strings_present(
            item, ("call_id", "name", "arguments")
        ):
            self._fail(index, "invalid_function_call")
        elif item_type == "custom_tool_call" and not _strings_present(
            item, ("call_id", "name", "input")
        ):
            self._fail(index, "invalid_custom_tool_call")
        elif item_type == "tool_search_call" and not isinstance(item.get("arguments"), dict):
            self._fail(index, "invalid_tool_search_call")
        elif item_type == "tool_search_output" and not isinstance(item.get("tools"), list):
            self._fail(index, "invalid_tool_search_output")
        elif (
            item_type in _OUTPUT_TYPES
            and item_type != "tool_search_output"
            and not isinstance(item.get("output"), (str, list))
        ):
            self._fail(index, "invalid_tool_output")

    def _observe_content(self, index: int, content: object) -> None:
        if isinstance(content, str):
            self._count(self.content_types, "string")
            return
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                self._count(self.content_types, _value_kind(block))
                self._fail(index, "invalid_content_block")
                continue
            typed_block = cast(ReadOnlyJsonObject, block)
            block_type = typed_block.get("type")
            self._count(self.content_types, _closed_label(block_type, _KNOWN_CONTENT_TYPES))
            if not isinstance(block_type, str) or block_type not in _KNOWN_CONTENT_TYPES:
                self._fail(index, "unknown_content_type")
            elif block_type in {"input_text", "output_text"} and not isinstance(
                typed_block.get("text"), str
            ):
                self._fail(index, "invalid_input_text_block")
            elif block_type == "encrypted_content" and not isinstance(
                typed_block.get("encrypted_content"), str
            ):
                self._fail(index, "malformed_encrypted_content_block")
            elif block_type == "input_image" and not _valid_image(typed_block):
                self._fail(index, "invalid_input_image_block")

    def _observe_pair(self, index: int, item: ReadOnlyJsonObject, item_type: object) -> None:
        if not isinstance(item_type, str):
            return
        if item_type not in _CALL_TYPES | _OUTPUT_TYPES:
            return
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            self.missing_call_ids += 1
            self._fail(index, "missing_call_id")
            return
        if item_type in _CALL_TYPES:
            count, _ = self.calls.get(call_id, (0, str(item_type)))
            self.calls[call_id] = (count + 1, str(item_type))
            if count:
                self.duplicate_calls += 1
                self._fail(index, "duplicate_call")
            return
        count, _ = self.outputs.get(call_id, (0, str(item_type)))
        self.outputs[call_id] = (count + 1, str(item_type))
        if call_id not in self.calls:
            self.outputs_before_calls += 1
            self._fail(index, "output_before_call")
        else:
            expected = _PAIR_TYPES[self.calls[call_id][1]]
            if expected != item_type:
                self.mismatched_output_types += 1
                self._fail(index, "mismatched_output_type")
            elif count == 0:
                self.matched_pairs += 1
        if count:
            self.duplicate_outputs += 1
            self._fail(index, "duplicate_output")

    def _fail(self, index: int, reason: str) -> None:
        if self.first_index is None:
            self.first_index = index
            self.first_reason = reason

    @staticmethod
    def _count(target: dict[str, int], key: str) -> None:
        target[key] = target.get(key, 0) + 1

    def finish(self) -> InputDiagnostic:
        call_ids = set(self.calls)
        output_ids = set(self.outputs)
        return InputDiagnostic(
            input_items_bucket=_size_bucket(self.input_items),
            item_types=_bucketed_counts(self.item_types),
            content_types=_bucketed_counts(self.content_types),
            matched_pairs=bool(self.matched_pairs),
            unmatched_calls=any(call_id not in output_ids for call_id in call_ids),
            unmatched_outputs=any(call_id not in call_ids for call_id in output_ids),
            outputs_before_calls=bool(self.outputs_before_calls),
            duplicate_calls=bool(self.duplicate_calls),
            duplicate_outputs=bool(self.duplicate_outputs),
            missing_call_ids=bool(self.missing_call_ids),
            mismatched_output_types=bool(self.mismatched_output_types),
            first_incompatible_reason=self.first_reason,
            shape_sha256=self.shape_sha256,
        )


def _strings_present(item: ReadOnlyJsonObject, fields: tuple[str, ...]) -> bool:
    return all(isinstance(item.get(field), str) and bool(item.get(field)) for field in fields)


def _valid_image(block: ReadOnlyJsonObject) -> bool:
    return block.get("detail") in {"low", "high", "auto", "original"} and (
        isinstance(block.get("image_url"), str) or isinstance(block.get("file_id"), str)
    )


def _bucket_counts(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    typed_value = cast(ReadOnlyJsonObject, value)
    return {
        key: cast(str, bucket)
        for key, bucket in typed_value.items()
        if isinstance(key, str) and bucket in {"0", "1", "2-4", "5-16", "17+"}
    }


def _size_bucket_value(value: object) -> str:
    return cast(str, value) if value in {"0", "1", "2-4", "5-16", "17+"} else "0"


def _presence_value(value: object) -> bool:
    return value is True
