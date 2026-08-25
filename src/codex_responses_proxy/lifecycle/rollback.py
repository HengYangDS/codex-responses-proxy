"""Exact snapshot and restoration of the current installed payload."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.json_value import ReadOnlyJsonObject
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import state
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory


@dataclass(frozen=True)
class RollbackInventory:
    """Verified content retained for rollback."""

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


RETAINED_BINDING_FILENAME = "generation.json"
RETAINED_BINDING_SCHEMA = 1


def write_snapshot(ctx: runtime_context.RuntimeContext, root: Path) -> RollbackInventory:
    """Persist the exact current payload, or its complete absence."""
    install = Path(ctx.install_dir)
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
    owned_files.write_bytes(root / "snapshot.json", digest.canonical_json(raw), mode=0o600)
    return read_inventory(raw)


def load_inventory(root: Path) -> RollbackInventory:
    """Load and verify a retained rollback inventory."""
    return read_inventory(
        owned_files.read_canonical_json(root / "snapshot.json", "payload rollback snapshot")
    )


def promote(
    ctx: runtime_context.RuntimeContext,
    source: Path,
    *,
    transaction_id: str,
    successor: Mapping[str, object],
) -> None:
    """Idempotently promote one transaction snapshot to retained authority."""
    current = _require_successor(ctx, successor, transaction_id)
    root = state.retained_rollback_root(ctx)
    generations = root / "generations"
    if root.is_symlink() or generations.is_symlink():
        raise errors.InstallError("retained rollback root is a symbolic link")
    generations.mkdir(parents=True, exist_ok=True, mode=0o700)
    generation = generations / transaction_id
    _materialize_generation(source, generation, transaction_id, current)
    _load_generation(ctx, generation, transaction_id)
    _select_generation(ctx, transaction_id)
    _remove_superseded_generations(ctx, generation)
    _require_selected_generation(ctx, generation)


def _require_successor(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    transaction_id: str,
) -> identity.LoadedPayloadIdentity:
    """Return the live successor bound to this exact finalization transaction."""
    current = identity.committed_payload(Path(ctx.executable))
    installed = state.read_installed(ctx)
    if (
        current is None
        or installed is None
        or installed.get("transaction_id") != transaction_id
        or any(expected.get(field) != value for field, value in current.handoff().items())
    ):
        raise errors.InstallError("retained rollback successor identity is invalid")
    return current


def _materialize_generation(
    source: Path,
    generation: Path,
    generation_name: str,
    successor: identity.LoadedPayloadIdentity,
) -> None:
    """Move a verified transaction snapshot once, or accept its exact moved form."""
    source_present = source.is_dir() and not source.is_symlink()
    generation_present = generation.is_dir() and not generation.is_symlink()
    if source_present == generation_present:
        raise errors.InstallError("retained rollback generation source is ambiguous")
    if not source_present:
        if (
            source.exists()
            or source.is_symlink()
            or (generation.exists() and not generation_present)
        ):
            raise errors.InstallError("retained rollback generation source is invalid")
        return
    predecessor = _snapshot_identity(source)
    command.read_snapshot(source)
    load_inventory(source)
    binding = {
        "schema_version": RETAINED_BINDING_SCHEMA,
        "generation": generation_name,
        "predecessor": predecessor.handoff(),
        "successor": successor.handoff(),
    }
    owned_files.write_bytes(
        source / RETAINED_BINDING_FILENAME,
        digest.canonical_json(binding),
        mode=0o600,
        root=source,
    )
    try:
        os.replace(source, generation)
    except OSError as exc:
        raise errors.InstallError("retained rollback generation move failed") from exc


def _select_generation(ctx: runtime_context.RuntimeContext, generation_name: str) -> None:
    """Atomically select the fully verified retained generation."""
    root = state.retained_rollback_root(ctx)
    owned_files.write_bytes(
        state.retained_rollback_pointer(ctx),
        digest.canonical_json(
            {"schema_version": RETAINED_BINDING_SCHEMA, "generation": generation_name}
        ),
        mode=0o600,
        root=root,
    )


def _remove_superseded_generations(ctx: runtime_context.RuntimeContext, selected: Path) -> None:
    """Remove only generations superseded by the durable selector."""
    try:
        for generation in state.retained_generations(ctx):
            if generation != selected:
                if generation.is_symlink() or not generation.is_dir():
                    raise errors.InstallError("retained rollback generation set is invalid")
                shutil.rmtree(generation)
    except errors.InstallError:
        raise
    except OSError as exc:
        raise errors.InstallError("retained rollback generation cleanup failed") from exc


def _require_selected_generation(ctx: runtime_context.RuntimeContext, selected: Path) -> None:
    """Prove the retained store converged to one selected generation."""
    if (
        selected.is_symlink()
        or not selected.is_dir()
        or state.retained_generations(ctx) != (selected,)
    ):
        raise errors.InstallError("retained rollback generation cleanup is incomplete")
    retained = load_retained(ctx)
    if retained.root != selected:
        raise errors.InstallError("retained rollback generation selection is incomplete")


def remove_retained(ctx: runtime_context.RuntimeContext) -> None:
    """Remove the product-owned retained store when no predecessor can exist."""
    root = state.retained_rollback_root(ctx)
    if root.is_symlink():
        raise errors.InstallError("retained rollback root is a symbolic link")
    if root.exists():
        shutil.rmtree(root)


def load_retained(ctx: runtime_context.RuntimeContext) -> RetainedRollback:
    """Load and verify the sole predecessor bound to the live successor."""
    root = state.retained_rollback_root(ctx)
    if root.is_symlink() or not root.is_dir():
        raise errors.InstallError("retained rollback root is unavailable or invalid")
    pointer_path = state.retained_rollback_pointer(ctx)
    if pointer_path.is_symlink() or not pointer_path.is_file():
        raise errors.InstallError("retained rollback pointer is unavailable or invalid")
    pointer = owned_files.read_canonical_json(pointer_path, "retained rollback pointer")
    generation_name = pointer.get("generation")
    if (
        pointer.get("schema_version") != RETAINED_BINDING_SCHEMA
        or not isinstance(generation_name, str)
        or not generation_name
        or any(character not in "0123456789abcdef" for character in generation_name)
    ):
        raise errors.InstallError("retained rollback pointer is invalid")
    generation = root / "generations" / generation_name
    if generation.is_symlink() or not generation.is_dir():
        raise errors.InstallError("retained rollback generation is unavailable or invalid")
    if state.retained_generations(ctx) != (generation,):
        raise errors.InstallError("retained rollback generation set is invalid")
    return _load_generation(ctx, generation, generation_name)


def _load_generation(
    ctx: runtime_context.RuntimeContext,
    generation: Path,
    generation_name: str,
) -> RetainedRollback:
    """Verify one exact retained generation independent of pointer cleanup."""
    if generation.is_symlink() or not generation.is_dir():
        raise errors.InstallError("retained rollback generation is unavailable or invalid")
    binding = owned_files.read_canonical_json(
        generation / RETAINED_BINDING_FILENAME, "retained rollback generation"
    )
    predecessor = _snapshot_identity(generation)
    successor = identity.committed_payload(Path(ctx.executable))
    installed = state.read_installed(ctx)
    if successor is None or installed is None:
        raise errors.InstallError("retained rollback successor is unavailable")
    if (
        binding.get("schema_version") != RETAINED_BINDING_SCHEMA
        or binding.get("generation") != generation_name
        or binding.get("predecessor") != predecessor.handoff()
        or binding.get("successor") != successor.handoff()
        or installed.get("transaction_id") != generation_name
        or installed.get("version") != successor.release
        or installed.get("receipt_sha256") != successor.release_receipt_sha256
        or installed.get("command") != ctx.command
    ):
        raise errors.InstallError("retained rollback generation binding is invalid")
    command.read_snapshot(generation)
    load_inventory(generation)
    return RetainedRollback(generation, predecessor, successor)


def load_retained_or_none(
    ctx: runtime_context.RuntimeContext,
) -> RetainedRollback | None:
    """Return the retained predecessor, distinguishing clean absence from corruption."""
    root = state.retained_rollback_root(ctx)
    if not root.exists() and not root.is_symlink():
        return None
    return load_retained(ctx)


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


def candidate(retained: RetainedRollback) -> artifact.VerifiedArtifact:
    """Mint one process-local artifact capability from a verified predecessor."""
    receipt = owned_files.read_canonical_json(
        retained.root / inventory.RELEASE_RECEIPT_FILENAME,
        "retained rollback release receipt",
    )
    entries = receipt.get("payload")
    if not isinstance(entries, list):
        raise errors.InstallError("retained rollback release receipt is invalid")
    blobs: list[artifact.ArtifactFile] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise errors.InstallError("retained rollback release receipt is invalid")
        relative = entry.get("path")
        mode = entry.get("mode")
        blob_oid = entry.get("blob_oid")
        sha256 = entry.get("sha256")
        if (
            not isinstance(relative, str)
            or mode not in {"100644", "100755"}
            or not isinstance(blob_oid, str)
            or not isinstance(sha256, str)
        ):
            raise errors.InstallError("retained rollback release receipt is invalid")
        source = owned_files.regular_file(retained.root, relative, "retained rollback")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise errors.InstallError(f"retained rollback digest mismatch: {relative}")
        blobs.append(artifact.ArtifactFile(relative, mode, blob_oid, sha256, content))
    receipt_sha256 = hashlib.sha256(digest.canonical_json(receipt)).hexdigest()
    return artifact.mint(
        tuple(blobs),
        receipt,
        {
            "schema_version": artifact.RECEIPT_SCHEMA,
            "algorithm": "sha256",
            "receipt_sha256": receipt_sha256,
            "serving_payload_sha256": receipt.get("serving_payload_sha256"),
        },
    )


def _snapshot_identity(root: Path) -> identity.LoadedPayloadIdentity:
    executable = next(
        (
            root / relative
            for relative in (inventory.EXECUTABLE, inventory.WINDOWS_EXECUTABLE)
            if (root / relative).is_file() and not (root / relative).is_symlink()
        ),
        None,
    )
    loaded = identity.committed_payload(executable) if executable is not None else None
    if loaded is None:
        raise errors.InstallError("retained rollback predecessor identity is invalid")
    return loaded


def read_inventory(snapshot: ReadOnlyJsonObject) -> RollbackInventory:
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
    metadata = set(owned_files.OWNED_PAYLOAD_METADATA)
    payload = owned - metadata
    if not payload and not raw_present:
        return RollbackInventory(present={}, owned=frozenset(owned))
    windows = inventory.WINDOWS_EXECUTABLE in payload
    if (
        len(owned) != len(raw_owned)
        or not metadata.issubset(owned)
        or not inventory.required_runtime_files(windows=windows).issubset(payload)
        or any(not inventory.is_runtime_file(relative, windows=windows) for relative in payload)
    ):
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


def restore_snapshot(
    ctx: runtime_context.RuntimeContext,
    root: Path,
    *,
    candidate_paths: frozenset[str] = frozenset(),
) -> None:
    """Restore retained bytes and remove candidate files absent beforehand."""
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
