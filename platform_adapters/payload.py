"""Runtime payload inventory, manifests, and transactional replacement.

This module is the sole owner of the executable payload boundary. It consumes
one opaque released-source capability, verifies immutable Git blobs, and owns
commit, rollback, recovery preservation, and finalization of the declared
runtime files. Route state remains owned by :mod:`platform_adapters.route_state`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from . import common
from . import payload_digest

if TYPE_CHECKING:
    from . import release_source


RUNTIME_PAYLOAD_FILES = (
    "VERSION",
    "control.py",
    "governance.py",
    "platform_adapters/__init__.py",
    "platform_adapters/common.py",
    "platform_adapters/control_handoff.py",
    "platform_adapters/payload.py",
    "platform_adapters/payload_digest.py",
    "platform_adapters/route_state.py",
    "platform_adapters/linux.py",
    "platform_adapters/macos.py",
    "platform_adapters/windows.py",
    "proxy/control_surface.py",
    "proxy/dmx_responses_proxy.py",
    "proxy/empty_response.py",
    "proxy/handoff.py",
    "proxy/http_surface.py",
    "proxy/input_compatibility.py",
    "proxy/payload_identity.py",
    "proxy/response_failed.py",
    "proxy/responses_rewrite.py",
    "proxy/responses_transport.py",
    "proxy/runtime_state.py",
    "proxy/sse_transport.py",
    "watchdog/watchdog.py",
)
SERVING_PAYLOAD_FILES = (
    "VERSION",
    "proxy/control_surface.py",
    "proxy/dmx_responses_proxy.py",
    "proxy/empty_response.py",
    "proxy/handoff.py",
    "proxy/http_surface.py",
    "proxy/input_compatibility.py",
    "proxy/payload_identity.py",
    "proxy/response_failed.py",
    "proxy/responses_rewrite.py",
    "proxy/responses_transport.py",
    "proxy/runtime_state.py",
    "proxy/sse_transport.py",
)
PAYLOAD_MANIFEST_FILENAME = "payload-manifest.json"
PAYLOAD_MANIFEST_SCHEMA_VERSION = 2
RELEASE_RECEIPT_FILENAME = "release-source-receipt.json"
INSTALLED_RELEASE_STATE_FILENAME = "release-install-state.json"
TRANSACTION_JOURNAL_FILENAME = "transaction.json"
INSTALLED_RELEASE_STATE_SCHEMA = 1
TRANSACTION_JOURNAL_SCHEMA = 1
_STRICT_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_LEGACY_CAPTURE_NAME = re.compile(r"^reject-[^/]+\.json$")
_RETIRED_INSTALL_PATHS = ("tests",)


def _atomic_write_text(path: str, text: str) -> None:
    """Atomically replace one owned UTF-8 metadata file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = f"{path}.tmp-{os.getpid()}"
    try:
        with open(temporary, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def payload_transaction_dir(ctx: common.InstallContext) -> str:
    """Return the sibling directory used for short-lived payload transactions."""
    return f"{ctx.install_dir}.transaction"


def _remove_retired_runtime_residue(ctx: common.InstallContext) -> None:
    """Remove exact superseded artifacts from runtime-owned roots only.

    Legacy ``reject-*.json`` files may contain raw request bodies.  Their names
    are inspected only as direct children of the configured runtime log root;
    contents are never opened, copied, journaled, or included in rollback.  The
    obsolete installed ``tests`` tree is likewise an exact, install-owned path,
    not a pattern or repository scan.
    """

    log_root = Path(ctx.log_dir)
    if log_root.is_dir() and not log_root.is_symlink():
        try:
            entries = tuple(log_root.iterdir())
        except OSError as exc:
            raise common.InstallError("retired runtime residue inventory failed") from exc
        for entry in entries:
            if _LEGACY_CAPTURE_NAME.fullmatch(entry.name) is None:
                continue
            try:
                if entry.is_symlink() or not entry.is_file():
                    continue
                entry.unlink()
            except OSError as exc:
                raise common.InstallError("legacy raw request capture cleanup failed") from exc

    install_root = Path(ctx.install_dir)
    for relative in _RETIRED_INSTALL_PATHS:
        retired = install_root / relative
        if retired.is_symlink():
            raise common.InstallError(f"retired installed path is a symlink: {relative}")
        if not retired.exists():
            continue
        if not retired.is_dir():
            raise common.InstallError(f"retired installed path is not a directory: {relative}")
        try:
            shutil.rmtree(retired)
        except OSError as exc:
            raise common.InstallError(f"retired installed path cleanup failed: {relative}") from exc


def installed_release_state_path(ctx: common.InstallContext) -> str:
    """Return the finalized released-projection state path."""

    return os.path.join(ctx.install_dir, INSTALLED_RELEASE_STATE_FILENAME)


def transaction_journal_path(ctx: common.InstallContext) -> str:
    """Return the active payload transaction's canonical journal path."""

    return os.path.join(payload_transaction_dir(ctx), TRANSACTION_JOURNAL_FILENAME)


def transaction_status(ctx: common.InstallContext) -> dict[str, object] | None:
    """Return the bounded, secret-free identity of an active transaction.

    Recovery diagnostics are intentionally excluded.  Exception text may contain
    request data, credentials, or source-side paths, so only typed journal fields
    needed to identify and classify the hold cross this installed read boundary.
    """

    path = Path(transaction_journal_path(ctx))
    if not path.exists():
        return None
    journal = _read_canonical_json(path, "payload transaction journal")
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
    _blobs: tuple[release_source.ReleasedBlob, ...]
    _ctx: common.InstallContext
    _fresh: bool
    _receipt: Mapping[str, Any]
    _receipt_sha256: str
    _state: str
    _transaction_id: str
    _version: str

    def __init__(
        self,
        *,
        ctx: common.InstallContext,
        blobs: tuple[release_source.ReleasedBlob, ...],
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
            "manifest_sha256": hashlib.sha256(_manifest_bytes(manifest)).hexdigest(),
            "serving_payload_sha256": manifest["serving_payload_sha256"],
            "release_receipt_sha256": self._receipt_sha256,
        }

    def commit_projection(self) -> None:
        """Install candidate bytes and pending provenance while retaining rollback."""

        if self._state != "prepared":
            raise common.InstallError("payload transaction is not prepared")
        root = Path(payload_transaction_dir(self._ctx))
        rollback = root / "rollback"
        rollback.mkdir(mode=0o700)
        _write_rollback_snapshot(self._ctx, rollback)
        try:
            _write_candidate_projection(
                self._ctx,
                self._blobs,
                self._version,
                self._receipt,
                self._receipt_sha256,
            )
            ok, detail = verify_payload_manifest(self._ctx)
            if not ok:
                raise common.InstallError(f"committed payload integrity check failed: {detail}")
            self._state = "committed"
            _write_journal(
                self._ctx,
                transaction_id=self._transaction_id,
                version=self._version,
                receipt_sha256=self._receipt_sha256,
                state=self._state,
                fresh=self._fresh,
            )
        except BaseException:
            self.rollback()
            raise

    def finalize(self, runtime: Mapping[str, object] | None = None) -> None:
        """Record installation success only after the caller proves SERVING."""

        if self._state != "committed":
            raise common.InstallError("payload transaction is not committed")
        state = {
            "schema_version": INSTALLED_RELEASE_STATE_SCHEMA,
            "version": self._version,
            "receipt_sha256": self._receipt_sha256,
            "transaction_id": self._transaction_id,
            "runtime": dict(runtime or {}),
        }
        _atomic_write_bytes(
            Path(installed_release_state_path(self._ctx)),
            _canonical_json(state),
            mode=0o600,
        )
        self._state = "finalized"
        _remove_transaction_root(self._ctx)

    def rollback(self) -> None:
        """Restore the exact prior payload, receipt, state, or their absence."""

        if self._state == "rolled_back":
            return
        rollback = Path(payload_transaction_dir(self._ctx), "rollback")
        if rollback.exists():
            _restore_rollback_snapshot(self._ctx, rollback)
        elif self._fresh:
            _remove_candidate_projection(self._ctx)
        self._state = "rolled_back"
        _remove_transaction_root(self._ctx)

    def preserve_for_recovery(self, reason: str) -> None:
        """Keep committed bytes and rollback while marking an unknown outcome."""

        if self._state != "committed":
            raise common.InstallError("only a committed transaction can require recovery")
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
    ctx: common.InstallContext,
    candidate: release_source.ReleasedPayload,
) -> PayloadTransaction:
    """Claim one admitted release and create its private transaction journal."""

    from . import release_source

    root = Path(payload_transaction_dir(ctx))
    if root.exists() or root.is_symlink():
        raise common.InstallError(f"payload transaction path already exists: {root}")
    try:
        blobs, version, receipt_sha256, receipt, _sidecar = release_source.claim(candidate)
    except release_source.ReleaseSourceError as exc:
        raise common.InstallError(str(exc)) from exc
    _validate_candidate(blobs, version, receipt_sha256, receipt)
    previous = _read_installed_release_state(ctx)
    if previous is not None:
        comparison = _compare_versions(version, _require_state_version(previous))
        if comparison < 0:
            raise common.InstallError("released payload downgrade is refused")
        if comparison == 0:
            raise common.InstallError("released payload replay is refused")
    _remove_retired_runtime_residue(ctx)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    transaction_id = uuid.uuid4().hex
    _write_journal(
        ctx,
        transaction_id=transaction_id,
        version=version,
        receipt_sha256=receipt_sha256,
        state="prepared",
        fresh=previous is None and not Path(ctx.install_dir).exists(),
    )
    return PayloadTransaction(
        ctx=ctx,
        blobs=blobs,
        version=version,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        transaction_id=transaction_id,
        fresh=previous is None and not Path(ctx.install_dir).exists(),
        _token=PayloadTransaction._TOKEN,
    )


