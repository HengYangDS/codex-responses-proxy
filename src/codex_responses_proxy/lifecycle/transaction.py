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
from collections.abc import Callable
from collections.abc import Mapping
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.json_value import ReadOnlyJsonObject
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import candidate as payload_candidate
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle import state
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory


def recover(
    ctx: runtime_context.RuntimeContext,
    *,
    runtime: Mapping[str, object] | None,
    bind_terminal: Callable[[runtime_context.RuntimeContext], None],
) -> dict[str, object]:
    """Recover one transaction and bind its terminal runtime before closing it."""
    root = state.transaction_root(ctx)
    if not root.exists() and not root.is_symlink():
        return {"state": "not_required"}
    try:
        journal = state.read_journal(ctx)
    except errors.InstallError as exc:
        raise errors.RecoveryStateError(str(exc)) from exc
    phase = str(journal.get("phase") or journal["state"])
    if phase == "prepared":
        return _close_prepared(ctx, journal)
    candidate = _recovery_candidate(ctx, journal)
    if phase == "materialized" and not _runtime_matches_projection(runtime, candidate):
        return _rollback_materialized(
            ctx,
            journal=journal,
            candidate=candidate,
            runtime=runtime,
            bind_terminal=bind_terminal,
        )
    installed = state.read_installed(ctx)
    if installed is not None and _installed_matches_transaction(
        installed,
        journal=journal,
        candidate=candidate,
        command_path=ctx.command,
    ):
        return _close_finalized(
            ctx,
            journal=journal,
            bind_terminal=bind_terminal,
        )
    if _runtime_matches_projection(runtime, candidate):
        if phase == "materialized":
            rollback = state.transaction_root(ctx) / "rollback"
            generation.select(
                ctx,
                active=str(journal["transaction_id"]),
                predecessor=(
                    str(journal["previous_generation"])
                    if journal.get("previous_generation") is not None
                    and generation.path(ctx, str(journal["previous_generation"])).is_dir()
                    else None
                ),
            )
            command.project(
                Path(ctx.command),
                Path(generation.control_context(ctx).executable),
                previous=command.read_snapshot(rollback),
            )
        return _finalize_recovery(
            ctx,
            journal=journal,
            runtime=runtime,
            bind_terminal=bind_terminal,
        )
    if journal["fresh"] is True:
        if runtime is not None:
            raise errors.InstallError(
                "payload recovery runtime does not match the candidate projection"
            )
        return _rollback_materialized(
            ctx,
            journal=journal,
            candidate=candidate,
            runtime=runtime,
            bind_terminal=bind_terminal,
        )
    return _rollback_upgrade(
        ctx,
        journal=journal,
        runtime=runtime,
        bind_terminal=bind_terminal,
    )


def _close_prepared(
    ctx: runtime_context.RuntimeContext, journal: Mapping[str, object]
) -> dict[str, object]:
    """Remove only a valid journal that proves no payload mutation began."""
    root = state.transaction_root(ctx)
    if tuple(root.iterdir()) != (state.journal_path(ctx),):
        raise errors.RecoveryStateError("prepared transaction contains unowned content")
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "closed",
    }
    _remove_transaction_root(ctx)
    return result


def _recovery_candidate(
    ctx: runtime_context.RuntimeContext,
    journal: Mapping[str, object],
) -> identity.LoadedPayloadIdentity:
    """Verify one mutated transaction and its exact candidate projection."""
    candidate_ctx = generation.context(ctx, str(journal["transaction_id"]))
    candidate = identity.committed_payload(Path(candidate_ctx.executable))
    if candidate is None:
        raise errors.RecoveryStateError("payload recovery candidate projection identity is invalid")
    if candidate.release != journal["version"] or candidate.release_receipt_sha256 != journal.get(
        "receipt_sha256"
    ):
        raise errors.RecoveryStateError("payload recovery candidate does not match the transaction")
    return candidate


def _close_finalized(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
    bind_terminal: Callable[[runtime_context.RuntimeContext], None],
) -> dict[str, object]:
    """Remove transaction residue only after finalized state proves the candidate."""
    selection = _select_retention(ctx, journal=journal)
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "finalized",
    }
    bind_terminal(generation.control_context(ctx))
    generation.prune(ctx, selection)
    _remove_transaction_root(ctx)
    return result


