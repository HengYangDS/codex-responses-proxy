"""Deterministic release assets shared by both Forge publication planes."""

from __future__ import annotations

import hashlib
import gzip
import io
import re
import tarfile
from collections.abc import Mapping
from pathlib import Path

ARCHIVE_NAME = "codex-responses-proxy-{version}.tar.gz"
CHECKSUM_NAME = "SHA256SUMS"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AssetError(ValueError):
    """A release asset set is incomplete, ambiguous, or inconsistent."""


def archive_bytes(files: Mapping[str, bytes], version: str) -> bytes:
    """Build one reproducible source archive from a path-to-bytes mapping."""

    prefix = f"codex-responses-proxy-{version}"
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=9, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for relative, content in sorted(files.items()):
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise AssetError("release asset path escapes the source root")
                info = tarfile.TarInfo(f"{prefix}/{path.as_posix()}")
                info.size = len(content)
                info.mode = 0o755 if content.startswith(b"#!") else 0o644
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def checksums(assets: Mapping[str, bytes]) -> bytes:
    """Return a stable GNU-style SHA-256 manifest for named assets."""

    if not assets:
        raise AssetError("release asset set must not be empty")
    return "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(assets.items())
    ).encode()


def parse_checksums(content: bytes) -> dict[str, str]:
    """Parse a strict checksum manifest without permitting duplicate names."""

    parsed: dict[str, str] = {}
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise AssetError("release checksum manifest is not ASCII") from error
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not _DIGEST.fullmatch(parts[0]) or not parts[1]:
            raise AssetError("release checksum manifest is malformed")
        name = parts[1]
        if Path(name).name != name or name in parsed:
            raise AssetError("release checksum asset name is invalid or duplicated")
        parsed[name] = parts[0]
    if not parsed:
        raise AssetError("release checksum manifest is empty")
    return parsed


def verify(assets: Mapping[str, bytes], manifest: bytes) -> dict[str, str]:
    """Require a manifest to name every non-manifest asset with its exact digest."""

    expected = parse_checksums(manifest)
    actual = {name: hashlib.sha256(content).hexdigest() for name, content in assets.items()}
    if expected != actual:
        raise AssetError("release assets do not match SHA256SUMS")
    return expected


def release_digests(files: Mapping[str, bytes], version: str) -> dict[str, str]:
    """Verify and identify the exact two-file release asset set."""

    archive_name = ARCHIVE_NAME.format(version=version)
    if set(files) != {archive_name, CHECKSUM_NAME}:
        raise AssetError("release asset set is incomplete or contains unknown files")
    verify({archive_name: files[archive_name]}, files[CHECKSUM_NAME])
    return {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}
