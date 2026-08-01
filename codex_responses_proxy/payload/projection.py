"""Installed payload manifest, integrity, and purge ownership.

This module is the sole installed-projection reader and purge owner. It never
admits released source or owns transaction commit, rollback, or recovery state.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.payload import digest, inventory, owned_files

PAYLOAD_MANIFEST_SCHEMA_VERSION = 2
_STRICT_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RETIRED_MANIFEST_SCHEMAS = {1, 2}
_RETIRED_RUNTIME_FILES = {
    1: frozenset(
        {
            "VERSION",
            "codex_responses_proxy/commands/control.py",
            "governance.py",
            "platform_adapters/__init__.py",
            "platform_adapters/common.py",
            "platform_adapters/linux.py",
            "platform_adapters/macos.py",
            "platform_adapters/windows.py",
            "proxy/dmx_responses_proxy.py",
            "codex_responses_proxy/supervision/watchdog.py",
        }
    ),
    2: frozenset(
        {
            "VERSION",
            "codex_responses_proxy/commands/control.py",
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
            "codex_responses_proxy/supervision/watchdog.py",
        }
    ),
}


@dataclass(frozen=True)
class HistoricalProjection:
    """One exact, digest-verified historical installed projection."""

    release: str
    files: frozenset[str]
    entrypoint: str


def payload_manifest_path(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the installed runtime payload manifest path."""
    return Path(ctx.install_dir, inventory.MANIFEST_FILENAME)


def purge_installed_projection(ctx: runtime_context.RuntimeContext) -> tuple[str, ...]:
    """Delete only bytes admitted by the installed payload manifest.

    The manifest is the sole ownership proof.  Current projections require the
    complete manifest verifier; retired schema-1/2 projections require exact
    per-file digest and VERSION proof.  Unknown entries are never traversed or
    removed and are returned to the caller as an explicit incomplete-purge hold.
    """

    install = Path(ctx.install_dir)
    manifest_path = install / inventory.MANIFEST_FILENAME
    if manifest_path.is_symlink():
        raise errors.InstallError("installed payload manifest is a symlink")
    if not manifest_path.exists():
        raise errors.InstallError("installed payload manifest is required")
    manifest = owned_files.read_json_object(manifest_path, "installed payload manifest")
    files = manifest.get("files")
    current = (
        manifest.get("schema_version") == PAYLOAD_MANIFEST_SCHEMA_VERSION
        and isinstance(files, dict)
        and set(files) == set(inventory.RUNTIME_FILES)
    )
    if current:
        ok, detail = verify_payload_manifest(ctx)
        if not ok:
            raise errors.InstallError(f"installed payload integrity check failed: {detail}")
        owned = set(owned_files.OWNED_PAYLOAD_FILES)
    else:
        owned = set(verify_historical_projection(ctx).files) | {inventory.MANIFEST_FILENAME}
    for relative in owned:
        owned_files.regular_file(install, relative, "installed payload purge")
    for relative in sorted(owned, key=lambda value: len(PurePosixPath(value).parts), reverse=True):
        try:
            owned_files.path(install, relative).unlink()
        except OSError as exc:
            raise errors.InstallError(f"installed payload purge failed: {relative}") from exc
    _remove_empty_owned_directories(install, owned)
    residual_owned = [
        relative
        for relative in owned
        if (
            owned_files.path(install, relative).exists()
            or owned_files.path(install, relative).is_symlink()
        )
    ]
    if residual_owned:
        raise errors.InstallError(
            "installed payload remains after purge: " + ", ".join(residual_owned)
        )
    return _remaining_paths(install)