def _installed_matches_transaction(
    installed: Mapping[str, object],
    *,
    journal: Mapping[str, object],
    candidate: identity.LoadedPayloadIdentity,
    command_path: str,
) -> bool:
    """Return whether finalized state proves this exact candidate transaction."""
    return (
        installed.get("transaction_id") == journal["transaction_id"]
        and installed.get("version") == candidate.release
        and installed.get("receipt_sha256") == candidate.release_receipt_sha256
        and installed.get("command") == command_path
    )


def _runtime_matches_projection(
    runtime: Mapping[str, object] | None,
    projection: identity.LoadedPayloadIdentity,
) -> bool:
    """Return whether one accepting runtime serves the verified projection."""
    return (
        runtime is not None
        and identity.runtime_payload_matches(runtime, projection.handoff())
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
        and runtime.get("handoff_state") in {"idle", "serving", "finalized"}
    )


def _finalize_recovery(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
    runtime: Mapping[str, object] | None,
    bind_terminal: Callable[[runtime_context.RuntimeContext], None],
) -> dict[str, object]:
    """Finalize an installed candidate after its runtime proves success."""
    assert runtime is not None
    installed = {
        "schema_version": state.INSTALLED_RELEASE_STATE_SCHEMA,
        "version": journal["version"],
        "receipt_sha256": journal["receipt_sha256"],
        "transaction_id": journal["transaction_id"],
        "command": ctx.command,
        "runtime": dict(runtime),
    }
    owned_files.write_bytes(
        state.installed_path(ctx),
        digest.canonical_json(installed),
        mode=0o600,
    )
    selection = _select_retention(ctx, journal=journal)
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "finalized",
    }
    bind_terminal(generation.control_context(ctx))
    generation.prune(ctx, selection)
    _remove_transaction_root(ctx)
    return result


def _select_retention(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
) -> generation.Selection:
    """Select final retained generations without pruning recovery material."""
    try:
        active = str(journal["transaction_id"])
        previous_generation = journal.get("previous_generation")
        if journal["fresh"] is True or previous_generation is None:
            selection = generation.Selection(active, None)
        else:
            previous = str(previous_generation)
            rollback = state.transaction_root(ctx) / "rollback"
            legacy_snapshot = payload_rollback.legacy_snapshot_path(rollback)
            if legacy_snapshot.is_file():
                legacy_inventory = payload_rollback.load_legacy_snapshot(rollback)
                generation.materialize_legacy_projection(
                    ctx,
                    rollback,
                    previous,
                    legacy_inventory.present,
                )
                generation.retire_legacy_projection(
                    Path(ctx.install_dir),
                    legacy_inventory.present,
                )
            elif not generation.path(ctx, previous).is_dir():
                raise errors.InstallError("predecessor payload generation is unavailable")
            selection = generation.Selection(active, previous)
        generation.select(ctx, active=selection.active, predecessor=selection.predecessor)
        return selection
    except errors.InstallError as exc:
        state.write_journal(
            ctx,
            transaction_id=str(journal["transaction_id"]),
            version=str(journal["version"]),
            receipt_sha256=str(journal["receipt_sha256"]),
            state="recovery_required",
            fresh=bool(journal["fresh"]),
            previous_generation=(
                str(journal["previous_generation"])
                if journal.get("previous_generation") is not None
                else None
            ),
            previous_predecessor=(
                str(journal["previous_predecessor"])
                if journal.get("previous_predecessor") is not None
                else None
            ),
            phase="activated",
            reason=f"finalization failed: {exc}",
        )
        raise


