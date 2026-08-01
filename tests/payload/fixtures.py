#!/usr/bin/env python3
"""Builders for released payload and transaction behavior tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast
from unittest import mock

from codex_responses_proxy.payload import digest as payload_digest
from codex_responses_proxy.payload import projection as payload_projection
from codex_responses_proxy.payload import source as payload_source
from codex_responses_proxy.payload import transaction as payload_transaction
from codex_responses_proxy.runtime import context as runtime_context

ROOT = Path(__file__).resolve().parents[2]


def released_fixture(version: str = "1.2.3") -> payload_source.ReleasedPayload:
    """Build a transaction candidate while tests remain below source admission."""

    def blob(relative: str) -> payload_source.ReleasedBlob:
        content = (
            f"{version}\n".encode() if relative == "VERSION" else (ROOT / relative).read_bytes()
        )
        return payload_source.ReleasedBlob(
            path=relative,
            mode="100644",
            blob_oid=hashlib.sha1(content).hexdigest(),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    blobs = tuple(map(blob, payload_projection.RUNTIME_PAYLOAD_FILES))
    serving = {
        item.path: item.sha256
        for item in blobs
        if item.path in payload_projection.SERVING_PAYLOAD_FILES
    }
    receipt = {
        "schema_version": 1,
        "version": version,
        "serving_payload_sha256": payload_projection.serving_payload_sha256(serving),
        "serving_files": list(payload_projection.SERVING_PAYLOAD_FILES),
        "payload": [
            dict(path=item.path, mode=item.mode, blob_oid=item.blob_oid, sha256=item.sha256)
            for item in blobs
        ],
    }
    candidate = mock.create_autospec(payload_source.ReleasedPayload, instance=True)
    candidate.peek_blobs.return_value = blobs
    candidate.receipt = receipt
    candidate.version = version
    candidate.receipt_sha256 = hashlib.sha256(payload_digest.canonical_json(receipt)).hexdigest()
    return cast("payload_source.ReleasedPayload", candidate)


def begin_transaction(
    ctx: runtime_context.RuntimeContext, candidate: payload_source.ReleasedPayload
) -> payload_transaction.PayloadTransaction:
    """Exercise transaction behavior with source claim patched at its authority boundary."""

    if not isinstance(candidate, payload_source.ReleasedPayload):
        return payload_transaction.begin_transaction(ctx, candidate)
    blobs = candidate.peek_blobs()
    receipt = candidate.receipt
    claimed = (blobs, candidate.version, candidate.receipt_sha256, receipt, {})
    with mock.patch.object(payload_source, "claim", return_value=claimed):
        return payload_transaction.begin_transaction(ctx, candidate)


def install_payload(
    ctx: runtime_context.RuntimeContext, version: str = "1.2.3"
) -> payload_transaction.PayloadTransaction:
    """Install and finalize one released payload projection."""

    transaction = begin_transaction(ctx, released_fixture(version))
    transaction.commit_projection()
    transaction.finalize({"pid": 1})
    return transaction
