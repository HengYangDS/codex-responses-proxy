"""Source-side payload transaction, rollback, and recovery state machine.

The transaction consumes one admitted payload capability and composes installed
projection writes through :mod:`codex_dmx_proxy.release.projection`. It owns the
private journal, rollback snapshot, commit, restore, and finalization lifecycle;
it does not own installed manifest reads or purge.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from codex_dmx_proxy import errors, installation
from codex_dmx_proxy.release import digest, inventory, projection

if TYPE_CHECKING:
    from codex_dmx_proxy.release import admission


RUNTIME_PAYLOAD_FILES = inventory.RUNTIME_FILES
SERVING_PAYLOAD_FILES = inventory.SERVING_FILES
TRANSACTION_JOURNAL_FILENAME = "transaction.json"
INSTALLED_RELEASE_STATE_SCHEMA = 1
TRANSACTION_JOURNAL_SCHEMA = 1
_STRICT_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_LEGACY_CAPTURE_NAME = re.compile(r"^reject-[^/]+\.json$")
_RETIRED_INSTALL_DIRECTORIES = projection._RETIRED_INSTALL_DIRECTORIES
_OWNED_PAYLOAD_FILES = projection._OWNED_PAYLOAD_FILES


def payload_transaction_dir(ctx: installation.InstallContext) -> Path:
    """Return the sibling directory used for short-lived payload transactions."""
    return Path(f"{ctx.install_dir}.transaction")


def _remove_legacy_captures(ctx: installation.InstallContext) -> None:
    """Remove exact retired raw captures without reading their contents.

    Legacy ``reject-*.json`` files may contain raw request bodies.  Their names
    are inspected only as direct children of the configured runtime log root;
    contents are never opened, copied, journaled, or included in rollback.
    Superseded executable paths are handled separately: rollback captures their
    prior owned bytes before the candidate projection removes them.
    """

    log_root = Path(ctx.log_dir)
    if log_root.is_dir() and not log_root.is_symlink():
        try:
            entries = tuple(log_root.iterdir())
        except OSError as exc:
            raise errors.InstallError("retired runtime residue inventory failed") from exc
        for entry in entries:
            if _LEGACY_CAPTURE_NAME.fullmatch(entry.name) is None:
                continue
            try:
                if entry.is_symlink() or not entry.is_file():
                    continue
                entry.unlink()
            except OSError as exc:
                raise errors.InstallError("legacy raw request capture cleanup failed") from exc


def installed_release_state_path(ctx: installation.InstallContext) -> Path:
    """Return the finalized released-projection state path."""
    return Path(ctx.install_dir, inventory.INSTALLED_RELEASE_STATE_FILENAME)


def transaction_journal_path(ctx: installation.InstallContext) -> Path:
    """Return the active payload transaction's canonical journal path."""
    return payload_transaction_dir(ctx) / TRANSACTION_JOURNAL_FILENAME