def _rollback_materialized(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
    candidate: identity.LoadedPayloadIdentity,
    runtime: Mapping[str, object] | None,
    bind_terminal: Callable[[runtime_context.RuntimeContext], None],
) -> dict[str, object]:
    """Discard a candidate that never became the proven serving runtime."""
    previous_generation_value = journal.get("previous_generation")
    previous_generation = (
        str(previous_generation_value) if previous_generation_value is not None else None
    )
    selection = generation.read(ctx)
    candidate_generation = str(journal["transaction_id"])
    expected_before = (
        generation.Selection(
            previous_generation,
            (
                str(journal["previous_predecessor"])
                if journal.get("previous_predecessor") is not None
                else None
            ),
        )
        if previous_generation is not None
        else None
    )
    selected_candidate = generation.Selection(candidate_generation, previous_generation)
    if selection not in {expected_before, selected_candidate}:
        raise errors.RecoveryStateError("materialized recovery selection changed")
    if selection == expected_before and _reuses_retained_generation(journal):
        assert previous_generation is not None
        _require_unchanged_prior_terminal(
            ctx,
            generation_id=previous_generation,
            runtime=runtime,
        )
        result = {
            "transaction_id": journal["transaction_id"],
            "version": candidate.release,
            "state": "rolled_back",
        }
        _remove_transaction_root(ctx)
        return result
    rollback = state.transaction_root(ctx) / "rollback"
    command_snapshot = command.read_snapshot(rollback)
    if selection == selected_candidate:
        command.detach(
            Path(ctx.command),
            Path(generation.context(ctx, candidate_generation).executable),
            command_snapshot,
        )
        if expected_before is None:
            generation.clear(ctx)
        else:
            generation.select(
                ctx,
                active=expected_before.active,
                predecessor=expected_before.predecessor,
            )
            command.restore(
                Path(ctx.command),
                Path(generation.control_context(ctx).executable),
                command_snapshot,
            )
    if expected_before is not None:
        bind_terminal(generation.control_context(ctx))
    if not _reuses_retained_generation(journal):
        generation.remove(ctx, candidate_generation)
    generations = generation.root(ctx)
    if generations.is_dir() and not any(generations.iterdir()):
        generations.rmdir()
    install = Path(ctx.install_dir)
    if journal["fresh"] is True and install.is_dir() and not any(install.iterdir()):
        install.rmdir()
    result = {
        "transaction_id": journal["transaction_id"],
        "version": candidate.release,
        "state": "rolled_back",
    }
    _remove_transaction_root(ctx)
    return result


def _require_unchanged_prior_terminal(
    ctx: runtime_context.RuntimeContext,
    *,
    generation_id: str,
    runtime: Mapping[str, object] | None,
) -> None:
    """Prove the unselected reverse candidate changed no terminal authority."""
    prior_ctx = generation.context(ctx, generation_id)
    prior = identity.committed_payload(Path(prior_ctx.executable))
    if prior is None:
        raise errors.RecoveryStateError(
            "payload recovery prior selected generation identity is invalid"
        )
    try:
        installed = state.read_installed(ctx)
        installed_command = state.require_command(installed) if installed is not None else None
    except errors.InstallError as exc:
        raise errors.RecoveryStateError(str(exc)) from exc
    if installed is None or not (
        installed.get("transaction_id") == generation_id
        and installed.get("version") == prior.release
        and installed.get("receipt_sha256") == prior.release_receipt_sha256
    ):
        raise errors.RecoveryStateError(
            "payload recovery installed state does not match the prior selected generation"
        )
    if (
        installed_command != ctx.command
        or command.status(Path(installed_command), Path(prior_ctx.executable)).get("state")
        != "owned"
    ):
        raise errors.RecoveryStateError(
            "payload recovery command does not match the prior selected generation"
        )
    if not _runtime_matches_projection(runtime, prior):
        raise errors.RecoveryStateError(
            "payload recovery runtime does not match the prior selected generation"
        )


