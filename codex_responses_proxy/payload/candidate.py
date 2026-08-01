"""Validation and materialization of one admitted payload candidate."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Set
from pathlib import Path, PurePosixPath
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.payload import digest, inventory, projection, source
from codex_responses_proxy.runtime import context as runtime_context

_STRICT_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def validate(
    blobs: tuple[source.ReleasedBlob, ...],
    version: str,
    receipt_sha256: str,
    receipt: Mapping[str, Any],
) -> None:
    """Reject an admitted candidate whose payload contract is inconsistent."""

    if _STRICT_VERSION.fullmatch(version) is None:
        raise errors.InstallError("released payload version is invalid")
    if not isinstance(receipt_sha256, str) or len(receipt_sha256) != 64:
        raise errors.InstallError("released payload receipt digest is invalid")
    if receipt.get("version") != version:
        raise errors.InstallError("released payload receipt version mismatch")
    expected_paths = tuple(inventory.RUNTIME_FILES)
    actual_paths = tuple(blob.path for blob in blobs)
    if actual_paths != expected_paths or len(set(actual_paths)) != len(actual_paths):
        raise errors.InstallError("released payload file set mismatch")
    for blob in blobs:
        if blob.mode not in {"100644", "100755"}:
            raise errors.InstallError(f"released payload mode is invalid: {blob.path}")
        if hashlib.sha256(blob.content).hexdigest() != blob.sha256:
            raise errors.InstallError(f"released payload digest mismatch: {blob.path}")
    version_blob = next(blob for blob in blobs if blob.path == "VERSION")
    if version_blob.content != f"{version}\n".encode():
        raise errors.InstallError("released payload VERSION blob mismatch")
    manifest = manifest_for(version, blobs, receipt_sha256)
    if tuple(receipt.get("serving_files", ())) != tuple(inventory.SERVING_FILES):
        raise errors.InstallError("released payload serving file set mismatch")
    if receipt.get("serving_payload_sha256") != manifest["serving_payload_sha256"]:
        raise errors.InstallError("released payload serving identity mismatch")


def manifest_for(
    version: str,
    blobs: tuple[source.ReleasedBlob, ...],
    receipt_sha256: str,
) -> dict[str, Any]:
    """Build the installed manifest for one validated candidate."""

    return projection.manifest_for_digests(
        version, {blob.path: blob.sha256 for blob in blobs}, receipt_sha256
    )


def reject_unowned_collisions(
    ctx: runtime_context.RuntimeContext,
    previous_owned: Set[str],
) -> None:
    """Refuse to overwrite a candidate path not owned by the prior projection."""

    install = Path(ctx.install_dir)
    for relative in projection._OWNED_PAYLOAD_FILES:
        path = projection._payload_path(install, relative)
        if relative not in previous_owned and (path.exists() or path.is_symlink()):
            raise errors.InstallError(f"candidate unowned collision: {relative}")


def write_projection(
    ctx: runtime_context.RuntimeContext,
    blobs: tuple[source.ReleasedBlob, ...],
    version: str,
    receipt: Mapping[str, Any],
    receipt_sha256: str,
) -> None:
    """Write candidate bytes, manifest, and receipt into the install root."""

    install = Path(ctx.install_dir)
    for blob in blobs:
        target = install.joinpath(*PurePosixPath(blob.path).parts)
        projection._atomic_write_bytes(
            target,
            blob.content,
            mode=0o755 if blob.mode == "100755" else 0o644,
            root=install,
        )
        if projection._sha256_file(target) != blob.sha256:
            raise errors.InstallError(f"installed payload digest mismatch: {blob.path}")
    projection._atomic_write_bytes(
        install / inventory.MANIFEST_FILENAME,
        projection.manifest_bytes(manifest_for(version, blobs, receipt_sha256)),
        root=install,
    )
    projection._atomic_write_bytes(
        install / inventory.RELEASE_RECEIPT_FILENAME,
        digest.canonical_json(_json_value(receipt)),
        mode=0o600,
        root=install,
    )


def remove_projection(ctx: runtime_context.RuntimeContext) -> None:
    """Remove only files owned by an uncommitted fresh candidate."""

    install = Path(ctx.install_dir)
    for relative in projection._OWNED_PAYLOAD_FILES:
        projection._payload_path(install, relative).unlink(missing_ok=True)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value
