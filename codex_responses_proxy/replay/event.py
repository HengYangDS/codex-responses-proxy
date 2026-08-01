"""Remove provider ciphertext from complete downstream Responses SSE events."""

from __future__ import annotations

import json
from typing import cast

from codex_responses_proxy.replay.request import OPAQUE_CONTENT_MARKER

type JsonObject = dict[str, object]

_OUTPUT_ITEM_TYPES = frozenset(("function_call_output", "custom_tool_call_output"))


def _semantically_empty_stream_content(value: object) -> bool:
    if value in (None, "", []):
        return True
    if not isinstance(value, list):
        return False
    return all(
        isinstance(block, dict)
        and (
            (block.get("type") in ("input_text", "output_text") and block.get("text") == "")
            or (block.get("type") == "refusal" and block.get("refusal") == "")
        )
        for block in value
    )


def _strip_encrypted_blocks(item: JsonObject, field: str, marker_type: str) -> int:
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
        item[field] = (
            [{"type": marker_type, "text": OPAQUE_CONTENT_MARKER}]
            if _semantically_empty_stream_content(kept)
            else kept
        )
    return removed


def _mark_root_only_ciphertext(item: JsonObject, field: str, marker_type: str) -> None:
    if _semantically_empty_stream_content(item.get(field)):
        item[field] = [{"type": marker_type, "text": OPAQUE_CONTENT_MARKER}]


def _strip_provider_ciphertext(obj: object) -> int:
    removed = 0
    if isinstance(obj, dict):
        item = cast(JsonObject, obj)
        item_type = item.get("type")
        if item_type == "reasoning" and "encrypted_content" in item:
            del item["encrypted_content"]
            removed += 1
        if item_type == "agent_message":
            removed += _strip_encrypted_blocks(item, "content", "output_text")
            if "encrypted_content" in item:
                del item["encrypted_content"]
                removed += 1
                _mark_root_only_ciphertext(item, "content", "output_text")
        if item_type in _OUTPUT_ITEM_TYPES:
            removed += _strip_encrypted_blocks(item, "output", "input_text")
            if "encrypted_content" in item:
                del item["encrypted_content"]
                removed += 1
                _mark_root_only_ciphertext(item, "output", "input_text")
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