def transaction_status(ctx: installation.InstallContext) -> dict[str, object] | None:
    """Return the bounded, secret-free identity of an active transaction.

    Recovery diagnostics are intentionally excluded.  Exception text may contain
    request data, credentials, or source-side paths, so only typed journal fields
    needed to identify and classify the hold cross this installed read boundary.
    """

    path = transaction_journal_path(ctx)
    if not path.exists():
        return None
    journal = projection._read_canonical_json(path, "payload transaction journal")
    allowed = (
        "transaction_id",
        "version",
        "receipt_sha256",
        "state",
        "fresh",
    )
    return {key: journal[key] for key in allowed if key in journal}


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
    _blobs: tuple[admission.ReleasedBlob, ...]
    _ctx: installation.InstallContext
    _fresh: bool
    _receipt: Mapping[str, Any]
    _receipt_sha256: str
    _state: str
    _transaction_id: str
    _version: str

    def __init__(
        self,
        *,
        ctx: installation.InstallContext,
        blobs: tuple[admission.ReleasedBlob, ...],
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
        manifest = _manifest_for_blobs(self._version, self._blobs, self._receipt_sha256)
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
            _write_rollback_snapshot(self._ctx, rollback)
            _reject_unowned_candidate_collisions(self._ctx, rollback)
            _remove_retired_install_paths(self._ctx, rollback)
            mutated = True
            _write_candidate_projection(
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
            _restore_rollback_snapshot(self._ctx, rollback)
        elif self._fresh:
            _remove_candidate_projection(self._ctx)
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
    ctx: installation.InstallContext,
    candidate: admission.ReleasedPayload,
) -> PayloadTransaction:
    """Claim one admitted release and create its private transaction journal."""

    from codex_dmx_proxy.release import admission

    root = payload_transaction_dir(ctx)
    if root.exists() or root.is_symlink():
        raise errors.InstallError(f"payload transaction path already exists: {root}")
    try:
        blobs, version, receipt_sha256, receipt, _sidecar = admission.claim(candidate)
    except admission.ReleaseSourceError as exc:
        raise errors.InstallError(str(exc)) from exc
    _validate_candidate(blobs, version, receipt_sha256, receipt)
    previous = _read_installed_release_state(ctx)
    if previous is not None:
        comparison = _compare_versions(version, _require_state_version(previous))
        if comparison < 0:
            raise errors.InstallError("released payload downgrade is refused")
        if comparison == 0:
            raise errors.InstallError("released payload replay is refused")
    _remove_legacy_captures(ctx)
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


def _validate_candidate(
    blobs: tuple[admission.ReleasedBlob, ...],
    version: str,
    receipt_sha256: str,
    receipt: Mapping[str, Any],
) -> None:
    if _STRICT_VERSION.fullmatch(version) is None:
        raise errors.InstallError("released payload version is invalid")
    if not isinstance(receipt_sha256, str) or len(receipt_sha256) != 64:
        raise errors.InstallError("released payload receipt digest is invalid")
    if receipt.get("version") != version:
        raise errors.InstallError("released payload receipt version mismatch")
    expected_paths = tuple(RUNTIME_PAYLOAD_FILES)
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
    manifest = _manifest_for_blobs(version, blobs, receipt_sha256)
    if tuple(receipt.get("serving_files", ())) != tuple(SERVING_PAYLOAD_FILES):
        raise errors.InstallError("released payload serving file set mismatch")
    if receipt.get("serving_payload_sha256") != manifest["serving_payload_sha256"]:
        raise errors.InstallError("released payload serving identity mismatch")


def _manifest_for_blobs(
    version: str,
    blobs: tuple[admission.ReleasedBlob, ...],
    receipt_sha256: str,
) -> dict[str, Any]:
    return projection.manifest_for_digests(
        version, {blob.path: blob.sha256 for blob in blobs}, receipt_sha256
    )


def _reject_unowned_candidate_collisions(ctx: installation.InstallContext, rollback: Path) -> None:
    snapshot = projection._read_canonical_json(
        rollback / "snapshot.json", "payload rollback snapshot"
    )
    present, retired, previous_owned = _snapshot_inventory(snapshot)
    prior_owned = previous_owned
    install = Path(ctx.install_dir)
    for relative in _OWNED_PAYLOAD_FILES:
        path = projection._payload_path(install, relative)
        if relative not in prior_owned and (path.exists() or path.is_symlink()):
            raise errors.InstallError(f"candidate unowned collision: {relative}")


def _write_candidate_projection(
    ctx: installation.InstallContext,
    blobs: tuple[admission.ReleasedBlob, ...],
    version: str,
    receipt: Mapping[str, Any],
    receipt_sha256: str,
) -> None:
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
        projection.manifest_bytes(_manifest_for_blobs(version, blobs, receipt_sha256)),
        root=install,
    )
    projection._atomic_write_bytes(
        install / inventory.RELEASE_RECEIPT_FILENAME,
        digest.canonical_json(_json_value(receipt)),
        mode=0o600,
        root=install,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _snapshot_file(source: Path, target: Path) -> dict[str, object]:
    try:
        content = source.read_bytes()
        mode = source.stat(follow_symlinks=False).st_mode & 0o777
    except OSError as exc:
        raise errors.InstallError(f"payload rollback snapshot read failed: {source.name}") from exc
    projection._atomic_write_bytes(target, content, mode=mode)
    return {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}


def _path_set_sha256(paths: set[str]) -> str:
    content = json.dumps(sorted(paths), separators=(",", ":")) + "\n"
    return hashlib.sha256(content.encode()).hexdigest()


def _read_journal_version(ctx: installation.InstallContext) -> str:
    value = projection._read_canonical_json(
        transaction_journal_path(ctx), "payload transaction journal"
    ).get("version")
    if not isinstance(value, str) or _STRICT_VERSION.fullmatch(value) is None:
        raise errors.InstallError("payload transaction version is invalid")
    return value


def _write_rollback_snapshot(ctx: installation.InstallContext, rollback: Path) -> None:
    install = Path(ctx.install_dir)
    present: dict[str, dict[str, object]] = {}
    current_owned = set(_OWNED_PAYLOAD_FILES)
    retired_owned: set[str] = set()
    manifest_path = install / inventory.MANIFEST_FILENAME
    manifest_exists = manifest_path.exists() or manifest_path.is_symlink()
    retired_roots_exist = any(
        (install / relative).exists() or (install / relative).is_symlink()
        for relative in _RETIRED_INSTALL_DIRECTORIES
    )
    if not manifest_exists:
        if retired_roots_exist:
            raise errors.InstallError("retired installed payload manifest is required")
        previous_owned = current_owned
    else:
        if manifest_path.is_symlink():
            raise errors.InstallError("installed payload manifest is a symlink")
        manifest = projection._read_json_object(manifest_path, "installed payload manifest")
        files = manifest.get("files")
        current_manifest = (
            manifest.get("schema_version") == projection.PAYLOAD_MANIFEST_SCHEMA_VERSION
            and isinstance(files, dict)
            and set(files) == set(RUNTIME_PAYLOAD_FILES)
        )
        if current_manifest:
            ok, detail = projection.verify_payload_manifest(ctx)
            if not ok:
                raise errors.InstallError(f"installed payload integrity check failed: {detail}")
            previous_owned = current_owned
        else:
            owned = projection._manifest_owned_files(install)
            previous = manifest["release"]
            if _compare_versions(_read_journal_version(ctx), previous) < 0:
                raise errors.InstallError("released payload downgrade is refused")
            previous_owned = set(owned) | {inventory.MANIFEST_FILENAME}
            retired_owned = {
                relative
                for relative in owned
                if PurePosixPath(relative).parts[0] in _RETIRED_INSTALL_DIRECTORIES
            }
    for relative in sorted(previous_owned):
        source = projection._payload_path(install, relative)
        if not source.exists() and not source.is_symlink():
            continue
        source = projection._regular_file(install, relative, "live owned")
        present[relative] = _snapshot_file(source, projection._payload_path(rollback, relative))
    projection._atomic_write_bytes(
        rollback / "snapshot.json",
        digest.canonical_json(
            {
                "schema_version": 2,
                "present": present,
                "retired": sorted(retired_owned),
                "retired_owned_sha256": _path_set_sha256(retired_owned),
                "previous_owned": sorted(previous_owned),
            }
        ),
        mode=0o600,
    )


def _snapshot_inventory(
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, int]], set[str], set[str]]:
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
    retired = {projection._canonical_owned_path(value, "payload rollback") for value in raw_retired}
    previous_owned = {
        projection._canonical_owned_path(value, "payload rollback") for value in raw_previous_owned
    }
    if len(retired) != len(raw_retired) or len(previous_owned) != len(raw_previous_owned):
        raise errors.InstallError("payload rollback retired inventory is invalid")
    if retired_proof != _path_set_sha256(retired):
        raise errors.InstallError("payload rollback retired owned proof is invalid")
    present: dict[str, tuple[str, int]] = {}
    for raw_relative, metadata in raw_present.items():
        relative = projection._canonical_owned_path(raw_relative, "payload rollback")
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "mode"}
            or not isinstance(metadata.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) is None
            or not isinstance(metadata.get("mode"), int)
            or isinstance(metadata.get("mode"), bool)
            or not 0 <= metadata["mode"] <= 0o777
        ):
            raise errors.InstallError(f"payload rollback metadata is invalid: {relative}")
        present[relative] = (metadata["sha256"], metadata["mode"])
    if not retired.issubset(present) or not retired.issubset(previous_owned):
        raise errors.InstallError("payload rollback retired inventory is incomplete")
    if any(
        PurePosixPath(relative).parts[0] not in _RETIRED_INSTALL_DIRECTORIES for relative in retired
    ):
        raise errors.InstallError("payload rollback retired inventory is invalid")
    if not set(present).issubset(set(_OWNED_PAYLOAD_FILES) | retired):
        raise errors.InstallError("payload rollback owned inventory is invalid")
    return present, retired, previous_owned


