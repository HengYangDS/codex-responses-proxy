"""Bounded compatibility policy for Responses ``input`` validation failures.

This module owns the only recovery admitted for the observed third-party
``validation_error`` contract.  It is pure request policy: no network, process,
logging, metrics, or conversation storage access belongs here.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence, Set
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import Final, Mapping, cast

type JsonObject = dict[str, object]
type ReadOnlyJsonObject = Mapping[str, object]

_ERROR_MESSAGE: Final = (
    "invalid request body: Invalid 'input': value did not match any expected variant"
)
_INVALID_JSON: Final = object()
_KNOWN_ITEM_TYPES: Final = frozenset(
    """message agent_message reasoning function_call function_call_output
    custom_tool_call custom_tool_call_output web_search_call tool_search_call
    tool_search_output file_search_call computer_call computer_call_output
    code_interpreter_call image_generation_call local_shell_call local_shell_call_output
    shell_call shell_call_output apply_patch_call apply_patch_call_output mcp_list_tools
    mcp_approval_request mcp_approval_response mcp_call compaction compaction_trigger
    item_reference additional_tools program program_output""".split()
)
_KNOWN_CONTENT_TYPES: Final = frozenset(
    "input_text output_text input_image input_file input_audio refusal encrypted_content".split()
)
_PAIR_TYPES: Final = {
    "custom_tool_call": "custom_tool_call_output",
    "function_call": "function_call_output",
    "tool_search_call": "tool_search_output",
}
_CALL_TYPES: Final = frozenset(_PAIR_TYPES)
_OUTPUT_TYPES: Final = frozenset(_PAIR_TYPES.values())
_ROLES: Final = ("system", "developer", "user")
_VALUE_KINDS: Final = {
    type(None): "null",
    bool: "bool",
    str: "str",
    int: "number",
    float: "number",
    list: "list",
    dict: "dict",
}
_SIZE_BUCKETS: Final = ((0, "0"), (1, "1"), (4, "2-4"), (16, "5-16"))
_TEXT_CONTENT_TYPES: Final = frozenset(("input_text", "output_text"))
_BUCKETS: Final = frozenset(("0", "1", "2-4", "5-16", "17+"))
_REQUIRED_STRING_FIELDS: Final = {
    "function_call": ("call_id", "name", "arguments"),
    "custom_tool_call": ("call_id", "name", "input"),
}
_CONTENT_VALUE_FIELDS: Final = {
    "input_text": ("text", "invalid_input_text_block"),
    "output_text": ("text", "invalid_input_text_block"),
    "encrypted_content": ("encrypted_content", "malformed_encrypted_content_block"),
}
_ITEM_VALUE_FIELDS: Final = {
    "tool_search_call": ("arguments", dict, "invalid_tool_search_call"),
    "tool_search_output": ("tools", list, "invalid_tool_search_output"),
}


@dataclass(frozen=True, slots=True)
class InputDiagnostic:
    """Content-free structural facts about one rejected Responses input."""

    input_items_bucket: str = "0"
    item_types: dict[str, str] = field(default_factory=dict)
    content_types: dict[str, str] = field(default_factory=dict)
    matched_pairs: bool = False
    unmatched_calls: bool = False
    unmatched_outputs: bool = False
    outputs_before_calls: bool = False
    duplicate_calls: bool = False
    duplicate_outputs: bool = False
    missing_call_ids: bool = False
    mismatched_output_types: bool = False
    first_incompatible_reason: str = ""
    shape_sha256: str = "invalid-json"


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

    payload = _load_json(error_body)
    error = payload.get("error") if isinstance(payload, dict) else None
    return status_code == 400 and error == {
        "message": _ERROR_MESSAGE,
        "type": "invalid_request_error",
        "param": "",
        "code": "validation_error",
    }


def diagnose(raw: bytes) -> InputDiagnostic:
    """Describe request structure without retaining values or high-cardinality sizes."""

    payload = _load_json(raw)
    if payload is _INVALID_JSON:
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


def _load_json(raw: bytes) -> object:
    payload: object = _INVALID_JSON
    with suppress(TypeError, ValueError, json.JSONDecodeError):
        payload = json.loads(raw)
    return payload


def diagnostic_dict(diagnostic: InputDiagnostic) -> dict[str, object]:
    """Project an immutable diagnostic to the stable runtime mapping contract."""

    return asdict(diagnostic)


def format_diagnostic(diagnostic: InputDiagnostic | dict[str, object]) -> str:
    """Render a bounded, content-free diagnostic fragment."""

    values = asdict(diagnostic) if isinstance(diagnostic, InputDiagnostic) else diagnostic
    fields: dict[str, object] = {
        "input_items_bucket": _size_bucket_value(values.get("input_items_bucket")),
        "item_types": _format_counts(_bucket_counts(values.get("item_types"))),
        "content_types": _format_counts(_bucket_counts(values.get("content_types"))),
        **{key: _presence(values.get(key) is True) for key in _DIAGNOSTIC_FLAGS},
        "first_incompatible_reason": str(values.get("first_incompatible_reason", "")) or "-",
        "shape_sha256": str(values.get("shape_sha256", "-")),
    }
    return " ".join(f"{key}={value}" for key, value in fields.items())[:768]


def build_recovery(raw: bytes, budget: int) -> tuple[bytes | None, RecoveryMetrics | None]:
    """Build one instructions-plus-current-dialogue request, or reject safely."""

    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        return None, None
    payload = _load_json(raw)
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
    candidate["store"] = False
    removed_bindings = sum(key in candidate for key in _PROVIDER_BINDINGS)
    for key in _PROVIDER_BINDINGS:
        candidate.pop(key, None)
    include_removed = _remove_reasoning_include(candidate)
    try:
        recovery = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
    except (TypeError, ValueError, RecursionError, UnicodeError):
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
_DIAGNOSTIC_FLAGS: Final = (
    "matched_pairs",
    "unmatched_calls",
    "unmatched_outputs",
    "outputs_before_calls",
    "duplicate_calls",
    "duplicate_outputs",
    "missing_call_ids",
    "mismatched_output_types",
)


def _current_dialogue(items: Sequence[object]) -> list[JsonObject] | None:
    latest: dict[str, int] = {}
    for index, item in enumerate(items):
        match item:
            case {"type": "message", "role": str(role)} if role in _ROLES:
                latest[role] = index
    if "user" not in latest:
        return None
    dialogue: list[JsonObject] = []
    for index in sorted(latest.values()):
        item = items[index]
        match item:
            case {"role": str(role), "content": value} if content := _text_content(value):
                dialogue.append({"type": "message", "role": role, "content": content})
            case _:
                return None
    return dialogue


def _text_content(value: object) -> str | list[JsonObject] | None:
    match value:
        case str() if value:
            return value
        case list():
            projected: list[JsonObject] = [
                {"type": "input_text", "text": text}
                for block in value
                if isinstance(block, dict)
                and block.get("type") in _TEXT_CONTENT_TYPES
                and isinstance((text := block.get("text")), str)
                and text
            ]
            return projected or None
        case _:
            return None


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
        return "truncated", _value_kind(value)
    if isinstance(value, list):
        items = {_shape(item, depth + 1) for item in value}
        return "list", _size_bucket(len(value)), _bounded(items)
    if not isinstance(value, dict):
        return _value_kind(value)
    entries: set[object] = set()
    for key, item in value.items():
        if key == "type":
            entry = "type", _closed_label(item, _KNOWN_ITEM_TYPES | _KNOWN_CONTENT_TYPES)
        elif key == "role":
            entry = "role", item if item in (*_ROLES, "assistant") else "unknown"
        else:
            entry = "field", _shape(item, depth + 1)
        entries.add(entry)
    known_fields = len(value.keys() & {"type", "role"})
    return (
        "dict",
        _size_bucket(known_fields),
        _presence(len(value) > known_fields),
        _bounded(entries),
    )


def _bounded(entries: Set[object]) -> tuple[tuple[object, ...], str]:
    ordered = tuple(sorted(entries, key=repr))
    return ordered[:32], _presence(len(ordered) > 32)


def _closed_label(value: object, known: frozenset[str]) -> str:
    return value if isinstance(value, str) and value in known else _unknown_label(value)


def _unknown_label(value: object) -> str:
    return "unknown" if isinstance(value, str) else _value_kind(value)


def _value_kind(value: object) -> str:
    return _VALUE_KINDS.get(type(value), "other")


def _size_bucket(size: int) -> str:
    return next((label for limit, label in _SIZE_BUCKETS if size <= limit), "17+")


def _bucketed_counts(values: dict[str, int]) -> dict[str, str]:
    return {key: _size_bucket(count) for key, count in values.items()}


def _format_counts(values: dict[str, str]) -> str:
    return ",".join(f"{key}:{values[key]}" for key in sorted(values)) or "-"


def _presence(value: bool) -> str:
    return "present" if value else "absent"


def _diagnostic(*, first_reason: str, shape: str) -> InputDiagnostic:
    return InputDiagnostic(first_incompatible_reason=first_reason, shape_sha256=shape)


def _diagnose_items(items: Sequence[object], shape_sha256: str) -> InputDiagnostic:
    state = _DiagnosticState(shape_sha256=shape_sha256, input_items=len(items))
    for item in items:
        state.observe(item)
    return state.finish()


class _DiagnosticState:
    """Reduce one rejected input to bounded structural evidence."""

    def __init__(self, *, shape_sha256: str, input_items: int) -> None:
        self.shape_sha256 = shape_sha256
        self.input_items = input_items
        self.item_types: Counter[str] = Counter()
        self.content_types: Counter[str] = Counter()
        self.calls: dict[str, str] = {}
        self.outputs: set[str] = set()
        self.flags: set[str] = set()
        self.first_reason = ""

    def observe(self, item: object) -> None:
        if not isinstance(item, dict):
            self._fail("item_not_object")
            self.item_types[_value_kind(item)] += 1
            return
        typed_item = cast(ReadOnlyJsonObject, item)
        raw_type = typed_item.get("type")
        self.item_types[_closed_label(raw_type, _KNOWN_ITEM_TYPES)] += 1
        self._fail(_item_type_failure(raw_type))
        self._fail(_item_failure(typed_item, raw_type))
        self._observe_content(typed_item.get("content"))
        self._observe_pair(typed_item, raw_type)

    def _observe_content(self, content: object) -> None:
        if isinstance(content, str):
            self.content_types["string"] += 1
        elif isinstance(content, list):
            for block in content:
                self._observe_block(block)

    def _observe_block(self, block: object) -> None:
        if not isinstance(block, dict):
            self.content_types[_value_kind(block)] += 1
            self._fail("invalid_content_block")
            return
        typed_block = cast(ReadOnlyJsonObject, block)
        block_type = typed_block.get("type")
        self.content_types[_closed_label(block_type, _KNOWN_CONTENT_TYPES)] += 1
        self._fail(_content_failure(typed_block, block_type))

    def _observe_pair(self, item: ReadOnlyJsonObject, item_type: object) -> None:
        if not isinstance(item_type, str) or item_type not in _CALL_TYPES | _OUTPUT_TYPES:
            return
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            self.flags.add("missing_call_ids")
            self._fail("missing_call_id")
        elif item_type in _CALL_TYPES:
            self._record_call(call_id, item_type)
        else:
            self._record_output(call_id, item_type)

    def _record_call(self, call_id: str, item_type: str) -> None:
        if call_id in self.calls:
            self.flags.add("duplicate_calls")
            self._fail("duplicate_call")
        self.calls[call_id] = item_type

    def _record_output(self, call_id: str, item_type: str) -> None:
        duplicate = call_id in self.outputs
        self.outputs.add(call_id)
        call = self.calls.get(call_id)
        if call is None:
            self.flags.add("outputs_before_calls")
            self._fail("output_before_call")
        elif _PAIR_TYPES[call] != item_type:
            self.flags.add("mismatched_output_types")
            self._fail("mismatched_output_type")
        elif not duplicate:
            self.flags.add("matched_pairs")
        if duplicate:
            self.flags.add("duplicate_outputs")
            self._fail("duplicate_output")

    def _fail(self, reason: str) -> None:
        self.first_reason = self.first_reason or reason

    def finish(self) -> InputDiagnostic:
        flags = self.flags
        call_ids, output_ids = set(self.calls), set(self.outputs)
        if not call_ids <= output_ids:
            flags.add("unmatched_calls")
        if not output_ids <= call_ids:
            flags.add("unmatched_outputs")
        return InputDiagnostic(
            _size_bucket(self.input_items),
            _bucketed_counts(self.item_types),
            _bucketed_counts(self.content_types),
            *(flag in flags for flag in _DIAGNOSTIC_FLAGS),
            first_incompatible_reason=self.first_reason,
            shape_sha256=self.shape_sha256,
        )


def _item_type_failure(item_type: object) -> str:
    if not isinstance(item_type, str):
        return "missing_item_type"
    return "" if item_type in _KNOWN_ITEM_TYPES else "unknown_item_type"


def _item_failure(item: ReadOnlyJsonObject, item_type: object) -> str:
    if not isinstance(item_type, str):
        return ""
    if item_type == "message":
        return _message_failure(item)
    fields = _REQUIRED_STRING_FIELDS.get(item_type)
    if fields is not None and not _strings_present(item, fields):
        return f"invalid_{item_type}"
    contract = _ITEM_VALUE_FIELDS.get(item_type)
    if contract is not None and not isinstance(item.get(contract[0]), contract[1]):
        return contract[2]
    if item_type in _OUTPUT_TYPES - {"tool_search_output"} and not isinstance(
        item.get("output"), (str, list)
    ):
        return "invalid_tool_output"
    return ""


def _content_failure(block: ReadOnlyJsonObject, block_type: object) -> str:
    if not isinstance(block_type, str) or block_type not in _KNOWN_CONTENT_TYPES:
        return "unknown_content_type"
    if block_type == "input_image" and not _valid_image(block):
        return "invalid_input_image_block"
    contract = _CONTENT_VALUE_FIELDS.get(block_type)
    if contract and not isinstance(block.get(contract[0]), str):
        return contract[1]
    return ""


def _strings_present(item: ReadOnlyJsonObject, fields: tuple[str, ...]) -> bool:
    return all(type(item.get(field)) is str and bool(item.get(field)) for field in fields)


def _message_failure(item: ReadOnlyJsonObject) -> str:
    content = item.get("content")
    match item.get("role") in (*_ROLES, "assistant"), content:
        case False, _:
            return "invalid_message_role"
        case True, value if not isinstance(value, (str, list)):
            return "invalid_message_content"
        case True, []:
            return "empty_message_content"
        case _:
            return ""


def _valid_image(block: ReadOnlyJsonObject) -> bool:
    has_source = any(isinstance(block.get(field), str) for field in ("image_url", "file_id"))
    return block.get("detail") in {"low", "high", "auto", "original"} and has_source


def _bucket_counts(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: cast(str, bucket)
        for key, bucket in value.items()
        if isinstance(key, str) and bucket in _BUCKETS
    }


def _size_bucket_value(value: object) -> str:
    return cast(str, value) if value in _BUCKETS else "0"
