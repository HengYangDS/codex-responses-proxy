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
from collections.abc import Callable
from typing import cast

type JsonObject = dict[str, object]
type JsonReject = Callable[[object], bool]


def _prune_list_fields(obj: object, fields: tuple[str, ...], reject: JsonReject) -> int:
    """Remove rejected items from named lists anywhere in a JSON value."""
    removed = 0
    if isinstance(obj, list):
        return sum(_prune_list_fields(value, fields, reject) for value in obj)
    if not isinstance(obj, dict):
        return 0

    owner = cast(JsonObject, obj)
    for field in fields:
        items = owner.get(field)
        if isinstance(items, list):
            kept = [item for item in items if not reject(item)]
            removed += len(items) - len(kept)
            if len(kept) != len(items):
                owner[field] = kept
    return removed + sum(_prune_list_fields(value, fields, reject) for value in owner.values())


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
    return _prune_list_fields(
        obj,
        ("content", "output"),
        lambda item: (
            isinstance(item, dict)
            and cast(JsonObject, item).get("type") == "encrypted_content"
            and "encrypted_content" not in item
        ),
    )


def _strip_replayed_reasoning_items(payload: JsonObject) -> tuple[int, int]:
    """Drop top-level reasoning items while preserving valid agent ciphertext."""
    inputs = cast(list[object], payload.get("input", []))

    kept = [
        item
        for item in inputs
        if not (isinstance(item, dict) and cast(JsonObject, item).get("type") == "reasoning")
    ]
    preserved_agent_blocks = sum(
        1
        for item in kept
        if isinstance(item, dict) and cast(JsonObject, item).get("type") == "agent_message"
        for content in (cast(JsonObject, item).get("content"),)
        if isinstance(content, list)
        for block in content
        if (
            isinstance(block, dict)
            and cast(JsonObject, block).get("type") == "encrypted_content"
            and "encrypted_content" in block
        )
    )
    dropped_items = len(inputs) - len(kept)
    if dropped_items:
        payload["input"] = kept
    return dropped_items, preserved_agent_blocks


def _is_replayable_remote_image_url(value: object) -> bool:
    """Return whether a value is a remotely fetchable HTTP(S) image URL."""
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


def _strip_unreplayable_images(obj: object) -> int:
    """Drop historical input images that the provider cannot fetch remotely."""
    return _prune_list_fields(
        obj,
        ("output", "content"),
        lambda item: (
            isinstance(item, dict)
            and cast(JsonObject, item).get("type") == "input_image"
            and not _is_replayable_remote_image_url(cast(JsonObject, item).get("image_url"))
        ),
    )


def sanitize_responses_body(raw: bytes) -> tuple[bytes, str]:
    """Project a Responses request onto provider-compatible replay semantics.

    Unrecognized JSON and failed reserialization are returned unchanged. The
    diagnostic note reports transformation categories without request values.
    """
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return raw, f"passthrough (non-json: {exc.__class__.__name__})"
    if not isinstance(payload, dict):
        return raw, "passthrough (non-object JSON)"

    try:
        dropped_items, preserved_agent_blocks = _strip_replayed_reasoning_items(payload)
        dropped_malformed_blocks = _drop_malformed_encrypted_content_blocks(payload)
        dropped_images = _strip_unreplayable_images(payload)
    except RecursionError:
        return raw, "passthrough (projection depth exceeded)"
    include = payload.get("include")

    include_trimmed = False
    if isinstance(include, list):
        new_include = [item for item in include if item != "reasoning.encrypted_content"]
        include_trimmed = len(new_include) != len(include)
        payload["include"] = new_include

    if not (dropped_items or dropped_malformed_blocks or dropped_images or include_trimmed):
        return raw, "clean (nothing to strip)"

    try:
        rewritten = json.dumps(payload).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        return raw, f"passthrough (reserialize failed: {exc.__class__.__name__})"
    return rewritten, (
        f"stripped reasoning_items={dropped_items} "
        f"malformed_encrypted_blocks={dropped_malformed_blocks} "
        f"local_image_items={dropped_images} "
        f"agent_message_encrypted={preserved_agent_blocks} "
        f"include_trimmed={include_trimmed}"
    )


def sanitize_sse_event(raw_event: bytes) -> tuple[bytes, int]:
    """Remove reasoning ciphertext, or return the exact event when projection is unsafe."""
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
            try:
                obj = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                out_lines.append(line)
                continue
            try:
                removed = _strip_reasoning_encrypted_content_from_sse_event(obj)
            except RecursionError:
                return raw_event, 0
            if removed:
                try:
                    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                except (TypeError, ValueError, RecursionError):
                    return raw_event, 0
                line = prefix + data + suffix
                removed_total += removed
        out_lines.append(line)
    return b"".join(out_lines), removed_total