def _remove_empty_retired_directories(install: Path) -> None:
    for relative in _RETIRED_INSTALL_DIRECTORIES:
        root = install / relative
        if root.is_symlink() or not root.exists():
            continue
        if not root.is_dir():
            raise errors.InstallError(f"retired installed path is not a directory: {relative}")
        try:
            directories = sorted(
                (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
        except OSError as exc:
            raise errors.InstallError(f"retired installed path cleanup failed: {relative}") from exc
        for directory in (*directories, root):
            try:
                directory.rmdir()
            except OSError as exc:
                try:
                    nonempty = any(directory.iterdir())
                except OSError:
                    nonempty = False
                if nonempty:
                    continue
                raise errors.InstallError(
                    f"retired installed path cleanup failed: {directory.relative_to(install).as_posix()}"
                ) from exc


def _remove_retired_install_paths(ctx: installation.InstallContext, rollback: Path) -> None:
    """Unlink only retired files admitted into the verified rollback snapshot."""

    snapshot = projection._read_canonical_json(
        rollback / "snapshot.json", "payload rollback snapshot"
    )
    present, retired, _previous_owned = _snapshot_inventory(snapshot)
    install = Path(ctx.install_dir)
    for relative in sorted(
        retired, key=lambda value: len(PurePosixPath(value).parts), reverse=True
    ):
        path = projection._regular_file(install, relative, "retired installed payload")
        if projection._sha256_file(path) != present[relative][0]:
            raise errors.InstallError(
                f"retired installed payload changed after snapshot: {relative}"
            )
        try:
            path.unlink()
        except OSError as exc:
            raise errors.InstallError(f"retired installed path cleanup failed: {relative}") from exc
    _remove_empty_retired_directories(install)


def _restore_rollback_snapshot(ctx: installation.InstallContext, rollback: Path) -> None:
    snapshot = projection._read_canonical_json(
        rollback / "snapshot.json", "payload rollback snapshot"
    )
    present, retired, _previous_owned = _snapshot_inventory(snapshot)
    install = Path(ctx.install_dir)
    restored: dict[str, tuple[bytes, int]] = {}
    for relative, (expected, mode) in present.items():
        source = projection._regular_file(rollback, relative, "payload rollback")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise errors.InstallError(f"payload rollback is unreadable: {relative}") from exc
        if hashlib.sha256(content).hexdigest() != expected:
            raise errors.InstallError(f"payload rollback digest mismatch: {relative}")
        target = projection._payload_path(install, relative)
        if relative in retired and (target.exists() or target.is_symlink()):
            existing = projection._regular_file(install, relative, "retired rollback target")
            if projection._sha256_file(existing) != expected:
                raise errors.InstallError(f"retired rollback target conflicts: {relative}")
        restored[relative] = content, mode
    for relative in _OWNED_PAYLOAD_FILES:
        target = projection._payload_path(install, relative)
        if relative not in present and (target.exists() or target.is_symlink()):
            projection._regular_file(install, relative, "live owned")
    for relative in _OWNED_PAYLOAD_FILES:
        if relative not in present:
            projection._payload_path(install, relative).unlink(missing_ok=True)
    for relative, (content, mode) in restored.items():
        target = projection._payload_path(install, relative)
        if relative in retired and target.exists():
            continue
        projection._atomic_write_bytes(target, content, mode=mode, root=install)
    for relative, (expected, _mode) in present.items():
        target = projection._regular_file(install, relative, "restored payload")
        if projection._sha256_file(target) != expected:
            raise errors.InstallError(f"restored payload digest mismatch: {relative}")


def _remove_candidate_projection(ctx: installation.InstallContext) -> None:
    install = Path(ctx.install_dir)
    for relative in _OWNED_PAYLOAD_FILES:
        projection._payload_path(install, relative).unlink(missing_ok=True)


def _remove_transaction_root(ctx: installation.InstallContext) -> None:
    root = payload_transaction_dir(ctx)
    if not root.exists():
        return
    try:
        shutil.rmtree(root)
    except OSError as exc:
        raise errors.InstallError(f"payload transaction cleanup failed: {exc}") from exc
    if root.exists():
        raise errors.InstallError("payload transaction cleanup did not remove the transaction")


def _write_journal(
    ctx: installation.InstallContext,
    *,
    transaction_id: str,
    version: str,
    receipt_sha256: str,
    state: str,
    fresh: bool,
    reason: str | None = None,
) -> None:
    journal: dict[str, Any] = {
        "schema_version": TRANSACTION_JOURNAL_SCHEMA,
        "transaction_id": transaction_id,
        "version": version,
        "receipt_sha256": receipt_sha256,
        "state": state,
        "fresh": fresh,
    }
    if reason is not None:
        journal["reason"] = reason
    projection._atomic_write_bytes(
        transaction_journal_path(ctx),
        digest.canonical_json(journal),
        mode=0o600,
    )


def _read_installed_release_state(ctx: installation.InstallContext) -> dict[str, Any] | None:
    path = installed_release_state_path(ctx)
    if not path.exists():
        return None
    state = projection._read_canonical_json(path, "installed release state")
    if state.get("schema_version") != INSTALLED_RELEASE_STATE_SCHEMA:
        raise errors.InstallError("installed release state schema is unsupported")
    return state


def _require_state_version(state: Mapping[str, Any]) -> str:
    version = state.get("version")
    if not isinstance(version, str) or _STRICT_VERSION.fullmatch(version) is None:
        raise errors.InstallError("installed release state version is invalid")
    return version


def _compare_versions(left: str, right: str) -> int:
    versions = tuple(tuple(map(int, version.split("."))) for version in (left, right))
    return (versions[0] > versions[1]) - (versions[0] < versions[1])
