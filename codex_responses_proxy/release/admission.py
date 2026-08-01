"""Admit signed Git release source into an opaque immutable payload bundle.

This module owns source identity only.  It reads exact committed blobs from a
signed annotated release tag under the caller's trust anchor.  Forge publication
is a release concern, not an installation dependency.  This module never writes
the installed projection or any installed state;
:mod:`codex_responses_proxy.payload.transaction` owns that later transaction.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, cast

from codex_responses_proxy.payload import digest, inventory, source


RECEIPT_SCHEMA = 1
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_ALLOWED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_TERMINAL_PROMPT",
    "GIT_OPTIONAL_LOCKS",
    "GIT_NO_REPLACE_OBJECTS",
}
_GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
}


class ReleaseSourceError(source.PayloadSourceError):
    """Report a fail-closed signed release-source invariant."""


def admit(
    repository: os.PathLike[str] | str,
    *,
    payload_paths: Iterable[str],
    trust_anchor: os.PathLike[str] | str,
    git_path: os.PathLike[str] | str,
    ssh_keygen_path: os.PathLike[str] | str,
) -> source.ReleasedPayload:
    """Admit exact signed release objects under one external trust anchor."""
    return _admit_verified(
        source.mint,
        repository,
        payload_paths=payload_paths,
        trust_anchor=trust_anchor,
        git_path=git_path,
        ssh_keygen_path=ssh_keygen_path,
    )


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the canonical aggregate for the declared serving inventory."""

    try:
        return inventory.serving_payload_sha256(file_digests)
    except digest.PayloadDigestError as exc:
        raise ReleaseSourceError(str(exc)) from exc


def _admit_verified(
    mint: Any,
    repository: os.PathLike[str] | str,
    *,
    payload_paths: Iterable[str],
    trust_anchor: os.PathLike[str] | str,
    git_path: os.PathLike[str] | str,
    ssh_keygen_path: os.PathLike[str] | str,
) -> source.ReleasedPayload:
    """Admit one exact signed release from the caller-selected source."""

    repo = Path(repository).resolve(strict=True)
    git = _absolute_executable(git_path, "git")
    require_clean_checkout(repo, git_path=git)
    ssh_keygen = _absolute_executable(ssh_keygen_path, "ssh-keygen")
    anchor = _external_regular_file(trust_anchor, repo)
    paths = _canonical_payload_paths(payload_paths)
    head = _git_text(git, repo, ("rev-parse", "--verify", "HEAD^{commit}"))
    version = _strict_version(_git_bytes(git, repo, ("show", f"{head}:VERSION")))
    tag_name = f"v{version}"
    tag = f"refs/tags/{tag_name}"
    tag_object = _git_text(git, repo, ("rev-parse", "--verify", tag))
    _validate_tag(git, repo, tag, tag_name, tag_object, head)
    commit = _git_text(git, repo, ("rev-parse", "--verify", f"{tag}^{{commit}}"))
    tree = _git_text(git, repo, ("rev-parse", "--verify", f"{commit}^{{tree}}"))
    identity = {
        "tag_object_oid": tag_object,
        "commit_oid": commit,
        "tree_oid": tree,
    }
    _verify_tag_signature(git, repo, tag, anchor, ssh_keygen)

    blobs = tuple(_read_blob(git, repo, commit, relative) for relative in paths)
    serving_paths = inventory.SERVING_FILES
    if not set(serving_paths) <= set(paths):
        raise ReleaseSourceError("declared serving inventory is absent from the admitted payload")
    serving_digest = serving_payload_sha256(
        {blob.path: blob.sha256 for blob in blobs if blob.path in set(serving_paths)}
    )
    object_format = _git_text(git, repo, ("rev-parse", "--show-object-format"))
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "verification_scope": "signed-release-source",
        "version": version,
        "tag": tag,
        **identity,
        "object_format": object_format,
        "trust_anchor_sha256": _sha256_file(anchor),
        "serving_payload_sha256": serving_digest,
        "serving_files": list(serving_paths),
        "payload": [
            {
                "path": blob.path,
                "mode": blob.mode,
                "blob_oid": blob.blob_oid,
                "sha256": blob.sha256,
            }
            for blob in blobs
        ],
    }
    sidecar = {
        "schema_version": RECEIPT_SCHEMA,
        "algorithm": "sha256",
        "receipt_sha256": hashlib.sha256(digest.canonical_json(receipt)).hexdigest(),
        "serving_payload_sha256": serving_digest,
        **identity,
    }
    expected_identity = (head, tag_object, commit, tree, object_format)
    if _source_identity(git, repo, tag, commit) != expected_identity:
        raise ReleaseSourceError("released-source identity changed during admission")
    require_clean_checkout(repo, git_path=git)
    if _source_identity(git, repo, tag, commit) != expected_identity:
        raise ReleaseSourceError("released-source identity changed during admission")
    return mint(blobs, receipt, sidecar)