def _rollback_upgrade(
    ctx: runtime_context.RuntimeContext,
    *,
    journal: Mapping[str, object],
    runtime: Mapping[str, object] | None,
    bind_terminal: Callable[[runtime_context.RuntimeContext], None],
) -> dict[str, object]:
    """Restore one exact retained upgrade bound to its prior live runtime."""
    rollback = state.transaction_root(ctx) / "rollback"
    command_snapshot = command.read_snapshot(rollback)
    if _reuses_retained_generation(journal):
        previous_generation = str(journal["previous_generation"])
        previous_ctx = generation.context(ctx, previous_generation)
        previous = identity.committed_payload(Path(previous_ctx.executable))
        if previous is None or not _runtime_matches_projection(runtime, previous):
            raise errors.RecoveryStateError(
                "payload recovery runtime does not match the prior selected generation"
            )
        selection = generation.Selection(
            previous_generation,
            str(journal["transaction_id"]),
        )
        command.detach(
            Path(ctx.command),
            Path(generation.context(ctx, str(journal["transaction_id"])).executable),
            command_snapshot,
        )
        generation.select(ctx, active=selection.active, predecessor=selection.predecessor)
        command.restore(
            Path(ctx.command),
            Path(generation.control_context(ctx).executable),
            command_snapshot,
        )
        result = {
            "transaction_id": journal["transaction_id"],
            "version": journal["version"],
            "state": "rolled_back",
        }
        bind_terminal(generation.control_context(ctx))
        _remove_transaction_root(ctx)
        return result
    previous_generation = journal.get("previous_generation")
    selection = generation.read(ctx)
    restored = (
        generation.Selection(
            str(previous_generation),
            (
                str(journal["previous_predecessor"])
                if journal.get("previous_predecessor") is not None
                else None
            ),
        )
        if previous_generation is not None
        else None
    )
    if (
        restored is not None
        and selection is not None
        and selection
        in {
            generation.Selection(str(journal["transaction_id"]), str(previous_generation)),
            restored,
        }
        and generation.path(ctx, restored.active).is_dir()
    ):
        previous_ctx = generation.context(ctx, restored.active)
        previous = identity.committed_payload(Path(previous_ctx.executable))
        if previous is None or not _runtime_matches_projection(runtime, previous):
            raise errors.RecoveryStateError(
                "payload recovery runtime does not match the prior selected generation"
            )
        if selection != restored:
            command.detach(
                Path(ctx.command),
                Path(generation.context(ctx, str(journal["transaction_id"])).executable),
                command_snapshot,
            )
            generation.select(
                ctx,
                active=restored.active,
                predecessor=restored.predecessor,
            )
            command.restore(
                Path(ctx.command),
                Path(generation.control_context(ctx).executable),
                command_snapshot,
            )
        bind_terminal(generation.control_context(ctx))
        generation.remove(ctx, str(journal["transaction_id"]))
        result = {
            "transaction_id": journal["transaction_id"],
            "version": journal["version"],
            "state": "rolled_back",
        }
        _remove_transaction_root(ctx)
        return result
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
        raise errors.RecoveryStateError("payload recovery rollback runtime identity is invalid")
    if not _runtime_matches_projection(runtime, previous):
        raise errors.RecoveryStateError(
            "payload recovery runtime does not match the rollback projection"
        )
    command.detach(
        Path(ctx.command),
        Path(generation.context(ctx, str(journal["transaction_id"])).executable),
        command_snapshot,
    )
    generation.clear(ctx)
    payload_rollback.restore_legacy_projection(
        ctx,
        rollback,
        candidate_paths=owned_files.current_inventory(Path(ctx.install_dir)),
    )
    command.restore(Path(ctx.command), Path(ctx.executable), command_snapshot)
    bind_terminal(generation.control_context(ctx))
    generation.remove(ctx, str(journal["transaction_id"]))
    result = {
        "transaction_id": journal["transaction_id"],
        "version": journal["version"],
        "state": "rolled_back",
    }
    _remove_transaction_root(ctx)
    return result


def _reuses_retained_generation(journal: Mapping[str, object]) -> bool:
    """Return whether a reverse transition targets the selected predecessor itself."""
    return journal.get("transaction_id") == journal.get("previous_predecessor")


