#!/usr/bin/env python3
"""Rewrite only provider-incompatible Responses replay state at the network edge.

The local conversation remains authoritative and untouched. This module owns
the bounded request/response projection needed by the configured third-party
Responses endpoint: stale reasoning replay state, malformed legacy encrypted
blocks, and images that are not remotely fetchable. Unknown structures pass
through unchanged.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import cast

type JsonObject = dict[str, object]


def _strip_reasoning_encrypted_content_from_sse_event(obj: object) -> int:
    """Remove encrypted replay state only from typed reasoning output items."""
    removed = 0
    if isinstance(obj, dict):
        item = cast(JsonObject, obj)
        if item.get("type") == "reasoning" and "encrypted_content" in item:
            del item["encrypted_content"]
            removed += 1
        for value in item.values():
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    elif isinstance(obj, list):
        for value in obj:
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    return removed


def _drop_malformed_encrypted_content_blocks(obj: object) -> int:
    """Drop legacy typed encrypted blocks that lack their required payload."""
    dropped = 0
    if isinstance(obj, dict):
        owner = cast(JsonObject, obj)
        for field in ("content", "output"):
            items = owner.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and cast(JsonObject, item).get("type") == "encrypted_content"
                    and "encrypted_content" not in item
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                owner[field] = kept
        for value in owner.values():
            dropped += _drop_malformed_encrypted_content_blocks(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _drop_malformed_encrypted_content_blocks(value)
    return dropped


def _strip_replayed_reasoning_items(payload: JsonObject) -> tuple[int, int]:
    """Drop top-level reasoning items while preserving valid agent ciphertext."""
    dropped_items = 0
    preserved_agent_blocks = 0
    inputs = payload.get("input")
    if not isinstance(inputs, list):
        return dropped_items, preserved_agent_blocks

    kept = []
    for item in inputs:
        if isinstance(item, dict) and cast(JsonObject, item).get("type") == "reasoning":
            dropped_items += 1
            continue
        if isinstance(item, dict) and cast(JsonObject, item).get("type") == "agent_message":
            content = cast(JsonObject, item).get("content")
            if isinstance(content, list):
                preserved_agent_blocks += sum(
                    1
                    for block in content
                    if (
                        isinstance(block, dict)
                        and cast(JsonObject, block).get("type") == "encrypted_content"
                        and "encrypted_content" in block
                    )
                )
        kept.append(item)
    if dropped_items:
        payload["input"] = kept
    return dropped_items, preserved_agent_blocks


def _is_replayable_remote_image_url(value: object) -> bool:
    """Return whether a value is a remotely fetchable HTTP(S) image URL."""
    if not isinstance(value, str) or not value:
        return False
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        _ = parsed.port
    except ValueError:
        return False
    return True


def _strip_unreplayable_images(obj: object) -> int:
    """Drop historical input images that the provider cannot fetch remotely."""
    dropped = 0
    if isinstance(obj, dict):
        owner = cast(JsonObject, obj)
        for field in ("output", "content"):
            items = owner.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and cast(JsonObject, item).get("type") == "input_image"
                    and not _is_replayable_remote_image_url(cast(JsonObject, item).get("image_url"))
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                owner[field] = kept
        for value in owner.values():
            dropped += _strip_unreplayable_images(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _strip_unreplayable_images(value)
    return dropped


def sanitize_responses_body(raw: bytes) -> tuple[bytes, str]:
    """Project a Responses request onto provider-compatible replay semantics.

    Unrecognized or non-object JSON is returned unchanged. The diagnostic note
    reports transformation categories without including request values.
    """
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return raw, f"passthrough (non-json: {exc.__class__.__name__})"

    if not isinstance(payload, dict):
        return raw, "passthrough (json not object)"
    payload = cast(JsonObject, payload)

    dropped_items, preserved_agent_blocks = _strip_replayed_reasoning_items(payload)
    dropped_malformed_blocks = _drop_malformed_encrypted_content_blocks(payload)
    dropped_images = _strip_unreplayable_images(payload)

    include = payload.get("include")
    include_trimmed = False
    if isinstance(include, list):
        new_include = [item for item in include if item != "reasoning.encrypted_content"]
        if len(new_include) != len(include):
            payload["include"] = new_include
            include_trimmed = True

    if not (dropped_items or dropped_malformed_blocks or dropped_images or include_trimmed):
        return raw, "clean (nothing to strip)"

    try:
        new_raw = json.dumps(payload).encode("utf-8")
    except Exception as exc:
        return raw, f"passthrough (reserialize failed: {exc.__class__.__name__})"

    return new_raw, (
        f"stripped reasoning_items={dropped_items} "
        f"malformed_encrypted_blocks={dropped_malformed_blocks} "
        f"local_image_items={dropped_images} "
        f"agent_message_encrypted={preserved_agent_blocks} "
        f"include_trimmed={include_trimmed}"
    )


def sanitize_sse_event(raw_event: bytes) -> tuple[bytes, int]:
    """Remove reasoning ciphertext from one SSE event while preserving framing."""
    if b"encrypted_content" not in raw_event:
        return raw_event, 0
    out_lines = []
    removed_total = 0
    for line in raw_event.splitlines(keepends=True):
        if line.startswith(b"data: "):
            prefix = b"data: "
            suffix = b"\n" if line.endswith(b"\n") else b""
            data = line[len(prefix) :]
            if suffix:
                data = data[:-1]
            if data.strip() == b"[DONE]":
                out_lines.append(line)
                continue
            try:
                obj = json.loads(data)
                removed = _strip_reasoning_encrypted_content_from_sse_event(obj)
                if removed:
                    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                    line = prefix + data + suffix
                    removed_total += removed
            except Exception:
                pass
        out_lines.append(line)
    return b"".join(out_lines), removed_total
