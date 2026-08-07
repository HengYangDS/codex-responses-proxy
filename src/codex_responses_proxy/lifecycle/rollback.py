"""Exact snapshot and restoration of the current installed payload."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import owned_files, projection
from codex_responses_proxy.service import digest


@dataclass(frozen=True)
class RollbackInventory:
    """Verified content retained for rollback."""

    present: Mapping[str, tuple[str, int]]
    owned: frozenset[str]


def write_snapshot(ctx: runtime_context.RuntimeContext, root: Path) -> RollbackInventory:
    """Persist the exact current payload, or its complete absence."""

    install = Path(ctx.install_dir)
    manifest = projection.payload_manifest_path(ctx)
    owned = frozenset(owned_files.OWNED_PAYLOAD_FILES)
    if not (manifest.exists() or manifest.is_symlink()):
        collisions = [
            relative
            for relative in owned
            if owned_files.path(install, relative).exists()
            or owned_files.path(install, relative).is_symlink()
        ]
        if collisions:
            raise errors.InstallError("unowned install content conflicts: " + ", ".join(collisions))
        present: dict[str, dict[str, object]] = {}
    else:
        if manifest.is_symlink():
            raise errors.InstallError("installed payload manifest is a symlink")
        ok, detail = projection.verify_payload_manifest(ctx)
        if not ok:
            raise errors.InstallError(f"installed payload integrity check failed: {detail}")
        present = {}
        for relative in sorted(owned):
            source = owned_files.path(install, relative)
            if source.exists() or source.is_symlink():
                source = owned_files.regular_file(install, relative, "live owned")
                present[relative] = _snapshot_file(source, owned_files.path(root, relative))
    raw = {"schema_version": 3, "present": present, "owned": sorted(owned)}
    owned_files.write_bytes(root / "snapshot.json", digest.canonical_json(raw), mode=0o600)
    return read_inventory(raw)


def load_inventory(root: Path) -> RollbackInventory:
    """Load and verify a retained rollback inventory."""

    return read_inventory(
        owned_files.read_canonical_json(root / "snapshot.json", "payload rollback snapshot")
    )


def read_inventory(snapshot: Mapping[str, Any]) -> RollbackInventory:
    """Validate an in-memory rollback snapshot."""

    raw_present = snapshot.get("present")
    raw_owned = snapshot.get("owned")
    if (
        snapshot.get("schema_version") != 3
        or not isinstance(raw_present, dict)
        or not isinstance(raw_owned, list)
    ):
        raise errors.InstallError("payload rollback snapshot is invalid")
    owned = {owned_files.canonical_relative(value, "payload rollback") for value in raw_owned}
    if len(owned) != len(raw_owned) or owned != set(owned_files.OWNED_PAYLOAD_FILES):
        raise errors.InstallError("payload rollback owned inventory is invalid")
    present: dict[str, tuple[str, int]] = {}
    for raw_relative, metadata in raw_present.items():
        relative = owned_files.canonical_relative(raw_relative, "payload rollback")
        if (
            relative not in owned
            or not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "mode"}
            or not isinstance(metadata.get("sha256"), str)
            or len(metadata["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in metadata["sha256"])
            or type(metadata.get("mode")) is not int
            or not 0 <= metadata["mode"] <= 0o777
        ):
            raise errors.InstallError(f"payload rollback metadata is invalid: {relative}")
        present[relative] = (metadata["sha256"], metadata["mode"])
    return RollbackInventory(present=present, owned=frozenset(owned))


def restore_snapshot(ctx: runtime_context.RuntimeContext, root: Path) -> None:
    """Restore every retained byte and remove current bytes that were absent."""

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
        restored[relative] = content, mode
    for relative in snapshot.owned - snapshot.present.keys():
        target = owned_files.path(install, relative)
        if target.exists() or target.is_symlink():
            owned_files.regular_file(install, relative, "live owned")
            target.unlink()
    for relative, (content, mode) in restored.items():
        owned_files.write_bytes(
            owned_files.path(install, relative), content, mode=mode, root=install
        )
    for relative, (expected, _mode) in snapshot.present.items():
        if (
            digest.sha256_file(owned_files.regular_file(install, relative, "restored payload"))
            != expected
        ):
            raise errors.InstallError(f"restored payload digest mismatch: {relative}")


def _snapshot_file(source: Path, target: Path) -> dict[str, object]:
    try:
        content = source.read_bytes()
        mode = source.stat(follow_symlinks=False).st_mode & 0o777
    except OSError as exc:
        raise errors.InstallError(f"payload rollback snapshot read failed: {source.name}") from exc
    owned_files.write_bytes(target, content, mode=mode)
    return {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
