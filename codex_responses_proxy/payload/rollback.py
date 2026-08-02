"""Exact snapshot, validation, and restoration of an installed payload."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.payload import digest, inventory, owned_files, projection, state
from codex_responses_proxy.runtime import context as runtime_context


@dataclass(frozen=True)
class RollbackInventory:
    """Verified ownership and content metadata retained for rollback."""

    present: Mapping[str, tuple[str, int]]
    retired: frozenset[str]
    previous_owned: frozenset[str]


def path_set_sha256(paths: set[str] | frozenset[str]) -> str:
    """Return the canonical digest of a set of owned relative paths."""

    content = json.dumps(sorted(paths), separators=(",", ":")) + "\n"
    return hashlib.sha256(content.encode()).hexdigest()


def write_snapshot(
    ctx: runtime_context.RuntimeContext,
    root: Path,
    candidate_version: str,
) -> RollbackInventory:
    """Persist and return the exact prior owned projection."""

    install = Path(ctx.install_dir)
    present: dict[str, dict[str, object]] = {}
    current_owned = set(owned_files.OWNED_PAYLOAD_FILES)
    retired_owned: set[str] = set()
    manifest_path = install / inventory.MANIFEST_FILENAME
    manifest_exists = manifest_path.exists() or manifest_path.is_symlink()
    retired_roots_exist = any(
        (install / relative).exists() or (install / relative).is_symlink()
        for relative in owned_files.RETIRED_INSTALL_DIRECTORIES
    )
    if not manifest_exists:
        if retired_roots_exist:
            raise errors.InstallError("retired installed payload manifest is required")
        previous_owned = current_owned
    else:
        if manifest_path.is_symlink():
            raise errors.InstallError("installed payload manifest is a symlink")
        manifest = owned_files.read_json_object(manifest_path, "installed payload manifest")
        files = manifest.get("files")
        current_manifest = (
            manifest.get("schema_version") == projection.PAYLOAD_MANIFEST_SCHEMA_VERSION
            and isinstance(files, dict)
            and set(files) == set(inventory.RUNTIME_FILES)
        )
        if current_manifest:
            ok, detail = projection.verify_payload_manifest(ctx)
            if not ok:
                raise errors.InstallError(f"installed payload integrity check failed: {detail}")
            previous_owned = current_owned
        else:
            historical = projection.verify_historical_projection(ctx)
            owned = historical.files
            if state.compare_versions(candidate_version, historical.release) < 0:
                raise errors.InstallError("released payload downgrade is refused")
            previous_owned = set(owned) | set(historical.metadata)
            retired_owned = previous_owned - current_owned
    for relative in sorted(previous_owned):
        source = owned_files.path(install, relative)
        if not source.exists() and not source.is_symlink():
            continue
        source = owned_files.regular_file(install, relative, "live owned")
        present[relative] = _snapshot_file(source, owned_files.path(root, relative))
    raw = {
        "schema_version": 2,
        "present": present,
        "retired": sorted(retired_owned),
        "retired_owned_sha256": path_set_sha256(retired_owned),
        "previous_owned": sorted(previous_owned),
    }
    owned_files.write_bytes(root / "snapshot.json", digest.canonical_json(raw), mode=0o600)
    return read_inventory(raw)


def load_inventory(root: Path) -> RollbackInventory:
    """Load and verify a retained rollback inventory."""

    snapshot = owned_files.read_canonical_json(root / "snapshot.json", "payload rollback snapshot")
    return read_inventory(snapshot)


def read_inventory(snapshot: Mapping[str, Any]) -> RollbackInventory:
    """Validate an in-memory rollback snapshot and project its inventory."""

    if snapshot.get("schema_version") != 2:
        raise errors.InstallError("payload rollback snapshot schema is unsupported")
    raw_present = snapshot.get("present")
    raw_retired = snapshot.get("retired")
    retired_proof = snapshot.get("retired_owned_sha256")
    raw_previous_owned = snapshot.get("previous_owned")
    if (
        not isinstance(raw_present, dict)
        or not isinstance(raw_retired, list)
        or not isinstance(raw_previous_owned, list)
    ):
        raise errors.InstallError("payload rollback snapshot is invalid")
    retired = {owned_files.canonical_relative(value, "payload rollback") for value in raw_retired}
    previous_owned = {
        owned_files.canonical_relative(value, "payload rollback") for value in raw_previous_owned
    }
    if len(retired) != len(raw_retired) or len(previous_owned) != len(raw_previous_owned):
        raise errors.InstallError("payload rollback retired inventory is invalid")
    if retired_proof != path_set_sha256(retired):
        raise errors.InstallError("payload rollback retired owned proof is invalid")
    present: dict[str, tuple[str, int]] = {}
    for raw_relative, metadata in raw_present.items():
        relative = owned_files.canonical_relative(raw_relative, "payload rollback")
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "mode"}
            or not isinstance(metadata.get("sha256"), str)
            or len(metadata["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in metadata["sha256"])
            or not isinstance(metadata.get("mode"), int)
            or isinstance(metadata.get("mode"), bool)
            or not 0 <= metadata["mode"] <= 0o777
        ):
            raise errors.InstallError(f"payload rollback metadata is invalid: {relative}")
        present[relative] = (metadata["sha256"], metadata["mode"])
    if not retired.issubset(present) or not retired.issubset(previous_owned):
        raise errors.InstallError("payload rollback retired inventory is incomplete")
    if not retired.issubset(projection.RETIRED_OWNED_FILES):
        raise errors.InstallError("payload rollback retired inventory is invalid")
    if not set(present).issubset(previous_owned):
        raise errors.InstallError("payload rollback owned inventory is invalid")
    return RollbackInventory(
        present=present,
        retired=frozenset(retired),
        previous_owned=frozenset(previous_owned),
    )


def restore_snapshot(ctx: runtime_context.RuntimeContext, root: Path) -> None:
    """Restore every retained byte and prove the resulting projection."""

    snapshot = load_inventory(root)
    install = Path(ctx.install_dir)
    restored: dict[str, tuple[bytes, int]] = {}
    for relative, (expected, mode) in snapshot.present.items():
        source = owned_files.regular_file(root, relative, "payload rollback")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise errors.InstallError(f"payload rollback is unreadable: {relative}") from exc
        if hashlib.sha256(content).hexdigest() != expected:
            raise errors.InstallError(f"payload rollback digest mismatch: {relative}")
        target = owned_files.path(install, relative)
        if relative in snapshot.retired and (target.exists() or target.is_symlink()):
            existing = owned_files.regular_file(install, relative, "retired rollback target")
            if digest.sha256_file(existing) != expected:
                raise errors.InstallError(f"retired rollback target conflicts: {relative}")
        restored[relative] = content, mode
    absent = set(owned_files.OWNED_PAYLOAD_FILES) - set(snapshot.present)
    for relative in absent:
        target = owned_files.path(install, relative)
        if target.exists() or target.is_symlink():
            owned_files.regular_file(install, relative, "live owned")
    for relative in absent:
        owned_files.path(install, relative).unlink(missing_ok=True)
    for relative, (content, mode) in restored.items():
        target = owned_files.path(install, relative)
        if relative in snapshot.retired and target.exists():
            continue
        owned_files.write_bytes(target, content, mode=mode, root=install)
    for relative, (expected, _mode) in snapshot.present.items():
        target = owned_files.regular_file(install, relative, "restored payload")
        if digest.sha256_file(target) != expected:
            raise errors.InstallError(f"restored payload digest mismatch: {relative}")


def _snapshot_file(source: Path, target: Path) -> dict[str, object]:
    try:
        content = source.read_bytes()
        mode = source.stat(follow_symlinks=False).st_mode & 0o777
    except OSError as exc:
        raise errors.InstallError(f"payload rollback snapshot read failed: {source.name}") from exc
    owned_files.write_bytes(target, content, mode=mode)
    return {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
