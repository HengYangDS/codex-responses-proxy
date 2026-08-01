"""Opaque source payload capability consumed by one projection transaction."""

from __future__ import annotations

import hashlib
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from codex_responses_proxy.payload import digest, inventory

RECEIPT_SCHEMA = 1


class PayloadSourceError(RuntimeError):
    """Report an invalid, mutated, forged, or already consumed payload capability."""


@dataclass(frozen=True, slots=True)
class ReleasedBlob:
    """One immutable regular Git blob admitted for a projection transaction."""

    path: str
    mode: Literal["100644", "100755"]
    blob_oid: str
    sha256: str
    content: bytes


class _PayloadAuthority:
    """Process-local issuer and one-use claimant for released payloads."""

    def __init__(self) -> None:
        self.token = object()
        self.issued: weakref.WeakSet[Any] = weakref.WeakSet()

    def mint(
        self,
        blobs: tuple[ReleasedBlob, ...],
        receipt: Mapping[str, Any],
        sidecar: Mapping[str, Any],
    ) -> ReleasedPayload:
        candidate = ReleasedPayload(
            blobs=blobs, receipt=receipt, sidecar=sidecar, _token=self.token
        )
        self.issued.add(candidate)
        return candidate

    def claim(
        self, candidate: object
    ) -> tuple[tuple[ReleasedBlob, ...], str, str, Mapping[str, Any], Mapping[str, Any]]:
        if type(candidate) is not ReleasedPayload or candidate not in self.issued:
            raise PayloadSourceError("payload transaction requires an admitted ReleasedPayload")
        candidate._verify_integrity()
        return (
            candidate._claim_blobs(),
            candidate.version,
            candidate.receipt_sha256,
            candidate.receipt,
            candidate.sidecar,
        )


_AUTHORITY = _PayloadAuthority()


class ReleasedPayload:
    """Opaque single-use authority over one exact released payload projection."""

    __slots__ = ("_blobs", "_claimed", "_receipt", "_receipt_sha256", "_sidecar", "__weakref__")

    _blobs: tuple[ReleasedBlob, ...]
    _claimed: bool
    _receipt: Mapping[str, Any]
    _receipt_sha256: str
    _sidecar: Mapping[str, Any]

    def __init__(
        self,
        *,
        blobs: tuple[ReleasedBlob, ...],
        receipt: Mapping[str, Any],
        sidecar: Mapping[str, Any],
        _token: object | None = None,
    ) -> None:
        if _token is not _AUTHORITY.token:
            raise TypeError("ReleasedPayload is opaque; use signed release admission")
        object.__setattr__(self, "_blobs", blobs)
        object.__setattr__(self, "_receipt", digest.freeze_mapping(receipt))
        object.__setattr__(self, "_sidecar", digest.freeze_mapping(sidecar))
        object.__setattr__(
            self, "_receipt_sha256", hashlib.sha256(digest.canonical_json(receipt)).hexdigest()
        )
        object.__setattr__(self, "_claimed", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise PayloadSourceError("released payload capability is immutable")

    @property
    def version(self) -> str:
        """Return the admitted strict release version."""

        return str(self._receipt["version"])

    @property
    def serving_payload_sha256(self) -> str:
        """Return the aggregate digest of admitted serving files."""

        return str(self._receipt["serving_payload_sha256"])

    @property
    def receipt_sha256(self) -> str:
        """Return the digest of the canonical receipt bytes."""

        return self._receipt_sha256

    @property
    def receipt(self) -> Mapping[str, Any]:
        """Return immutable signed-source evidence."""

        return self._receipt

    @property
    def sidecar(self) -> Mapping[str, Any]:
        """Return immutable receipt-integrity evidence."""

        return self._sidecar

    def peek_blobs(self) -> tuple[ReleasedBlob, ...]:
        """Return immutable bytes for read-only identity checks."""

        return self._blobs

    def _claim_blobs(self) -> tuple[ReleasedBlob, ...]:
        if self._claimed:
            raise PayloadSourceError("released payload bytes were already claimed")
        object.__setattr__(self, "_claimed", True)
        return self._blobs

    def _verify_integrity(self) -> None:
        receipt_digest = hashlib.sha256(
            digest.canonical_json(plain_value(self._receipt))
        ).hexdigest()
        entries = self._receipt.get("payload")
        bound = ("tag_object_oid", "commit_oid", "tree_oid", "serving_payload_sha256")
        if (
            receipt_digest != self._receipt_sha256
            or self._sidecar.get("schema_version") != RECEIPT_SCHEMA
            or self._sidecar.get("algorithm") != "sha256"
            or self._sidecar.get("receipt_sha256") != receipt_digest
            or any(self._sidecar.get(field) != self._receipt.get(field) for field in bound)
            or not isinstance(entries, tuple)
            or len(entries) != len(self._blobs)
        ):
            raise PayloadSourceError("released payload integrity check failed")
        for entry, blob in zip(entries, self._blobs, strict=True):
            expected = {
                "path": blob.path,
                "mode": blob.mode,
                "blob_oid": blob.blob_oid,
                "sha256": hashlib.sha256(blob.content).hexdigest(),
            }
            if (
                not isinstance(entry, Mapping)
                or dict(entry) != expected
                or blob.sha256 != expected["sha256"]
            ):
                raise PayloadSourceError("released payload integrity check failed")
        serving_paths = self._receipt.get("serving_files")
        if not isinstance(serving_paths, tuple):
            raise PayloadSourceError("released payload integrity check failed")
        try:
            actual = inventory.serving_payload_sha256(
                {blob.path: blob.sha256 for blob in self._blobs if blob.path in serving_paths}
            )
        except digest.PayloadDigestError as error:
            raise PayloadSourceError("released payload integrity check failed") from error
        if actual != self._receipt.get("serving_payload_sha256"):
            raise PayloadSourceError("released payload integrity check failed")


def mint(
    blobs: tuple[ReleasedBlob, ...],
    receipt: Mapping[str, Any],
    sidecar: Mapping[str, Any],
) -> ReleasedPayload:
    """Mint one process-local capability after signed-source verification."""

    return _AUTHORITY.mint(blobs, receipt, sidecar)


def claim(candidate: object):
    """Consume one live admitted released-payload authority."""

    return _AUTHORITY.claim(candidate)


def plain_value(value: Any) -> Any:
    """Copy frozen payload evidence into canonical JSON-compatible values."""

    if isinstance(value, Mapping):
        return {str(key): plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain_value(item) for item in value]
    return value