def _payload_relative_paths(root: str) -> list[str]:
    """Return the declared executable payload, not arbitrary deployment residue."""
    missing = [
        relative
        for relative in inventory.RUNTIME_FILES
        if not os.path.isfile(os.path.join(root, relative))
    ]
    if missing:
        raise errors.InstallError("installed payload is incomplete: " + ", ".join(missing))
    return list(inventory.RUNTIME_FILES)


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the canonical aggregate identity of the serving transaction.

    Each entry is encoded as the UTF-8 path length, path bytes, digest length,
    and raw SHA-256 digest bytes.  Sorting by path and length-delimiting every
    component makes the aggregate independent of mapping order and prevents
    boundary ambiguity.
    """
    expected = set(inventory.SERVING_FILES)
    if set(file_digests) != expected:
        raise errors.InstallError("serving payload file set mismatch")
    try:
        return inventory.serving_payload_sha256(file_digests)
    except digest.PayloadDigestError as exc:
        raise errors.InstallError(str(exc)) from exc


def manifest_for_digests(
    version: str, file_digests: Mapping[str, str], receipt_sha256: str
) -> dict[str, Any]:
    """Build the canonical current manifest from exact runtime-file digests."""

    serving_files = {relative: file_digests[relative] for relative in inventory.SERVING_FILES}
    return {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": version,
        "files": dict(file_digests),
        "serving_files": serving_files,
        "serving_payload_sha256": serving_payload_sha256(serving_files),
        "release_receipt_sha256": receipt_sha256,
    }


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Encode a human-readable deterministic payload manifest."""

    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_historical_projection(ctx: runtime_context.RuntimeContext) -> HistoricalProjection:
    """Verify one supported historical manifest, inventory, and entrypoint."""

    manifest, files = _historical_manifest_files(Path(ctx.install_dir))
    entrypoint = next(
        (relative for relative in ("proxy/dmx_responses_proxy.py",) if relative in files),
        "",
    )
    if not entrypoint:
        raise errors.InstallError("retired installed payload entrypoint is unsupported")
    return HistoricalProjection(
        release=manifest["release"],
        files=frozenset(files),
        entrypoint=str(owned_files.path(Path(ctx.install_dir), entrypoint)),
    )


