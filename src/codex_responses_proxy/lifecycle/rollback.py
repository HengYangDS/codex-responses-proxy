"""One-time legacy projection migration and retained generation rollback."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.json_value import ReadOnlyJsonObject
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import state
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory

LEGACY_SNAPSHOT_FILENAME = "legacy-projection.json"


@dataclass(frozen=True)
class LegacyProjectionSnapshot:
    """Verified flat payload retained only across one layout migration."""

    present: Mapping[str, tuple[str, int]]
    owned: frozenset[str]


@dataclass(frozen=True, slots=True)
class RetainedRollback:
    """One verified predecessor bound to the installed successor generation."""

    root: Path
    predecessor: identity.LoadedPayloadIdentity
    successor: identity.LoadedPayloadIdentity


@dataclass(frozen=True, slots=True)
class RetainedRollbackStatus:
    """Secret-free availability of the one retained predecessor."""

    state: str
    from_release: str | None = None
    to_release: str | None = None
    detail: str | None = None


def legacy_snapshot_path(root: Path) -> Path:
    """Return the private one-time legacy migration plan path."""
    return root / LEGACY_SNAPSHOT_FILENAME


def write_legacy_snapshot(
    ctx: runtime_context.RuntimeContext,
    root: Path,
) -> LegacyProjectionSnapshot:
    """Persist one exact flat payload for migration or restoration."""
    install = Path(ctx.payload_dir)
    manifest = projection.payload_manifest_path(ctx)
    if not (manifest.exists() or manifest.is_symlink()):
        owned = frozenset(owned_files.OWNED_PAYLOAD_METADATA)
        present: dict[str, dict[str, object]] = {}
    else:
        if manifest.is_symlink():
            raise errors.InstallError("installed payload manifest is a symlink")
        ok, detail = projection.verify_payload_manifest(ctx)
        if not ok:
            raise errors.InstallError(f"installed payload integrity check failed: {detail}")
        owned = owned_files.current_inventory(install)
        present = {}
        for relative in sorted(owned):
            source = owned_files.path(install, relative)
            if source.exists() or source.is_symlink():
                source = owned_files.regular_file(install, relative, "live owned")
                present[relative] = _snapshot_file(source, owned_files.path(root, relative))
    raw = {"schema_version": 3, "present": present, "owned": sorted(owned)}
    owned_files.write_bytes(legacy_snapshot_path(root), digest.canonical_json(raw), mode=0o600)
    return read_legacy_snapshot(raw)


def load_legacy_snapshot(root: Path) -> LegacyProjectionSnapshot:
    """Load and verify one legacy projection migration plan."""
    return read_legacy_snapshot(
        owned_files.read_canonical_json(
            legacy_snapshot_path(root),
            "legacy payload migration snapshot",
        )
    )


def remove_retained(ctx: runtime_context.RuntimeContext) -> None:
    """Drop the predecessor from the sole generation selector."""
    selection = generation.read(ctx)
    _require_closed_generation_store(ctx, selection)
    if selection is None or selection.predecessor is None:
        return
    generation.select(ctx, active=selection.active, predecessor=None)
    generation.prune(ctx, generation.Selection(selection.active, None))


def load_retained(ctx: runtime_context.RuntimeContext) -> RetainedRollback:
    """Load and verify the sole predecessor bound to the live successor."""
    selection = generation.read(ctx)
    _require_closed_generation_store(ctx, selection)
    if selection is None or selection.predecessor is None:
        raise errors.InstallError("retained rollback predecessor is unavailable")
    return _load_selected(ctx, selection)


def _load_selected(
    ctx: runtime_context.RuntimeContext,
    selection: generation.Selection,
) -> RetainedRollback:
    """Verify the identities bound by one already validated selection."""
    assert selection.predecessor is not None
    active_ctx = generation.context(ctx, selection.active)
    predecessor_ctx = generation.context(ctx, selection.predecessor)
    successor = identity.committed_payload(Path(active_ctx.executable))
    predecessor = identity.committed_payload(Path(predecessor_ctx.executable))
    installed = state.read_installed(ctx)
    if successor is None:
        raise errors.InstallError("retained rollback successor generation identity is invalid")
    if predecessor is None:
        raise errors.InstallError("retained rollback predecessor generation identity is invalid")
    if (
        installed is None
        or installed.get("transaction_id") != selection.active
        or installed.get("version") != successor.release
        or installed.get("receipt_sha256") != successor.release_receipt_sha256
        or installed.get("command") != ctx.command
    ):
        raise errors.InstallError("retained rollback installed binding is invalid")
    return RetainedRollback(
        Path(predecessor_ctx.payload_dir),
        predecessor,
        successor,
    )


def load_retained_or_none(
    ctx: runtime_context.RuntimeContext,
) -> RetainedRollback | None:
    """Return the retained predecessor, distinguishing clean absence from corruption."""
    selection = generation.read(ctx)
    _require_closed_generation_store(ctx, selection)
    if selection is None or selection.predecessor is None:
        return None
    return _load_selected(ctx, selection)


def _require_closed_generation_store(
    ctx: runtime_context.RuntimeContext,
    selection: generation.Selection | None,
) -> None:
    """Require the generation store to contain exactly the selected authority."""
    root = generation.root(ctx)
    if selection is None:
        if root.exists() or root.is_symlink():
            raise errors.InstallError("payload generation store exists without a durable selector")
        return
    if root.is_symlink() or not root.is_dir():
        raise errors.InstallError("payload generation store is unavailable or invalid")
    expected = {selection.active, selection.predecessor} - {None}
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise errors.InstallError("payload generation store is unreadable") from exc
    if {entry.name for entry in entries} != expected or any(
        entry.is_symlink() or not entry.is_dir() for entry in entries
    ):
        raise errors.InstallError("payload generation store is not closed over its selector")


def status(ctx: runtime_context.RuntimeContext) -> RetainedRollbackStatus:
    """Inspect retained rollback availability without exposing carrier paths."""
    try:
        retained = load_retained_or_none(ctx)
    except errors.InstallError as exc:
        return RetainedRollbackStatus(state="invalid", detail=str(exc))
    if retained is None:
        return RetainedRollbackStatus(state="unavailable")
    return RetainedRollbackStatus(
        state="available",
        from_release=retained.successor.release,
        to_release=retained.predecessor.release,
    )


def read_legacy_snapshot(snapshot: ReadOnlyJsonObject) -> LegacyProjectionSnapshot:
    """Validate an in-memory legacy projection migration plan."""
    raw_present = snapshot.get("present")
    raw_owned = snapshot.get("owned")
    if (
        snapshot.get("schema_version") != 3
        or not isinstance(raw_present, dict)
        or not isinstance(raw_owned, list)
    ):
        raise errors.InstallError("legacy payload migration snapshot is invalid")
    owned = {owned_files.canonical_relative(value, "payload rollback") for value in raw_owned}
    metadata = set(owned_files.OWNED_PAYLOAD_METADATA)
    payload = owned - metadata
    if not payload and not raw_present:
        return LegacyProjectionSnapshot(present={}, owned=frozenset(owned))
    windows = inventory.WINDOWS_EXECUTABLE in payload
    if (
        len(owned) != len(raw_owned)
        or not metadata.issubset(owned)
        or not inventory.required_runtime_files(windows=windows).issubset(payload)
        or any(not inventory.is_runtime_file(relative, windows=windows) for relative in payload)
    ):
        raise errors.InstallError("legacy payload migration inventory is invalid")
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
            raise errors.InstallError(f"legacy payload migration metadata is invalid: {relative}")
        present[relative] = (metadata["sha256"], metadata["mode"])
    return LegacyProjectionSnapshot(present=present, owned=frozenset(owned))


def restore_legacy_projection(
    ctx: runtime_context.RuntimeContext,
    root: Path,
    *,
    candidate_paths: frozenset[str] = frozenset(),
) -> None:
    """Restore exact flat payload bytes after a failed legacy migration."""
    snapshot = load_legacy_snapshot(root)
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
    for relative in (snapshot.owned | candidate_paths) - snapshot.present.keys():
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
