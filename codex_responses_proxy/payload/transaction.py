"""Source-side state machine for one admitted payload transaction.

The transaction consumes one admitted payload capability and coordinates the
candidate, migration, rollback, projection, and journal owners. It owns only
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
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.payload import identity
from codex_responses_proxy.payload import (
    candidate as payload_candidate,
    digest,
    inventory,
    migration,
    projection,
    rollback as payload_rollback,
    source,
    state,
)


RUNTIME_PAYLOAD_FILES = inventory.RUNTIME_FILES
SERVING_PAYLOAD_FILES = inventory.SERVING_FILES
TRANSACTION_JOURNAL_FILENAME = state.TRANSACTION_JOURNAL_FILENAME
INSTALLED_RELEASE_STATE_SCHEMA = state.INSTALLED_RELEASE_STATE_SCHEMA
TRANSACTION_JOURNAL_SCHEMA = state.TRANSACTION_JOURNAL_SCHEMA
_RETIRED_INSTALL_DIRECTORIES = projection._RETIRED_INSTALL_DIRECTORIES
_OWNED_PAYLOAD_FILES = projection._OWNED_PAYLOAD_FILES


payload_transaction_dir = state.transaction_root


_remove_legacy_captures = migration.remove_legacy_captures


installed_release_state_path = state.installed_path
transaction_journal_path = state.journal_path
transaction_status = state.status


def rollback_recovery(
    ctx: runtime_context.RuntimeContext,
    *,
    runtime: Mapping[str, object] | None,
) -> dict[str, object]:
    """Restore one exact retained transaction bound to its prior live runtime."""

    journal = projection._read_canonical_json(
        transaction_journal_path(ctx), "payload transaction journal"
    )
    if (
        journal.get("schema_version") != TRANSACTION_JOURNAL_SCHEMA
        or journal.get("state") != "recovery_required"
        or not isinstance(journal.get("transaction_id"), str)
        or not isinstance(journal.get("version"), str)
    ):
        raise errors.InstallError("payload recovery transaction is unavailable or invalid")
    rollback = payload_transaction_dir(ctx) / "rollback"
    previous = identity.committed_payload(rollback / inventory.ENTRYPOINT)
    if previous is None:
        raise errors.InstallError("payload recovery rollback runtime identity is invalid")
    candidate = identity.committed_payload(Path(ctx.proxy_script))
    if candidate is None:
        raise errors.InstallError("payload recovery candidate projection identity is invalid")
    expected_runtime = {
        **previous.handoff(),
        "payload_manifest_sha256": candidate.manifest_sha256,
        "accepting": True,
        "handoff_state": "idle",
    }
    expected_runtime.pop("manifest_sha256")
    if runtime is None or any(runtime.get(key) != value for key, value in expected_runtime.items()):
        raise errors.InstallError("payload recovery runtime does not match the rollback projection")
    payload_rollback.restore_snapshot(ctx, rollback)
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
    _blobs: tuple[source.ReleasedBlob, ...]
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
        blobs: tuple[source.ReleasedBlob, ...],
        version: str,
        receipt_sha256: str,
        receipt: Mapping[str, Any],
        transaction_id: str,
        fresh: bool,
        _token: object | None = None,
    ) -> None:
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
        rollback = payload_transaction_dir(self._ctx) / "rollback"
        rollback.mkdir(mode=0o700)
        mutated = False
        try:
            snapshot = payload_rollback.write_snapshot(self._ctx, rollback, self._version)
            payload_candidate.reject_unowned_collisions(self._ctx, snapshot.previous_owned)
            migration.remove_retired_paths(self._ctx, snapshot)
            mutated = True
            payload_candidate.write_projection(
                self._ctx,
                self._blobs,
                self._version,
                self._receipt,
                self._receipt_sha256,
            )
            ok, detail = projection.verify_payload_manifest(self._ctx)
            if not ok:
                raise errors.InstallError(f"committed payload integrity check failed: {detail}")
            self._state = "committed"
            _write_journal(
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
        state = {
            "schema_version": INSTALLED_RELEASE_STATE_SCHEMA,
            "version": self._version,
            "receipt_sha256": self._receipt_sha256,
            "transaction_id": self._transaction_id,
            "runtime": dict(runtime or {}),
        }
        projection._atomic_write_bytes(
            installed_release_state_path(self._ctx),
            digest.canonical_json(state),
            mode=0o600,
        )
        self._state = "finalized"
        _remove_transaction_root(self._ctx)

    def rollback(self) -> None:
        """Restore the exact prior payload, receipt, state, or their absence."""

        if self._state == "rolled_back":
            return
        rollback = payload_transaction_dir(self._ctx) / "rollback"
        if rollback.exists():
            payload_rollback.restore_snapshot(self._ctx, rollback)
        elif self._fresh:
            payload_candidate.remove_projection(self._ctx)
        self._state = "rolled_back"
        _remove_transaction_root(self._ctx)

    def preserve_for_recovery(self, reason: str) -> None:
        """Keep committed bytes and rollback while marking an unknown outcome."""

        if self._state != "committed":
            raise errors.InstallError("only a committed transaction can require recovery")
        self._state = "recovery_required"
        _write_journal(
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
    candidate: source.ReleasedPayload,
) -> PayloadTransaction:
    """Claim one admitted release and create its private transaction journal."""

    root = payload_transaction_dir(ctx)
    if root.exists() or root.is_symlink():
        raise errors.InstallError(f"payload transaction path already exists: {root}")
    try:
        blobs, version, receipt_sha256, receipt, _sidecar = source.claim(candidate)
    except source.PayloadSourceError as exc:
        raise errors.InstallError(str(exc)) from exc
    payload_candidate.validate(blobs, version, receipt_sha256, receipt)
    previous = _read_installed_release_state(ctx)
    if previous is not None:
        comparison = _compare_versions(version, _require_state_version(previous))
        if comparison < 0:
            raise errors.InstallError("released payload downgrade is refused")
        if comparison == 0:
            raise errors.InstallError("released payload replay is refused")
    migration.remove_legacy_captures(ctx)
    fresh = previous is None and not Path(ctx.install_dir).exists()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    transaction_id = uuid.uuid4().hex
    _write_journal(
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
    root = payload_transaction_dir(ctx)
    if not root.exists():
        return
    try:
        shutil.rmtree(root)
    except OSError as exc:
        raise errors.InstallError(f"payload transaction cleanup failed: {exc}") from exc
    if root.exists():
        raise errors.InstallError("payload transaction cleanup did not remove the transaction")


_write_journal = state.write_journal


_read_installed_release_state = state.read_installed
_require_state_version = state.require_version
_compare_versions = state.compare_versions
