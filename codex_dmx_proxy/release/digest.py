"""Canonical aggregate identity for an explicit serving-file digest map."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PayloadDigestError(ValueError):
    """Report an invalid path-to-SHA-256 aggregate input."""


def canonical_json(value: Mapping[str, Any]) -> bytes:
    """Encode one mapping in the canonical compact JSON form used by release state."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Recursively freeze one JSON-like mapping for immutable release evidence."""

    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return MappingProxyType({str(key): freeze(child) for key, child in item.items()})
        if isinstance(item, list | tuple):
            return tuple(freeze(child) for child in item)
        return item

    return MappingProxyType({str(key): freeze(item) for key, item in value.items()})


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Hash sorted length-delimited UTF-8 paths and raw SHA-256 digest bytes."""

    aggregate = hashlib.sha256()
    for relative in sorted(file_digests):
        digest = file_digests[relative]
        if not isinstance(relative, str) or not relative or _SHA256.fullmatch(digest) is None:
            raise PayloadDigestError(f"invalid serving payload digest: {relative}")
        path_bytes = relative.encode("utf-8")
        digest_bytes = bytes.fromhex(digest)
        aggregate.update(len(path_bytes).to_bytes(8, "big"))
        aggregate.update(path_bytes)
        aggregate.update(len(digest_bytes).to_bytes(8, "big"))
        aggregate.update(digest_bytes)
    return aggregate.hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()
