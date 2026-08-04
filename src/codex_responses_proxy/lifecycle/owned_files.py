"""Symlink-safe paths, file I/O, and inventories for owned payload bytes."""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from codex_responses_proxy import errors
from codex_responses_proxy.service import digest, inventory

RETIRED_INSTALL_DIRECTORIES = ("platform_adapters", "proxy", "tests")
OWNED_PAYLOAD_METADATA = (
    inventory.MANIFEST_FILENAME,
    inventory.RELEASE_RECEIPT_FILENAME,
    inventory.INSTALLED_RELEASE_STATE_FILENAME,
)
OWNED_PAYLOAD_FILES = (
    inventory.EXECUTABLE,
    inventory.WINDOWS_EXECUTABLE,
    inventory.PROVIDER_MANIFEST,
    *OWNED_PAYLOAD_METADATA,
)


def path(root: Path, relative: str) -> Path:
    """Return one canonical POSIX payload path beneath ``root``."""

    return root.joinpath(*PurePosixPath(relative).parts)


def canonical_relative(value: object, label: str) -> str:
    """Validate and return one canonical owned relative path."""

    if not isinstance(value, str) or not value:
        raise errors.InstallError(f"{label} path must be a non-empty string")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or PureWindowsPath(value).drive
        or value.startswith("//")
        or relative.as_posix() != value
        or value.endswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise errors.InstallError(f"{label} path is not canonical: {value!r}")
    return value


def regular_file(root: Path, relative: str, label: str) -> Path:
    """Return one existing owned regular file without following symlinks."""

    relative = canonical_relative(relative, label)
    try:
        if root.is_symlink() or not root.is_dir():
            raise errors.InstallError(f"{label} root is not a real directory")
        current = root
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current /= part
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise errors.InstallError(f"{label} path has a symlink ancestor: {relative}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise errors.InstallError(f"{label} path ancestor is not a directory: {relative}")
        target = current / parts[-1]
        metadata = target.lstat()
    except FileNotFoundError as exc:
        raise errors.InstallError(f"{label} file is unavailable: {relative}") from exc
    except OSError as exc:
        raise errors.InstallError(f"{label} path is unavailable: {relative}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise errors.InstallError(f"{label} path is a symlink: {relative}")
    if not stat.S_ISREG(metadata.st_mode):
        raise errors.InstallError(f"{label} path is not a regular file: {relative}")
    return target


def write_bytes(
    target: Path, content: bytes, *, mode: int = 0o644, root: Path | None = None
) -> None:
    """Atomically write one owned regular file through symlink-safe ancestors."""

    root = root or target.parent
    _real_parent(target, root)
    if target.is_symlink() or target.exists() and not target.is_file():
        raise errors.InstallError(f"owned path is not a regular file: {target.relative_to(root)}")
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _real_parent(target, root)
        if target.is_symlink() or target.exists() and not target.is_file():
            raise errors.InstallError(f"owned path changed type: {target.relative_to(root)}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_json_object(target: Path, label: str) -> dict[str, Any]:
    """Read one JSON object with a bounded installation error."""

    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise errors.InstallError(f"{label} is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise errors.InstallError(f"{label} is not a JSON object")
    return value


def read_canonical_json(target: Path, label: str) -> dict[str, Any]:
    """Read one canonical JSON object with a bounded installation error."""

    try:
        content = target.read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise errors.InstallError(f"{label} is unavailable or invalid") from exc
    if not isinstance(value, dict) or digest.canonical_json(value) != content:
        raise errors.InstallError(f"{label} is not canonical JSON")
    return value


def _real_parent(target: Path, root: Path) -> None:
    if root.is_symlink():
        raise errors.InstallError("installed payload root is a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise errors.InstallError("installed payload root is not a real directory")
    current = root
    try:
        relatives = target.relative_to(root).parts[:-1]
    except ValueError as exc:
        raise errors.InstallError("owned path escapes its root") from exc
    for part in relatives:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise errors.InstallError(
                f"owned path has a symlink ancestor: {target.relative_to(root)}"
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise errors.InstallError(
                f"owned path ancestor is not a directory: {target.relative_to(root)}"
            )
