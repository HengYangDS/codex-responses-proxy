"""Admit published signed Git source into an opaque immutable payload bundle.

This module owns source identity only.  It reads exact committed blobs from a
signed annotated release tag and binds them to externally verified GitLab and
GitHub publication evidence.  It never writes the installed projection or any
installed state; :mod:`platform_adapters.payload` owns that later transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from . import payload_digest
from . import publication


RECEIPT_SCHEMA = 1
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_TERMINAL_PROMPT",
    "GIT_OPTIONAL_LOCKS",
    "GIT_NO_REPLACE_OBJECTS",
}


class ReleaseSourceError(RuntimeError):
    """Report a fail-closed released-source or publication invariant."""


@dataclass(frozen=True, slots=True)
class ReleasedBlob:
    """One immutable regular Git blob admitted for the projection transaction."""

    path: str
    mode: Literal["100644", "100755"]
    blob_oid: str
    sha256: str
    content: bytes


class ReleasedPayload:
    """Opaque single-use authority over exact immutable released payload bytes."""

    __slots__ = ("_blobs", "_claimed", "_receipt", "_receipt_sha256", "_sidecar")
    _TOKEN = object()
    _blobs: tuple[ReleasedBlob, ...]
    _claimed: bool
    _receipt: Mapping[str, Any]
    _receipt_sha256: str
    _sidecar: Mapping[str, Any]

    def __init__(
        self,
        *,
        blobs: tuple[ReleasedBlob, ...],
        receipt: Mapping[str, Any],
        sidecar: Mapping[str, Any],
        _token: object | None = None,
    ) -> None:
        if _token is not self._TOKEN:
            raise TypeError("ReleasedPayload is an opaque capability; use admit()")
        object.__setattr__(self, "_blobs", blobs)
        object.__setattr__(self, "_receipt", MappingProxyType(dict(receipt)))
        object.__setattr__(self, "_sidecar", MappingProxyType(dict(sidecar)))
        object.__setattr__(
            self, "_receipt_sha256", hashlib.sha256(canonical_json(receipt)).hexdigest()
        )
        object.__setattr__(self, "_claimed", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise ReleaseSourceError("released payload capability is immutable")

    @property
    def version(self) -> str:
        """Return the admitted strict release version."""

        return str(self._receipt["version"])

    @property
    def serving_payload_sha256(self) -> str:
        """Return the canonical aggregate digest of all admitted payload blobs."""

        return str(self._receipt["serving_payload_sha256"])

    @property
    def receipt_sha256(self) -> str:
        """Return the digest of the canonical receipt bytes."""

        return self._receipt_sha256

    @property
    def receipt(self) -> Mapping[str, Any]:
        """Return immutable source and publication evidence for transaction ownership."""

        return self._receipt

    @property
    def sidecar(self) -> Mapping[str, Any]:
        """Return immutable receipt-integrity evidence for transaction ownership."""

        return self._sidecar

    def peek_blobs(self) -> tuple[ReleasedBlob, ...]:
        """Return immutable bytes for read-only identity checks without consuming authority."""

        return self._blobs

    def claim_blobs(self) -> tuple[ReleasedBlob, ...]:
        """Consume this capability once and transfer its immutable blobs to a transaction."""

        if self._claimed:
            raise ReleaseSourceError("released payload bytes were already claimed")
        object.__setattr__(self, "_claimed", True)
        return self._blobs

    @classmethod
    def _from_verified(
        cls,
        *,
        blobs: tuple[ReleasedBlob, ...],
        receipt: Mapping[str, Any],
        sidecar: Mapping[str, Any],
    ) -> ReleasedPayload:
        """Construct only after this module has verified source and publication."""

        return cls(
            blobs=blobs,
            receipt=receipt,
            sidecar=sidecar,
            _token=cls._TOKEN,
        )


def claim(
    candidate: object,
) -> tuple[
    tuple[ReleasedBlob, ...],
    str,
    str,
    Mapping[str, Any],
    Mapping[str, Any],
]:
    """Consume one genuine released-payload capability for the transaction owner.

    The class identity check prevents a path-like or structurally similar object
    from crossing the source-admission boundary.  The returned values are exact
    immutable bytes and canonical evidence; no private filesystem stage exists.
    """

    if not isinstance(candidate, ReleasedPayload):
        raise ReleaseSourceError("payload transaction requires an admitted ReleasedPayload")
    return (
        candidate.claim_blobs(),
        candidate.version,
        candidate.receipt_sha256,
        candidate.receipt,
        candidate.sidecar,
    )


def canonical_json(value: Mapping[str, Any]) -> bytes:
    """Return the unique UTF-8 JSON serialization used for release evidence."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def serving_payload_sha256(file_digests: Mapping[str, str]) -> str:
    """Return the canonical aggregate of an explicit serving-file digest map."""

    try:
        return payload_digest.serving_payload_sha256(file_digests)
    except payload_digest.PayloadDigestError as exc:
        raise ReleaseSourceError(str(exc)) from exc


