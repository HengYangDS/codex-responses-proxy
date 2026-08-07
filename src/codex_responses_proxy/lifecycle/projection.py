"""Installed payload manifest, integrity, and purge ownership."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.service import digest, inventory

PAYLOAD_MANIFEST_SCHEMA_VERSION = 2


def payload_manifest_path(ctx: runtime_context.RuntimeContext) -> Path:
    """Return the installed payload manifest path."""

    return Path(ctx.install_dir, inventory.MANIFEST_FILENAME)


def purge_installed_projection(ctx: runtime_context.RuntimeContext) -> tuple[str, ...]:
    """Delete only bytes proven by the current installed manifest."""

    install = Path(ctx.install_dir)
    manifest_path = payload_manifest_path(ctx)
    if manifest_path.is_symlink():
        raise errors.InstallError("installed payload manifest is a symlink")
    if not manifest_path.exists():
        raise errors.InstallError("installed payload manifest is required")
    ok, detail = verify_payload_manifest(ctx)
    if not ok:
        raise errors.InstallError(f"installed payload integrity check failed: {detail}")
    manifest = owned_files.read_json_object(manifest_path, "installed payload manifest")
    files = manifest["files"]
    assert isinstance(files, dict)
    owned = set(files) | set(owned_files.OWNED_PAYLOAD_METADATA)
    for relative in owned:
        owned_files.regular_file(install, relative, "installed payload purge")
    for relative in sorted(owned, key=lambda value: len(PurePosixPath(value).parts), reverse=True):
        try:
            owned_files.path(install, relative).unlink()
        except OSError as exc:
            raise errors.InstallError(f"installed payload purge failed: {relative}") from exc
    _remove_empty_owned_directories(install, owned)
    if residual := [
        relative
        for relative in owned
        if owned_files.path(install, relative).exists()
        or owned_files.path(install, relative).is_symlink()
    ]:
        raise errors.InstallError("installed payload remains after purge: " + ", ".join(residual))
    return _remaining_paths(install)


def _payload_relative_paths(root: str) -> list[str]:
    files = (
        inventory.runtime_files(windows=True)
        if os.path.isfile(os.path.join(root, inventory.WINDOWS_EXECUTABLE))
        else inventory.runtime_files()
    )
    if missing := [
        relative for relative in files if not os.path.isfile(os.path.join(root, relative))
    ]:
        raise errors.InstallError("installed payload is incomplete: " + ", ".join(missing))
    return list(files)


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the canonical identity of the executable and provider manifest."""

    executable_paths = {inventory.EXECUTABLE, inventory.WINDOWS_EXECUTABLE}
    if (
        set(file_digests).difference(executable_paths) != {inventory.PROVIDER_MANIFEST}
        or len(file_digests) != 2
        or not set(file_digests).intersection(executable_paths)
    ):
        raise errors.InstallError("serving payload file set mismatch")
    try:
        return digest.serving_payload_sha256(file_digests)
    except digest.PayloadDigestError as exc:
        raise errors.InstallError(str(exc)) from exc


def manifest_for_digests(
    version: str, file_digests: Mapping[str, str], receipt_sha256: str
) -> dict[str, Any]:
    """Build the canonical current manifest from exact runtime digests."""

    serving_files = dict(file_digests)
    return {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": version,
        "files": dict(file_digests),
        "serving_files": serving_files,
        "serving_payload_sha256": serving_payload_sha256(serving_files),
        "release_receipt_sha256": receipt_sha256,
    }


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Encode a deterministic, human-readable payload manifest."""

    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


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
    """Write the production manifest shape for a current test payload."""

    paths = _payload_relative_paths(ctx.install_dir)
    digests = {relative: digest.sha256_file(Path(ctx.install_dir, relative)) for relative in paths}
    manifest: dict[str, Any] = {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": "0.0.0",
        "files": digests,
        "serving_files": dict(digests),
        "serving_payload_sha256": serving_payload_sha256(digests),
    }
    if release_receipt_sha256 is not None:
        manifest["release_receipt_sha256"] = release_receipt_sha256
    path = payload_manifest_path(ctx)
    owned_files.write_bytes(path, manifest_bytes(manifest))
    return path


def verify_payload_manifest(ctx: runtime_context.RuntimeContext) -> tuple[bool, str]:
    """Verify the installed executable and provider manifest."""

    try:
        manifest = json.loads(payload_manifest_path(ctx).read_text(encoding="utf-8"))
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
        expected_files = _payload_relative_paths(ctx.install_dir)
    except errors.InstallError as exc:
        return False, str(exc)
    if sorted(files) != sorted(expected_files):
        return False, "manifest file set mismatch"
    if sorted(serving_files) != sorted(expected_files):
        return False, "manifest serving file set mismatch"
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
            return False, f"invalid digest: {relative}"
        try:
            actual = digest.sha256_file(Path(ctx.install_dir, *relative.split("/")))
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
    if receipt_digest is not None:
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            return False, "release receipt digest is invalid"
        try:
            actual_receipt = digest.sha256_file(
                Path(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME)
            )
        except OSError as exc:
            return False, f"release receipt unavailable: {exc}"
        if actual_receipt != receipt_digest:
            return False, "release receipt digest mismatch"
    return True, f"release {release}; {len(files)} files verified"