class PayloadTransaction:
    """Single-use owner of payload, receipt, state, journal, and rollback."""

    __slots__ = (
        "_blobs",
        "_candidate_ctx",
        "_ctx",
        "_fresh",
        "_previous_generation",
        "_previous_predecessor",
        "_previous_selection",
        "_receipt",
        "_receipt_sha256",
        "_retained_identity",
        "_reuse_generation",
        "_state",
        "_transaction_id",
        "_version",
    )
    _TOKEN = object()
    _blobs: tuple[artifact.ArtifactFile, ...]
    _ctx: runtime_context.RuntimeContext
    _fresh: bool
    _receipt: ReadOnlyJsonObject
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
        receipt: ReadOnlyJsonObject,
        transaction_id: str,
        fresh: bool,
        previous_generation: str | None,
        reuse_generation: bool = False,
        retained_identity: identity.LoadedPayloadIdentity | None = None,
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
        self._candidate_ctx = generation.context(ctx, transaction_id)
        self._reuse_generation = reuse_generation
        self._retained_identity = retained_identity
        self._previous_generation = previous_generation
        self._previous_selection = generation.read(ctx)
        if reuse_generation and (
            self._previous_selection is None
            or self._previous_selection.predecessor != transaction_id
        ):
            raise errors.InstallError("retained rollback selection changed before transition")
        self._previous_predecessor = (
            self._previous_selection.predecessor if self._previous_selection is not None else None
        )

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
        if self._retained_identity is not None:
            return {
                "transaction_id": self._transaction_id,
                **self._retained_identity.handoff(),
            }
        manifest = payload_candidate.manifest_for(self._version, self._blobs, self._receipt_sha256)
        return {
            "transaction_id": self._transaction_id,
            "release": self._version,
            "manifest_sha256": hashlib.sha256(projection.manifest_bytes(manifest)).hexdigest(),
            "serving_payload_sha256": manifest["serving_payload_sha256"],
            "release_receipt_sha256": self._receipt_sha256,
        }

    @property
    def context(self) -> runtime_context.RuntimeContext:
        """Return the immutable candidate runtime context."""
        return self._candidate_ctx

    def commit_projection(self) -> None:
        """Materialize one immutable candidate without changing the active generation."""
        if self._state != "prepared":
            raise errors.InstallError("payload transaction is not prepared")
        rollback = state.transaction_root(self._ctx) / "rollback"
        rollback.mkdir(mode=0o700)
        mutated = False
        try:
            if self._reuse_generation:
                candidate = identity.committed_payload(Path(self._candidate_ctx.executable))
                if candidate != self._retained_identity:
                    raise errors.InstallError(
                        "retained rollback predecessor changed before materialization"
                    )
            previous_ctx = (
                generation.context(self._ctx, self._previous_selection.active)
                if self._previous_selection is not None
                else self._ctx
            )
            control_ctx = generation.control_context(self._ctx)
            command_snapshot = command.snapshot(
                Path(self._ctx.command), Path(control_ctx.executable)
            )
            command.write_snapshot(rollback, command_snapshot)
            if self._reuse_generation:
                payload_candidate.prewarm(self._candidate_ctx)
                self._state = "materialized"
                self._write_journal()
                return
            if self._previous_selection is None:
                payload_rollback.write_legacy_snapshot(previous_ctx, rollback)
            candidate_paths = {blob.path for blob in self._blobs}
            payload_candidate.reject_unowned_collisions(
                self._candidate_ctx,
                frozenset(),
                candidate_paths,
            )
            mutated = True
            payload_candidate.write_projection(
                self._candidate_ctx,
                self._blobs,
                self._version,
                self._receipt,
                self._receipt_sha256,
            )
            runtime_spec.write(self._candidate_ctx)
            ok, detail = projection.verify_payload_manifest(self._candidate_ctx)
            if not ok:
                raise errors.InstallError(f"committed payload integrity check failed: {detail}")
            payload_candidate.prewarm(self._candidate_ctx)
            self._state = "materialized"
            self._write_journal()
        except BaseException as exc:
            if not mutated or not payload_rollback.legacy_snapshot_path(rollback).exists():
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

    def activate(self) -> None:
        """Atomically select and project the already materialized candidate."""
        if self._state != "materialized":
            raise errors.InstallError("payload transaction is not materialized")
        rollback = state.transaction_root(self._ctx) / "rollback"
        command_snapshot = command.read_snapshot(rollback)
        predecessor = (
            self._previous_selection.active if self._previous_selection is not None else None
        )
        generation.select(
            self._ctx,
            active=self._transaction_id,
            predecessor=predecessor,
        )
        control_ctx = generation.control_context(self._ctx)
        command.project(
            Path(self._ctx.command),
            Path(control_ctx.executable),
            previous=command_snapshot,
        )
        self._state = "activated"
        state.write_journal(
            self._ctx,
            transaction_id=self._transaction_id,
            version=self._version,
            receipt_sha256=self._receipt_sha256,
            state=self._state,
            fresh=self._fresh,
            previous_generation=self._previous_generation,
            previous_predecessor=self._previous_predecessor,
        )

    def finalize(self, runtime: Mapping[str, object] | None = None) -> None:
        """Record installation success only after the caller proves SERVING."""
        if self._state != "activated":
            raise errors.InstallError("payload transaction is not activated")
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
        rollback = state.transaction_root(self._ctx) / "rollback"
        try:
            if self._reuse_generation:
                assert self._previous_generation is not None
                selection = generation.Selection(
                    self._transaction_id,
                    self._previous_generation,
                )
            elif self._fresh:
                selection = generation.Selection(self._transaction_id, None)
            elif self._previous_selection is not None:
                selection = generation.Selection(
                    self._transaction_id,
                    self._previous_selection.active,
                )
            else:
                assert self._previous_generation is not None
                legacy_inventory = payload_rollback.load_legacy_snapshot(rollback)
                generation.materialize_legacy_projection(
                    self._ctx,
                    rollback,
                    self._previous_generation,
                    legacy_inventory.present,
                )
                generation.retire_legacy_projection(
                    Path(self._ctx.install_dir),
                    legacy_inventory.present,
                )
                selection = generation.Selection(
                    self._transaction_id,
                    self._previous_generation,
                )
            generation.select(
                self._ctx,
                active=selection.active,
                predecessor=selection.predecessor,
            )
        except errors.InstallError as exc:
            self.preserve_for_recovery(f"finalization failed: {exc}")
            raise
        self._state = "finalized"
        generation.prune(self._ctx, selection)
        _remove_transaction_root(self._ctx)

    def rollback(self) -> None:
        """Restore the exact prior payload, receipt, state, or their absence."""
        if self._state == "rolled_back":
            return
        rollback = state.transaction_root(self._ctx) / "rollback"
        if rollback.exists():
            command_snapshot = command.read_snapshot(rollback)
            if self._previous_selection is None:
                command.detach(
                    Path(self._ctx.command),
                    Path(self._candidate_ctx.executable),
                    command_snapshot,
                )
                generation.clear(self._ctx)
                if self._previous_generation is not None:
                    command.restore(
                        Path(self._ctx.command),
                        Path(self._ctx.executable),
                        command_snapshot,
                    )
            else:
                selection = generation.read(self._ctx)
                if selection is not None and selection.active == self._transaction_id:
                    command.detach(
                        Path(self._ctx.command),
                        Path(self._candidate_ctx.executable),
                        command_snapshot,
                    )
                generation.select(
                    self._ctx,
                    active=self._previous_selection.active,
                    predecessor=self._previous_selection.predecessor,
                )
                previous_executable = generation.control_context(self._ctx).executable
                command.restore(
                    Path(self._ctx.command),
                    Path(previous_executable),
                    command_snapshot,
                )
            if not self._reuse_generation:
                generation.remove(self._ctx, self._transaction_id)
        elif self._fresh:
            generation.remove(self._ctx, self._transaction_id)
        install_root = Path(self._ctx.install_dir)
        if self._fresh and install_root.is_dir() and not any(install_root.iterdir()):
            install_root.rmdir()
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
        if self._state not in {"materialized", "activated"}:
            raise errors.InstallError("only a materialized transaction can require recovery")
        phase = self._state
        self._state = "recovery_required"
        state.write_journal(
            self._ctx,
            transaction_id=self._transaction_id,
            version=self._version,
            receipt_sha256=self._receipt_sha256,
            state=self._state,
            fresh=self._fresh,
            previous_generation=self._previous_generation,
            previous_predecessor=(self._previous_predecessor),
            phase=phase,
            reason=reason,
        )

    def _write_journal(self) -> None:
        state.write_journal(
            self._ctx,
            transaction_id=self._transaction_id,
            version=self._version,
            receipt_sha256=self._receipt_sha256,
            state=self._state,
            fresh=self._fresh,
            previous_generation=self._previous_generation,
            previous_predecessor=self._previous_predecessor,
        )


