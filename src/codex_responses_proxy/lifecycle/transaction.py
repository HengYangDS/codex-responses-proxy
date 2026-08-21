"""Source-side state machine for one admitted payload transaction.

The transaction consumes one admitted payload capability and coordinates the
candidate, rollback, projection, and journal owners. It owns only
state transitions and transaction-root cleanup; it does not reimplement those
collaborators or own installed manifest reads and purge.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import (
    artifact,
    command,
    owned_files,
    projection,
    runtime_spec,
    state,
)
from codex_responses_proxy.lifecycle import (
    candidate as payload_candidate,
)
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import (
    rollback as payload_rollback,
)
from codex_responses_proxy.service import digest, identity, inventory


def recover(
    ctx: runtime_context.RuntimeContext,
    *,
    runtime: Mapping[str, object] | None,
) -> dict[str, object]:
    """Close an unmutated transaction or restore one exact retained rollback."""

    journal = owned_files.read_canonical_json(
        state.journal_path(ctx), "payload transaction journal"
    )
    if journal.get("state") == "prepared":
        return _close_prepared(ctx, journal)
    return _rollback_recovery(ctx, journal=journal, runtime=runtime)


def _close_prepared(
    ctx: runtime_context.RuntimeContext, journal: Mapping[str, object]
) -> dict[str, object]:
    """Remove only a valid journal that proves no payload mutation began."""

    root = state.transaction_root(ctx)
    if tuple(root.iterdir()) != (state.journal_path(ctx),):
        raise errors.InstallError("prepared transaction is not empty")
    if (
        journal.get("schema_version") != state.TRANSACTION_JOURNAL_SCHEMA
        or not isinstance(journal.get("transaction_id"), str)
        or not isinstance(journal.get("version"), str)
        or not isinstance(journal.get("receipt_sha256"), str)
        or not isinstance(journal.get("fresh"), bool)
    ):
        raise errors.InstallError("payload recovery transaction is unavailable or invalid")
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "closed",
    }
    _remove_transaction_root(ctx)
    return result


def _rollback_recovery(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
    runtime: Mapping[str, object] | None,
) -> dict[str, object]:
    """Restore one exact retained transaction bound to its prior live runtime."""

    if (
        journal.get("schema_version") != state.TRANSACTION_JOURNAL_SCHEMA
        or journal.get("state") != "recovery_required"
        or not isinstance(journal.get("transaction_id"), str)
        or not isinstance(journal.get("version"), str)
    ):
        raise errors.InstallError("payload recovery transaction is unavailable or invalid")
    rollback = state.transaction_root(ctx) / "rollback"
    command_snapshot = command.read_snapshot(rollback)
    previous_executable = next(
        (
            rollback / relative
            for relative in (inventory.EXECUTABLE, inventory.WINDOWS_EXECUTABLE)
            if (rollback / relative).is_file()
        ),
        None,
    )
    previous = (
        identity.committed_payload(previous_executable) if previous_executable is not None else None
    )
    if previous is None:
        raise errors.InstallError("payload recovery rollback runtime identity is invalid")
    candidate = identity.committed_payload(Path(ctx.executable))
    if candidate is None:
        raise errors.InstallError("payload recovery candidate projection identity is invalid")
    if candidate.release != journal["version"] or candidate.release_receipt_sha256 != journal.get(
        "receipt_sha256"
    ):
        raise errors.InstallError("payload recovery candidate does not match the transaction")
    expected_runtime = previous.handoff()
    if (
        runtime is None
        or not identity.runtime_payload_matches(runtime, expected_runtime)
        or runtime.get("accepting") is not True
        or runtime.get("draining") is not False
        or runtime.get("handoff_state") not in {"idle", "serving", "finalized"}
    ):
        raise errors.InstallError("payload recovery runtime does not match the rollback projection")
    command.detach(Path(ctx.command), Path(ctx.executable), command_snapshot)
    payload_rollback.restore_snapshot(ctx, rollback)
    command.restore(Path(ctx.command), Path(ctx.executable), command_snapshot)
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "rolled_back",
    }
    _remove_transaction_root(ctx)
    return result


class PayloadTransaction:
    """Single-use owner of payload, receipt, state, journal, and rollback."""

    __slots__ = (
        "_blobs",
        "_ctx",
        "_fresh",
        "_receipt",
        "_receipt_sha256",
        "_state",
        "_transaction_id",
        "_version",
    )
    _TOKEN = object()
    _blobs: tuple[artifact.ArtifactFile, ...]
    _ctx: runtime_context.RuntimeContext
    _fresh: bool
    _receipt: Mapping[str, Any]
    _receipt_sha256: str
    _state: str
    _transaction_id: str
    _version: str

    def __init__(
        self,
        *,
        ctx: runtime_context.RuntimeContext,
        blobs: tuple[artifact.ArtifactFile, ...],
        version: str,
        receipt_sha256: str,
        receipt: Mapping[str, Any],
        transaction_id: str,
        fresh: bool,
        _token: object | None = None,
    ) -> None:
        """Construct a transaction through the private admission token."""
        if _token is not self._TOKEN:
            raise TypeError("PayloadTransaction is sealed; use begin_transaction()")
        self._ctx = ctx
        self._blobs = blobs
        self._version = version
        self._receipt_sha256 = receipt_sha256
        self._receipt = receipt
        self._transaction_id = transaction_id
        self._fresh = fresh
        self._state = "prepared"

    @property
    def release(self) -> str:
        """Return the candidate strict release version."""

        return self._version

    @property
    def receipt_sha256(self) -> str:
        """Return the candidate canonical receipt digest."""

        return self._receipt_sha256

    @property
    def expected(self) -> dict[str, object]:
        """Return source-side successor identity for lifecycle proof."""
        manifest = payload_candidate.manifest_for(self._version, self._blobs, self._receipt_sha256)
        return {
            "transaction_id": self._transaction_id,
            "release": self._version,
            "manifest_sha256": hashlib.sha256(projection.manifest_bytes(manifest)).hexdigest(),
            "serving_payload_sha256": manifest["serving_payload_sha256"],
            "release_receipt_sha256": self._receipt_sha256,
        }

    def commit_projection(self) -> None:
        """Install candidate bytes and pending provenance while retaining rollback."""

        if self._state != "prepared":
            raise errors.InstallError("payload transaction is not prepared")
        rollback = state.transaction_root(self._ctx) / "rollback"
        rollback.mkdir(mode=0o700)
        mutated = False
        try:
            command_snapshot = command.snapshot(Path(self._ctx.command), Path(self._ctx.executable))
            snapshot = payload_rollback.write_snapshot(self._ctx, rollback)
            command.write_snapshot(rollback, command_snapshot)
            candidate_paths = {blob.path for blob in self._blobs}
            payload_candidate.reject_unowned_collisions(self._ctx, snapshot.owned, candidate_paths)
            mutated = True
            payload_candidate.write_projection(
                self._ctx,
                self._blobs,
                self._version,
                self._receipt,
                self._receipt_sha256,
            )
            runtime_spec.write(self._ctx)
            payload_candidate.retire_previous_projection(
                self._ctx,
                snapshot.owned,
                candidate_paths,
            )
            command.project(
                Path(self._ctx.command),
                Path(self._ctx.executable),
                previous=command_snapshot,
            )
            ok, detail = projection.verify_payload_manifest(self._ctx)
            if not ok:
                raise errors.InstallError(f"committed payload integrity check failed: {detail}")
            payload_candidate.prewarm(Path(self._ctx.executable))
            self._state = "committed"
            state.write_journal(
                self._ctx,
                transaction_id=self._transaction_id,
                version=self._version,
                receipt_sha256=self._receipt_sha256,
                state=self._state,
                fresh=self._fresh,
            )
        except BaseException as exc:
            if not mutated or not (rollback / "snapshot.json").exists():
                self._state = "rolled_back"
                _remove_transaction_root(self._ctx)
            else:
                try:
                    self.rollback()
                except errors.InstallError as rollback_exc:
                    raise errors.InstallError(
                        f"payload commit failed and rollback failed: {rollback_exc}"
                    ) from exc
            raise

    def finalize(self, runtime: Mapping[str, object] | None = None) -> None:
        """Record installation success only after the caller proves SERVING."""

        if self._state != "committed":
            raise errors.InstallError("payload transaction is not committed")
        installed = {
            "schema_version": state.INSTALLED_RELEASE_STATE_SCHEMA,
            "version": self._version,
            "receipt_sha256": self._receipt_sha256,
            "transaction_id": self._transaction_id,
            "command": self._ctx.command,
            "runtime": dict(runtime or {}),
        }
        owned_files.write_bytes(
            state.installed_path(self._ctx),
            digest.canonical_json(installed),
            mode=0o600,
        )
        self._state = "finalized"
        _remove_transaction_root(self._ctx)

    def rollback(self) -> None:
        """Restore the exact prior payload, receipt, state, or their absence."""

        if self._state == "rolled_back":
            return
        rollback = state.transaction_root(self._ctx) / "rollback"
        if rollback.exists():
            command_snapshot = command.read_snapshot(rollback)
            command.detach(Path(self._ctx.command), Path(self._ctx.executable), command_snapshot)
            payload_rollback.restore_snapshot(
                self._ctx,
                rollback,
                candidate_paths=frozenset(blob.path for blob in self._blobs),
            )
            command.restore(Path(self._ctx.command), Path(self._ctx.executable), command_snapshot)
        elif self._fresh:
            payload_candidate.remove_projection(self._ctx, {blob.path for blob in self._blobs})
        self._state = "rolled_back"
        _remove_transaction_root(self._ctx)

    def rollback_if_prepared(self) -> bool:
        """Close the transaction only before any projection mutation begins."""

        if self._state != "prepared":
            return False
        self.rollback()
        return True

    def preserve_for_recovery(self, reason: str) -> None:
        """Keep committed bytes and rollback while marking an unknown outcome."""

        if self._state != "committed":
            raise errors.InstallError("only a committed transaction can require recovery")
        self._state = "recovery_required"
        state.write_journal(
            self._ctx,
            transaction_id=self._transaction_id,
            version=self._version,
            receipt_sha256=self._receipt_sha256,
            state=self._state,
            fresh=self._fresh,
            reason=reason,
        )


def begin_transaction(
    ctx: runtime_context.RuntimeContext,
    candidate: artifact.VerifiedArtifact,
) -> PayloadTransaction:
    """Claim one admitted release and create its private transaction journal."""

    root = state.transaction_root(ctx)
    if root.exists() or root.is_symlink():
        raise errors.InstallError(f"payload transaction path already exists: {root}")
    try:
        blobs, version, receipt_sha256, receipt, _sidecar = artifact.claim(candidate)
    except artifact.ArtifactError as exc:
        raise errors.InstallError(str(exc)) from exc
    payload_candidate.validate(blobs, version, receipt_sha256, receipt)
    previous = state.read_installed(ctx)
    if previous is not None:
        comparison = state.compare_versions(version, state.require_version(previous))
        if comparison < 0:
            raise errors.InstallError("released payload downgrade is refused")
        if comparison == 0:
            raise errors.InstallError("released payload replay is refused")
    fresh = previous is None and not Path(ctx.install_dir).exists()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    transaction_id = uuid.uuid4().hex
    state.write_journal(
        ctx,
        transaction_id=transaction_id,
        version=version,
        receipt_sha256=receipt_sha256,
        state="prepared",
        fresh=fresh,
    )
    return PayloadTransaction(
        ctx=ctx,
        blobs=blobs,
        version=version,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        transaction_id=transaction_id,
        fresh=fresh,
        _token=PayloadTransaction._TOKEN,
    )


def _remove_transaction_root(ctx: runtime_context.RuntimeContext) -> None:
    root = state.transaction_root(ctx)
    if not root.exists():
        return
    try:
        shutil.rmtree(root)
    except OSError as exc:
        raise errors.InstallError(f"payload transaction cleanup failed: {exc}") from exc
    if root.exists():
        raise errors.InstallError("payload transaction cleanup did not remove the transaction")
