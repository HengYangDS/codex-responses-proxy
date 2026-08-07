"""Fingerprint repository state without trusting host Git configuration."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any


def _hash_field(digest: Any, label: bytes, value: bytes) -> None:
    """Add one length-delimited field to a repository fingerprint."""

    digest.update(len(label).to_bytes(2, "big") + label + len(value).to_bytes(8, "big") + value)


def _git_output(root: Path, *args: str, allow_absent_head: bool = False) -> bytes:
    """Return raw Git output without inheriting host-specific configuration."""

    environment = os.environ | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    command = ["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(root), *args]
    try:
        return subprocess.run(command, capture_output=True, check=True, env=environment).stdout
    except subprocess.CalledProcessError as error:
        if allow_absent_head:
            return b"<unborn>"
        detail = os.fsdecode(error.stderr).strip() or str(error.returncode)
        raise RuntimeError(f"git_failed:{detail}") from None


def worktree_fingerprint(root: Path) -> str:
    """Fingerprint HEAD and the current tracked or untracked worktree content."""

    digest = hashlib.sha256()
    head = _git_output(root, "rev-parse", "--verify", "HEAD", allow_absent_head=True).strip()
    _hash_field(digest, b"head", head)
    listed = _git_output(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for encoded_path in sorted({path for path in listed.split(b"\0") if path}):
        path = root / os.fsdecode(encoded_path)
        _hash_field(digest, b"path", encoded_path)
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            _hash_field(digest, b"type", b"missing")
            continue
        _hash_field(digest, b"executable", b"1" if mode & 0o111 else b"0")
        if stat.S_ISREG(mode):
            label, value = b"regular", path.read_bytes()
        elif stat.S_ISLNK(mode):
            label, value = b"symlink", os.fsencode(os.readlink(path))
        else:
            label = (
                b"directory" if stat.S_ISDIR(mode) else f"special:{stat.S_IFMT(mode):o}".encode()
            )
            value = b""
        _hash_field(digest, label, value)
    return digest.hexdigest()