def begin_transaction(
    ctx: runtime_context.RuntimeContext,
    candidate: artifact.VerifiedArtifact,
) -> PayloadTransaction:
    """Claim one admitted release and create its private transaction journal."""
    return _begin_transaction(ctx, candidate)


def begin_rollback_transaction(
    ctx: runtime_context.RuntimeContext,
    retained: payload_rollback.RetainedRollback,
) -> PayloadTransaction:
    """Begin one reverse transition from a verified retained predecessor."""
    previous = state.read_installed(ctx)
    if previous is None or state.require_version(previous) != retained.successor.release:
        raise errors.InstallError("retained rollback successor changed before transition")
    selection = generation.read(ctx)
    if selection is None or selection.predecessor is None:
        raise errors.InstallError("retained rollback selection changed before transition")
    predecessor_ctx = generation.context(ctx, selection.predecessor)
    if Path(predecessor_ctx.payload_dir) != retained.root:
        raise errors.InstallError("retained rollback predecessor changed before transition")
    _claim_transaction_root(ctx)
    state.write_journal(
        ctx,
        transaction_id=selection.predecessor,
        version=retained.predecessor.release,
        receipt_sha256=retained.predecessor.release_receipt_sha256,
        state="prepared",
        fresh=False,
        previous_generation=selection.active,
        previous_predecessor=selection.predecessor,
    )
    return PayloadTransaction(
        ctx=ctx,
        blobs=(),
        version=retained.predecessor.release,
        receipt_sha256=retained.predecessor.release_receipt_sha256,
        receipt={},
        transaction_id=selection.predecessor,
        fresh=False,
        previous_generation=selection.active,
        reuse_generation=True,
        retained_identity=retained.predecessor,
        _token=PayloadTransaction._TOKEN,
    )