def admit(
    repository: os.PathLike[str] | str,
    *,
    payload_paths: Iterable[str],
    trust_anchor: os.PathLike[str] | str,
    publication: publication.PublishedRelease,
    serving_payload_paths: Iterable[str] | None = None,
    git_path: os.PathLike[str] | str,
    ssh_keygen_path: os.PathLike[str] | str,
) -> ReleasedPayload:
    """Admit exact signed release objects bound to successful dual-forge publication."""

    repo = Path(repository).resolve(strict=True)
    git = _absolute_executable(git_path, "git")
    _absolute_executable(ssh_keygen_path, "ssh-keygen")
    anchor = _external_regular_file(trust_anchor, repo)
    paths = _canonical_payload_paths(payload_paths)
    head = _git_text(git, repo, ("rev-parse", "--verify", "HEAD^{commit}"))
    version = _strict_version(_git_bytes(git, repo, ("show", f"{head}:VERSION")))
    tag_name = f"v{version}"
    tag = f"refs/tags/{tag_name}"
    tag_object = _git_text(git, repo, ("rev-parse", "--verify", tag))
    if _git_text(git, repo, ("cat-file", "-t", tag_object)) != "tag":
        raise ReleaseSourceError(f"{tag} must be an annotated tag object")
    tag_headers = _git_bytes(git, repo, ("cat-file", "tag", tag_object)).split(b"\n\n", 1)[0]
    if f"tag {tag_name}".encode() not in tag_headers.splitlines():
        raise ReleaseSourceError("annotated tag embedded name is not exact vVERSION")
    if b"type commit" not in tag_headers.splitlines():
        raise ReleaseSourceError("annotated tag must directly name a commit")
    commit = _git_text(git, repo, ("rev-parse", "--verify", f"{tag}^{{commit}}"))
    if commit != head:
        raise ReleaseSourceError("annotated release tag must name the direct HEAD commit")
    tree = _git_text(git, repo, ("rev-parse", "--verify", f"{commit}^{{tree}}"))
    publication_evidence = publication_module_evidence(publication)
    _validate_publication(publication_evidence, tag_name, tag_object, commit, tree)
    _validate_anchor_binding(publication_evidence, tag_object, commit, tree, anchor)

    blobs = tuple(_read_blob(git, repo, commit, relative) for relative in paths)
    payload_entries = [
        {
            "path": blob.path,
            "mode": blob.mode,
            "blob_oid": blob.blob_oid,
            "sha256": blob.sha256,
        }
        for blob in blobs
    ]
    serving_paths = (
        paths if serving_payload_paths is None else _canonical_payload_paths(serving_payload_paths)
    )
    if not set(serving_paths).issubset(paths):
        raise ReleaseSourceError("serving payload paths must be part of the admitted payload")
    serving_digest = serving_payload_sha256(
        {blob.path: blob.sha256 for blob in blobs if blob.path in set(serving_paths)}
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "verification_scope": "published-signed-release-source",
        "version": version,
        "tag": tag,
        "tag_object_oid": tag_object,
        "commit_oid": commit,
        "tree_oid": tree,
        "object_format": _git_text(git, repo, ("rev-parse", "--show-object-format")),
        "trust_anchor_sha256": _sha256_file(anchor),
        "serving_payload_sha256": serving_digest,
        "serving_files": list(serving_paths),
        "payload": payload_entries,
        "publication": publication_evidence,
    }
    receipt_bytes = canonical_json(receipt)
    sidecar = {
        "schema_version": RECEIPT_SCHEMA,
        "algorithm": "sha256",
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "serving_payload_sha256": serving_digest,
        "tag_object_oid": tag_object,
        "commit_oid": commit,
        "tree_oid": tree,
    }
    return ReleasedPayload._from_verified(
        blobs=blobs,
        receipt=receipt,
        sidecar=sidecar,
    )


