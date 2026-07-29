"""Canonical aggregate identity for an explicit serving-file digest map."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PayloadDigestError(ValueError):
    """Report an invalid path-to-SHA-256 aggregate input."""


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