def _source_identity(
    git: Path, repo: Path, tag: str, commit: str
) -> tuple[str, str, str, str, str]:
    return (
        _git_text(git, repo, ("rev-parse", "--verify", "HEAD^{commit}")),
        _git_text(git, repo, ("rev-parse", "--verify", tag)),
        _git_text(git, repo, ("rev-parse", "--verify", f"{tag}^{{commit}}")),
        _git_text(git, repo, ("rev-parse", "--verify", f"{commit}^{{tree}}")),
        _git_text(git, repo, ("rev-parse", "--show-object-format")),
    )


def _validate_tag(git: Path, repo: Path, tag: str, name: str, tag_object: str, head: str) -> None:
    """Require an annotated tag whose embedded identity directly names HEAD."""

    if _git_text(git, repo, ("cat-file", "-t", tag_object)) != "tag":
        raise ReleaseSourceError(f"{tag} must be an annotated tag object")
    headers = _git_bytes(git, repo, ("cat-file", "tag", tag_object)).split(b"\n\n", 1)[0]
    lines = headers.splitlines()
    if f"tag {name}".encode() not in lines:
        raise ReleaseSourceError("annotated tag embedded name is not exact vVERSION")
    if b"type commit" not in lines:
        raise ReleaseSourceError("annotated tag must directly name a commit")
    if _git_text(git, repo, ("rev-parse", "--verify", f"{tag}^{{commit}}")) != head:
        raise ReleaseSourceError("annotated release tag must name the direct HEAD commit")


def _read_blob(git: Path, repo: Path, commit: str, relative: str) -> source.ReleasedBlob:
    entry = _git_text(git, repo, ("ls-tree", commit, "--", relative))
    metadata, separator, path = entry.partition("\t")
    mode, kind, blob_oid = (*metadata.split(), "", "")[:3]
    if (mode, kind, separator, path) not in {
        ("100644", "blob", "\t", relative),
        ("100755", "blob", "\t", relative),
    } or re.fullmatch(r"[0-9a-f]{40,64}", blob_oid) is None:
        raise ReleaseSourceError(f"payload must have a committed regular blob mode: {relative}")
    content = _git_bytes(git, repo, ("cat-file", "blob", blob_oid))
    return source.ReleasedBlob(
        path=relative,
        mode=cast("Literal['100644', '100755']", mode),
        blob_oid=blob_oid,
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


def _isolated_git_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_") or name in _ALLOWED_GIT_ENV
    }
    return environment | _GIT_ENVIRONMENT


def require_clean_checkout(
    repository: os.PathLike[str] | str,
    *,
    git_path: os.PathLike[str] | str,
) -> None:
    """Require no tracked or untracked worktree changes under isolated Git."""

    repo = Path(repository).resolve(strict=True)
    git = _absolute_executable(git_path, "git")
    status = _git_bytes(
        git,
        repo,
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
    )
    if status:
        raise ReleaseSourceError("released-source admission requires a clean checkout")