def payload_manifest_path(ctx: common.InstallContext) -> str:
    """Return the installed runtime payload manifest path."""
    return os.path.join(ctx.install_dir, PAYLOAD_MANIFEST_FILENAME)


def _payload_relative_paths(root: str) -> list[str]:
    """Return the declared executable payload, not arbitrary deployment residue."""
    missing = [
        relative
        for relative in RUNTIME_PAYLOAD_FILES
        if not os.path.isfile(os.path.join(root, relative))
    ]
    if missing:
        raise common.InstallError("installed payload is incomplete: " + ", ".join(missing))
    return list(RUNTIME_PAYLOAD_FILES)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the canonical aggregate identity of the serving payload.

    Each entry is encoded as the UTF-8 path length, path bytes, digest length,
    and raw SHA-256 digest bytes.  Sorting by path and length-delimiting every
    component makes the aggregate independent of mapping order and prevents
    boundary ambiguity.
    """
    expected = set(SERVING_PAYLOAD_FILES)
    if set(file_digests) != expected:
        raise common.InstallError("serving payload file set mismatch")
    try:
        return payload_digest.serving_payload_sha256(file_digests)
    except payload_digest.PayloadDigestError as exc:
        raise common.InstallError(str(exc)) from exc


def _validate_candidate(
    blobs: tuple[release_source.ReleasedBlob, ...],
    version: str,
    receipt_sha256: str,
    receipt: Mapping[str, Any],
) -> None:
    if _STRICT_VERSION.fullmatch(version) is None:
        raise common.InstallError("released payload version is invalid")
    if not isinstance(receipt_sha256, str) or len(receipt_sha256) != 64:
        raise common.InstallError("released payload receipt digest is invalid")
    if receipt.get("version") != version:
        raise common.InstallError("released payload receipt version mismatch")
    expected_paths = tuple(RUNTIME_PAYLOAD_FILES)
    actual_paths = tuple(blob.path for blob in blobs)
    if actual_paths != expected_paths or len(set(actual_paths)) != len(actual_paths):
        raise common.InstallError("released payload file set mismatch")
    for blob in blobs:
        if blob.mode not in {"100644", "100755"}:
            raise common.InstallError(f"released payload mode is invalid: {blob.path}")
        if hashlib.sha256(blob.content).hexdigest() != blob.sha256:
            raise common.InstallError(f"released payload digest mismatch: {blob.path}")
    version_blob = next(blob for blob in blobs if blob.path == "VERSION")
    if version_blob.content != f"{version}\n".encode():
        raise common.InstallError("released payload VERSION blob mismatch")
    manifest = _manifest_for_blobs(version, blobs, receipt_sha256)
    if receipt.get("serving_payload_sha256") != manifest["serving_payload_sha256"]:
        raise common.InstallError("released payload serving identity mismatch")


def _manifest_for_blobs(
    version: str,
    blobs: tuple[release_source.ReleasedBlob, ...],
    receipt_sha256: str,
) -> dict[str, Any]:
    digests = {blob.path: blob.sha256 for blob in blobs}
    serving_files = {relative: digests[relative] for relative in SERVING_PAYLOAD_FILES}
    return {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": version,
        "files": digests,
        "serving_files": serving_files,
        "serving_payload_sha256": serving_payload_sha256(serving_files),
        "release_receipt_sha256": receipt_sha256,
    }


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, content: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_candidate_projection(
    ctx: common.InstallContext,
    blobs: tuple[release_source.ReleasedBlob, ...],
    version: str,
    receipt: Mapping[str, Any],
    receipt_sha256: str,
) -> None:
    install = Path(ctx.install_dir)
    for blob in blobs:
        target = install.joinpath(*PurePosixPath(blob.path).parts)
        _atomic_write_bytes(target, blob.content, mode=0o755 if blob.mode == "100755" else 0o644)
        if _sha256_file(str(target)) != blob.sha256:
            raise common.InstallError(f"installed payload digest mismatch: {blob.path}")
    _atomic_write_bytes(
        install / PAYLOAD_MANIFEST_FILENAME,
        _manifest_bytes(_manifest_for_blobs(version, blobs, receipt_sha256)),
    )
    _atomic_write_bytes(
        install / RELEASE_RECEIPT_FILENAME,
        _canonical_json(dict(receipt)),
        mode=0o600,
    )


def _write_rollback_snapshot(ctx: common.InstallContext, rollback: Path) -> None:
    install = Path(ctx.install_dir)
    present: list[str] = []
    owned = (
        *RUNTIME_PAYLOAD_FILES,
        PAYLOAD_MANIFEST_FILENAME,
        RELEASE_RECEIPT_FILENAME,
        INSTALLED_RELEASE_STATE_FILENAME,
    )
    for relative in owned:
        source = install.joinpath(*PurePosixPath(relative).parts)
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file():
            raise common.InstallError(f"live owned path is not a regular file: {relative}")
        target = rollback.joinpath(*PurePosixPath(relative).parts)
        _atomic_write_bytes(target, source.read_bytes(), mode=source.stat().st_mode & 0o777)
        present.append(relative)
    _atomic_write_bytes(
        rollback / "snapshot.json",
        _canonical_json({"schema_version": 1, "present": present}),
        mode=0o600,
    )


def _restore_rollback_snapshot(ctx: common.InstallContext, rollback: Path) -> None:
    snapshot = _read_canonical_json(rollback / "snapshot.json", "payload rollback snapshot")
    present = snapshot.get("present")
    if not isinstance(present, list) or not all(isinstance(item, str) for item in present):
        raise common.InstallError("payload rollback snapshot is invalid")
    present_set = set(present)
    owned = (
        *RUNTIME_PAYLOAD_FILES,
        PAYLOAD_MANIFEST_FILENAME,
        RELEASE_RECEIPT_FILENAME,
        INSTALLED_RELEASE_STATE_FILENAME,
    )
    install = Path(ctx.install_dir)
    for relative in owned:
        target = install.joinpath(*PurePosixPath(relative).parts)
        if relative not in present_set:
            target.unlink(missing_ok=True)
            continue
        source = rollback.joinpath(*PurePosixPath(relative).parts)
        if source.is_symlink() or not source.is_file():
            raise common.InstallError(f"payload rollback is incomplete: {relative}")
        _atomic_write_bytes(target, source.read_bytes(), mode=source.stat().st_mode & 0o777)
    if present_set.intersection(RUNTIME_PAYLOAD_FILES):
        ok, detail = verify_payload_manifest(ctx)
        if not ok:
            raise common.InstallError(f"restored payload integrity check failed: {detail}")


def _remove_candidate_projection(ctx: common.InstallContext) -> None:
    install = Path(ctx.install_dir)
    for relative in (
        *RUNTIME_PAYLOAD_FILES,
        PAYLOAD_MANIFEST_FILENAME,
        RELEASE_RECEIPT_FILENAME,
        INSTALLED_RELEASE_STATE_FILENAME,
    ):
        install.joinpath(*PurePosixPath(relative).parts).unlink(missing_ok=True)


def _remove_transaction_root(ctx: common.InstallContext) -> None:
    root = Path(payload_transaction_dir(ctx))
    if not root.exists():
        return
    try:
        shutil.rmtree(root)
    except OSError as exc:
        raise common.InstallError(f"payload transaction cleanup failed: {exc}") from exc
    if root.exists():
        raise common.InstallError("payload transaction cleanup did not remove the transaction")


def _write_journal(
    ctx: common.InstallContext,
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
    _atomic_write_bytes(
        Path(transaction_journal_path(ctx)),
        _canonical_json(journal),
        mode=0o600,
    )


def _read_canonical_json(path: Path, label: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise common.InstallError(f"{label} is unavailable or invalid") from exc
    if not isinstance(value, dict) or _canonical_json(value) != content:
        raise common.InstallError(f"{label} is not canonical JSON")
    return value


def _read_installed_release_state(ctx: common.InstallContext) -> dict[str, Any] | None:
    path = Path(installed_release_state_path(ctx))
    if not path.exists():
        return None
    state = _read_canonical_json(path, "installed release state")
    if state.get("schema_version") != INSTALLED_RELEASE_STATE_SCHEMA:
        raise common.InstallError("installed release state schema is unsupported")
    return state


def _require_state_version(state: Mapping[str, Any]) -> str:
    version = state.get("version")
    if not isinstance(version, str) or _STRICT_VERSION.fullmatch(version) is None:
        raise common.InstallError("installed release state version is invalid")
    return version


def _compare_versions(left: str, right: str) -> int:
    left_parts = tuple(int(part) for part in left.split("."))
    right_parts = tuple(int(part) for part in right.split("."))
    return (left_parts > right_parts) - (left_parts < right_parts)


def _write_payload_manifest_for_fixture(
    ctx: common.InstallContext,
    *,
    release_receipt_sha256: str | None = None,
) -> str:
    """Build legacy fixture manifests; production writes them only in transactions.

    The manifest deliberately excludes configuration, backups, logs, request data,
    tokens, and installation state.  It is provenance for the re-creatable runtime
    projection, not a snapshot of user state.
    """
    files = _payload_relative_paths(ctx.install_dir)
    if not files:
        raise common.InstallError("installed payload is empty; refusing to write manifest")
    digests = {
        relative: _sha256_file(os.path.join(ctx.install_dir, relative)) for relative in files
    }
    serving_files = {relative: digests[relative] for relative in SERVING_PAYLOAD_FILES}
    manifest = {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": _read_text(os.path.join(ctx.install_dir, "VERSION")).strip(),
        "files": digests,
        "serving_files": serving_files,
        "serving_payload_sha256": serving_payload_sha256(serving_files),
    }
    if release_receipt_sha256 is not None:
        manifest["release_receipt_sha256"] = release_receipt_sha256
    _atomic_write_text(
        payload_manifest_path(ctx),
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return payload_manifest_path(ctx)


def verify_payload_manifest(ctx: common.InstallContext) -> tuple[bool, str]:
    """Verify the installed executable projection without reading user config."""
    path = payload_manifest_path(ctx)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"manifest unavailable: {exc}"
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != PAYLOAD_MANIFEST_SCHEMA_VERSION
    ):
        return False, "manifest schema is unsupported"
    release = manifest.get("release")
    files = manifest.get("files")
    serving_files = manifest.get("serving_files")
    aggregate = manifest.get("serving_payload_sha256")
    receipt_digest = manifest.get("release_receipt_sha256")
    if (
        not isinstance(release, str)
        or not release
        or not isinstance(files, dict)
        or not files
        or not isinstance(serving_files, dict)
        or not serving_files
        or not isinstance(aggregate, str)
    ):
        return False, "manifest is incomplete"
    version_path = os.path.join(ctx.install_dir, "VERSION")
    try:
        installed_release = _read_text(version_path).strip()
    except OSError as exc:
        return False, f"installed VERSION unavailable: {exc}"
    if installed_release != release:
        return False, f"release mismatch: manifest={release} installed={installed_release}"
    expected_files = _payload_relative_paths(ctx.install_dir)
    if sorted(files) != sorted(expected_files):
        return False, "manifest file set mismatch"
    if sorted(serving_files) != sorted(SERVING_PAYLOAD_FILES):
        return False, "manifest serving file set mismatch"
    for relative, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64:
            return False, f"invalid digest: {relative}"
        path = os.path.join(ctx.install_dir, *relative.split("/"))
        try:
            actual = _sha256_file(path)
        except OSError as exc:
            return False, f"payload unavailable: {relative}: {exc}"
        if actual != expected:
            return False, f"hash mismatch: {relative}"
    for relative, expected in serving_files.items():
        if files.get(relative) != expected:
            return False, f"serving digest mismatch: {relative}"
    try:
        actual_aggregate = serving_payload_sha256(serving_files)
    except common.InstallError as exc:
        return False, str(exc)
    if aggregate != actual_aggregate:
        return False, "serving payload aggregate mismatch"
    receipt_path = os.path.join(ctx.install_dir, RELEASE_RECEIPT_FILENAME)
    if receipt_digest is not None:
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            return False, "release receipt digest is invalid"
        try:
            actual_receipt = _sha256_file(receipt_path)
        except OSError as exc:
            return False, f"release receipt unavailable: {exc}"
        if actual_receipt != receipt_digest:
            return False, "release receipt digest mismatch"
    return True, f"release {release}; {len(files)} files verified"