def _begin_transaction(
    ctx: runtime_context.RuntimeContext,
    candidate: artifact.VerifiedArtifact,
) -> PayloadTransaction:
    """Claim one admitted payload for a forward transition."""
    try:
        blobs, version, receipt_sha256, receipt, _sidecar = artifact.claim(candidate)
    except artifact.ArtifactError as exc:
        raise errors.InstallError(str(exc)) from exc
    payload_candidate.validate(blobs, version, receipt_sha256, receipt)
    previous = state.read_installed(ctx)
    if previous is not None:
        control_identity = identity.committed_payload(
            Path(generation.control_context(ctx).executable)
        )
        if control_identity is None:
            raise errors.InstallError("installed control-plane identity is invalid")
        comparison = state.compare_versions(version, control_identity.release)
        if comparison < 0:
            raise errors.InstallError("released payload downgrade is refused")
        if comparison == 0:
            raise errors.InstallError("released payload replay is refused")
    install_root = Path(ctx.install_dir)
    fresh = previous is None and _empty_or_absent_control_root(install_root)
    current_selection = generation.read(ctx)
    if previous is None and current_selection is None and not fresh:
        raise errors.InstallError(
            "installed payload root contains unverified content; remove it explicitly before "
            "installing"
        )
    previous_generation = (
        current_selection.active
        if current_selection is not None
        else (str(previous["transaction_id"]) if previous is not None else None)
    )
    _claim_transaction_root(ctx)
    transaction_id = uuid.uuid4().hex
    state.write_journal(
        ctx,
        transaction_id=transaction_id,
        version=version,
        receipt_sha256=receipt_sha256,
        state="prepared",
        fresh=fresh,
        previous_generation=previous_generation,
        previous_predecessor=(
            current_selection.predecessor if current_selection is not None else None
        ),
    )
    return PayloadTransaction(
        ctx=ctx,
        blobs=blobs,
        version=version,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        transaction_id=transaction_id,
        fresh=fresh,
        previous_generation=previous_generation,
        _token=PayloadTransaction._TOKEN,
    )


def _empty_or_absent_control_root(root: Path) -> bool:
    """Return whether no installed or operator-owned state occupies the control root."""
    if not root.exists() and not root.is_symlink():
        return True
    if root.is_symlink() or not root.is_dir():
        return False
    try:
        return next(root.iterdir(), None) is None
    except OSError as exc:
        raise errors.InstallError("installed payload root is unreadable") from exc


def _claim_transaction_root(ctx: runtime_context.RuntimeContext) -> Path:
    root = state.transaction_root(ctx)
    if root.exists() or root.is_symlink():
        transaction_state = state.status(ctx)
        if transaction_state is not None and transaction_state.get("state") != "invalid":
            raise errors.RecoveryRequiredError("complete payload recovery before installing")
        raise errors.RecoveryStateError(
            "payload transaction evidence is invalid; preserve it for diagnosis"
        )
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    return root


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