def _run_git(git: Path, repo: Path, arguments: tuple[str, ...]) -> bytes:
    try:
        return subprocess.run(
            [
                str(git),
                "-C",
                str(repo),
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                *arguments,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=_isolated_git_environment(),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.decode("utf-8", "replace").strip()
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        raise ReleaseSourceError(f"isolated Git verification failed: {detail}") from error


def _git_bytes(git: Path, repo: Path, arguments: tuple[str, ...]) -> bytes:
    return _run_git(git, repo, arguments)


def _git_text(git: Path, repo: Path, arguments: tuple[str, ...]) -> str:
    try:
        return _run_git(git, repo, arguments).decode("utf-8").strip()
    except UnicodeError as error:
        raise ReleaseSourceError("Git identity output is not UTF-8") from error


def _verify_tag_signature(
    git: Path,
    repo: Path,
    tag: str,
    anchor: Path,
    ssh_keygen: Path,
) -> None:
    _run_git(
        git,
        repo,
        (
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={ssh_keygen}",
            "-c",
            f"gpg.ssh.allowedSignersFile={anchor}",
            "verify-tag",
            "--raw",
            tag,
        ),
    )


def _strict_version(content: bytes) -> str:
    try:
        value = content.decode("utf-8")
    except UnicodeError as error:
        raise ReleaseSourceError("VERSION blob is not UTF-8") from error
    if value != value.strip() + "\n" or _SEMVER.fullmatch(value.strip()) is None:
        raise ReleaseSourceError("VERSION must contain one strict release SemVer")
    return value.strip()


def _canonical_payload_paths(paths: Iterable[str]) -> tuple[str, ...]:
    result = tuple(map(_canonical_payload_path, paths))
    if len(set(result)) != len(result):
        raise ReleaseSourceError("payload path is not unique and canonical")
    if not result or "VERSION" not in result:
        raise ReleaseSourceError("payload paths must include VERSION")
    return result


def _canonical_payload_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseSourceError("payload path must be a non-empty string")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or path.as_posix() != value
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise ReleaseSourceError(f"payload path is not unique and canonical: {value!r}")
    return value


def _absolute_executable(path: os.PathLike[str] | str, label: str) -> Path:
    value = Path(path)
    if not value.is_absolute():
        raise ReleaseSourceError(f"{label} path must be absolute")
    resolved = value.resolve(strict=True)
    metadata = resolved.lstat()
    if not _is_executable_regular_file(resolved, metadata, os.name):
        raise ReleaseSourceError(f"{label} path must name an executable regular file")
    return resolved


def _is_executable_regular_file(path: Path, metadata: os.stat_result, os_name: str) -> bool:
    """Require a Windows executable suffix or the POSIX executable permission."""

    if not stat.S_ISREG(metadata.st_mode):
        return False
    if os_name == "nt":
        return path.suffix.casefold() in {".bat", ".cmd", ".com", ".exe"}
    return os.access(path, os.X_OK)


def _external_regular_file(path: os.PathLike[str] | str, repo: Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        raise ReleaseSourceError("trust anchor path must be absolute")
    resolved = value.resolve(strict=True)
    if resolved == repo or repo in resolved.parents:
        raise ReleaseSourceError("trust anchor must be outside the repository")
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ReleaseSourceError("trust anchor must be a regular non-symlink file")
    _assert_windows_no_reparse(resolved)
    return resolved


def _sha256_file(path: Path) -> str:
    return digest.sha256_file(path)


def _assert_windows_no_reparse(path: Path) -> None:
    """Fail closed when a Windows path carries any reparse-point attribute."""

    if os.name != "nt":
        return
    for candidate in (path, *path.parents):
        attributes = getattr(candidate.lstat(), "st_file_attributes", None)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if attributes is None:
            raise ReleaseSourceError("cannot safely prove Windows reparse-point absence")
        if attributes & reparse:
            raise ReleaseSourceError(f"Windows reparse point is refused: {candidate}")