def publication_module_evidence(
    authority: publication.PublishedRelease,
) -> Mapping[str, Any]:
    """Consume the process-local publication authority exactly once."""

    try:
        return _plain_value(publication.consume(authority))
    except publication.PublicationError as exc:
        raise ReleaseSourceError(str(exc)) from exc


def _plain_value(value: Any) -> Any:
    """Copy frozen publication evidence into canonical JSON-compatible values."""

    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _validate_publication(
    evidence: Mapping[str, Any],
    tag: str,
    tag_object_oid: str,
    commit_oid: str,
    tree_oid: str,
) -> None:
    if evidence.get("verified") is not True or evidence.get("tag") != tag:
        raise ReleaseSourceError("publication authority does not name the local release")
    forges = evidence.get("forges")
    if not isinstance(forges, Mapping):
        raise ReleaseSourceError("publication authority has no Forge evidence")
    gitlab = forges.get("gitlab")
    github = forges.get("github")
    if not isinstance(gitlab, Mapping) or not isinstance(github, Mapping):
        raise ReleaseSourceError("publication authority requires GitLab and GitHub evidence")
    if gitlab.get("tag") != tag:
        raise ReleaseSourceError("GitLab publication tag differs from local release")
    if gitlab.get("tag_object_oid") != tag_object_oid:
        raise ReleaseSourceError("GitLab publication tag object differs from local release")
    if gitlab.get("commit_oid") != commit_oid:
        raise ReleaseSourceError("GitLab publication commit differs from local release")
    if gitlab.get("tree_oid") != tree_oid:
        raise ReleaseSourceError("GitLab publication tree differs from local release")
    if github.get("tag") != tag or github.get("tree_oid") != tree_oid:
        raise ReleaseSourceError("GitHub publication identity differs from local release tree")


def _validate_anchor_binding(
    evidence: Mapping[str, Any],
    tag_object_oid: str,
    commit_oid: str,
    tree_oid: str,
    anchor: Path,
) -> None:
    """Bind the local released checkout to either already-verified Forge plane."""

    forges = evidence.get("forges")
    assert isinstance(forges, Mapping)
    anchor_sha256 = _sha256_file(anchor)
    matches = []
    for provider in ("gitlab", "github"):
        forge = forges.get(provider)
        if not isinstance(forge, Mapping):
            continue
        if (
            forge.get("anchor_sha256") == anchor_sha256
            and forge.get("tag_object_oid") == tag_object_oid
            and forge.get("commit_oid") == commit_oid
            and forge.get("tree_oid") == tree_oid
            and forge.get("signature_verified") is True
        ):
            matches.append(provider)
    if len(matches) != 1:
        raise ReleaseSourceError(
            "local release identity and trust anchor must match exactly one verified Forge plane"
        )


def _read_blob(
    git: Path,
    repo: Path,
    commit: str,
    relative: str,
) -> ReleasedBlob:
    entry = _git_text(git, repo, ("ls-tree", commit, "--", relative))
    match = re.fullmatch(r"(100644|100755) blob ([0-9a-f]{40,64})\t(.+)", entry)
    if match is None or match.group(3) != relative:
        raise ReleaseSourceError(f"payload must have a committed regular blob mode: {relative}")
    mode = cast("Literal['100644', '100755']", match.group(1))
    blob_oid = match.group(2)
    content = _git_bytes(git, repo, ("cat-file", "blob", blob_oid))
    return ReleasedBlob(
        path=relative,
        mode=mode,
        blob_oid=blob_oid,
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


def _isolated_git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("GIT_") and name not in _ALLOWED_GIT_ENV:
            environment.pop(name)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
    )
    return environment


def _run_git(git: Path, repo: Path, arguments: tuple[str, ...]) -> bytes:
    try:
        return subprocess.run(
            [str(git), "-C", str(repo), "--no-replace-objects", *arguments],
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
    result: list[str] = []
    for raw in paths:
        value = _canonical_payload_path(raw)
        if value in result:
            raise ReleaseSourceError(f"payload path is not unique and canonical: {value!r}")
        result.append(value)
    if not result or "VERSION" not in result:
        raise ReleaseSourceError("payload paths must include VERSION")
    return tuple(result)


def _canonical_payload_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseSourceError("payload path must be a non-empty string")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
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
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise ReleaseSourceError(f"{label} path must name an executable regular file")
    return resolved


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


def _payload_digest(payload: list[dict[str, str]]) -> str:
    return hashlib.sha256(canonical_json({"payload": payload})).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


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