def _historical_manifest_files(install: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Verify historical manifest bytes and return the parsed manifest and files."""

    manifest_path = install / inventory.MANIFEST_FILENAME
    if not manifest_path.exists():
        raise errors.InstallError("retired installed payload manifest is required")
    manifest = owned_files.read_json_object(manifest_path, "retired installed payload manifest")
    schema = manifest.get("schema_version")
    if schema not in _RETIRED_MANIFEST_SCHEMAS:
        raise errors.InstallError("retired installed payload manifest schema is unsupported")
    release = manifest.get("release")
    raw_files = manifest.get("files")
    if (
        not isinstance(release, str)
        or _STRICT_VERSION.fullmatch(release) is None
        or not isinstance(raw_files, dict)
        or not raw_files
    ):
        raise errors.InstallError("retired installed payload manifest is incomplete")
    files: dict[str, str] = {}
    for raw_relative, raw_digest in raw_files.items():
        relative = owned_files.canonical_relative(raw_relative, "retired manifest")
        if not isinstance(raw_digest, str) or re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None:
            raise errors.InstallError(f"retired installed payload digest is invalid: {relative}")
        if relative in files:
            raise errors.InstallError(f"retired manifest path is duplicated: {relative}")
        files[relative] = raw_digest
    if "VERSION" not in files:
        raise errors.InstallError("retired installed payload manifest has no VERSION")
    if set(files) != set(_RETIRED_RUNTIME_FILES[schema]):
        raise errors.InstallError("retired installed payload manifest file set is unsupported")
    for relative, expected in files.items():
        path = owned_files.regular_file(install, relative, "retired installed payload")
        try:
            actual = digest.sha256_file(path)
        except OSError as exc:
            raise errors.InstallError(
                f"retired installed payload is unreadable: {relative}"
            ) from exc
        if actual != expected:
            raise errors.InstallError(f"retired installed payload digest mismatch: {relative}")
    try:
        version = owned_files.regular_file(
            install, "VERSION", "retired installed payload"
        ).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise errors.InstallError("retired installed payload VERSION is unreadable") from exc
    if version != f"{release}\n":
        raise errors.InstallError("retired installed payload VERSION does not match manifest")
    return manifest, files


def _remove_empty_owned_directories(install: Path, owned: set[str]) -> None:
    directories = {
        parent
        for relative in owned
        for parent in PurePosixPath(relative).parents
        if parent != PurePosixPath(".")
    }
    for relative in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        directory = owned_files.path(install, relative.as_posix())
        if directory.is_symlink() or not directory.exists():
            continue
        if not directory.is_dir():
            raise errors.InstallError(
                f"installed payload directory changed type: {relative.as_posix()}"
            )
        try:
            directory.rmdir()
        except OSError:
            pass


def _remaining_paths(install: Path) -> tuple[str, ...]:
    if not install.exists():
        return ()
    if install.is_symlink() or not install.is_dir():
        raise errors.InstallError("installed payload root is not a real directory")
    try:
        remaining = tuple(
            sorted(path.relative_to(install).as_posix() for path in install.rglob("*"))
        )
    except OSError as exc:
        raise errors.InstallError("installed payload residue inventory failed") from exc
    if not remaining:
        try:
            install.rmdir()
        except OSError as exc:
            raise errors.InstallError("empty installed payload root removal failed") from exc
    return remaining


def _write_payload_manifest_for_fixture(
    ctx: runtime_context.RuntimeContext,
    *,
    release_receipt_sha256: str | None = None,
) -> Path:
    """Write the production manifest shape for a legacy installed fixture."""

    paths = _payload_relative_paths(ctx.install_dir)
    digests = {relative: digest.sha256_file(Path(ctx.install_dir, relative)) for relative in paths}
    serving = {relative: digests[relative] for relative in inventory.SERVING_FILES}
    manifest: dict[str, Any] = {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": Path(ctx.install_dir, "VERSION").read_text(encoding="utf-8").strip(),
        "files": digests,
        "serving_files": serving,
        "serving_payload_sha256": serving_payload_sha256(serving),
    }
    if release_receipt_sha256 is not None:
        manifest["release_receipt_sha256"] = release_receipt_sha256
    path = payload_manifest_path(ctx)
    owned_files.write_bytes(path, manifest_bytes(manifest))
    return path


def verify_payload_manifest(ctx: runtime_context.RuntimeContext) -> tuple[bool, str]:
    """Verify the installed executable projection without reading user config."""
    path = payload_manifest_path(ctx)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
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
    try:
        installed_release = Path(ctx.install_dir, "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        return False, f"installed VERSION unavailable: {exc}"
    if installed_release != release:
        return False, f"release mismatch: manifest={release} installed={installed_release}"
    expected_files = _payload_relative_paths(ctx.install_dir)
    if sorted(files) != sorted(expected_files):
        return False, "manifest file set mismatch"
    if sorted(serving_files) != sorted(inventory.SERVING_FILES):
        return False, "manifest serving file set mismatch"
    for relative, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64:
            return False, f"invalid digest: {relative}"
        path = os.path.join(ctx.install_dir, *relative.split("/"))
        try:
            actual = digest.sha256_file(Path(path))
        except OSError as exc:
            return False, f"payload unavailable: {relative}: {exc}"
        if actual != expected:
            return False, f"hash mismatch: {relative}"
    for relative, expected in serving_files.items():
        if files.get(relative) != expected:
            return False, f"serving digest mismatch: {relative}"
    try:
        actual_aggregate = serving_payload_sha256(serving_files)
    except errors.InstallError as exc:
        return False, str(exc)
    if aggregate != actual_aggregate:
        return False, "serving payload aggregate mismatch"
    receipt_path = os.path.join(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME)
    if receipt_digest is not None:
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            return False, "release receipt digest is invalid"
        try:
            actual_receipt = digest.sha256_file(Path(receipt_path))
        except OSError as exc:
            return False, f"release receipt unavailable: {exc}"
        if actual_receipt != receipt_digest:
            return False, "release receipt digest mismatch"
    return True, f"release {release}; {len(files)} files verified"
