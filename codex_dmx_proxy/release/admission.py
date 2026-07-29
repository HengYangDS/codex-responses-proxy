"""Admit published signed Git source into an opaque immutable payload bundle.

This module owns source identity only.  It reads exact committed blobs from a
signed annotated release tag and binds them to externally verified GitLab and
GitHub publication evidence.  It never writes the installed projection or any
installed state; :mod:`codex_dmx_proxy.release.transaction` owns that later
transaction.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import weakref
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, cast

from codex_dmx_proxy.release import digest, inventory
from codex_dmx_proxy.release import publication


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


def _authority_kernel() -> tuple[type[ReleasedPayload], Any, Any]:
    """Create a closure-sealed released-payload capability and its issuer."""

    token = object()
    issued: weakref.WeakSet[Any] = weakref.WeakSet()

    class ReleasedPayload:
        """Opaque single-use authority over one exact released payload projection."""

        __slots__ = ("_blobs", "_claimed", "_receipt", "_receipt_sha256", "_sidecar", "__weakref__")
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
            if _token is not token:
                raise TypeError("ReleasedPayload is opaque; use admission.admit()")
            receipt_sha256 = hashlib.sha256(digest.canonical_json(receipt)).hexdigest()
            object.__setattr__(self, "_blobs", blobs)
            object.__setattr__(self, "_receipt", digest.freeze_mapping(receipt))
            object.__setattr__(self, "_sidecar", digest.freeze_mapping(sidecar))
            object.__setattr__(self, "_receipt_sha256", receipt_sha256)
            object.__setattr__(self, "_claimed", False)

        def __setattr__(self, name: str, value: object) -> None:
            raise ReleaseSourceError("released payload capability is immutable")

        @property
        def version(self) -> str:
            """Return the admitted strict release version."""

            return str(self._receipt["version"])

        @property
        def serving_payload_sha256(self) -> str:
            """Return the aggregate digest of admitted serving files, including ``VERSION``."""

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

        def _claim_blobs(self) -> tuple[ReleasedBlob, ...]:
            if self._claimed:
                raise ReleaseSourceError("released payload bytes were already claimed")
            object.__setattr__(self, "_claimed", True)
            return self._blobs

        def _verify_integrity(self) -> None:
            receipt_digest = hashlib.sha256(
                digest.canonical_json(_plain_value(self._receipt))
            ).hexdigest()
            entries = self._receipt.get("payload")
            bound_fields = (
                "tag_object_oid",
                "commit_oid",
                "tree_oid",
                "serving_payload_sha256",
            )
            if (
                receipt_digest != self._receipt_sha256
                or self._sidecar.get("schema_version") != RECEIPT_SCHEMA
                or self._sidecar.get("algorithm") != "sha256"
                or self._sidecar.get("receipt_sha256") != receipt_digest
                or any(
                    self._sidecar.get(field) != self._receipt.get(field) for field in bound_fields
                )
                or not isinstance(entries, tuple)
                or len(entries) != len(self._blobs)
            ):
                raise ReleaseSourceError("released payload integrity check failed")
            for entry, blob in zip(entries, self._blobs, strict=True):
                expected = {
                    "path": blob.path,
                    "mode": blob.mode,
                    "blob_oid": blob.blob_oid,
                    "sha256": hashlib.sha256(blob.content).hexdigest(),
                }
                if (
                    not isinstance(entry, Mapping)
                    or set(entry) != set(expected)
                    or any(dict(entry).get(field) != value for field, value in expected.items())
                    or blob.sha256 != expected["sha256"]
                ):
                    raise ReleaseSourceError("released payload integrity check failed")
            serving_paths = self._receipt.get("serving_files")
            if not isinstance(serving_paths, tuple):
                raise ReleaseSourceError("released payload integrity check failed")
            try:
                serving_digest = serving_payload_sha256(
                    {blob.path: blob.sha256 for blob in self._blobs if blob.path in serving_paths}
                )
            except ReleaseSourceError as error:
                raise ReleaseSourceError("released payload integrity check failed") from error
            if serving_digest != self._receipt.get("serving_payload_sha256"):
                raise ReleaseSourceError("released payload integrity check failed")

    def mint(
        blobs: tuple[ReleasedBlob, ...],
        receipt: Mapping[str, Any],
        sidecar: Mapping[str, Any],
    ) -> ReleasedPayload:
        candidate = ReleasedPayload(blobs=blobs, receipt=receipt, sidecar=sidecar, _token=token)
        issued.add(candidate)
        return candidate

    def consume(
        candidate: object,
    ) -> tuple[
        tuple[ReleasedBlob, ...],
        str,
        str,
        Mapping[str, Any],
        Mapping[str, Any],
    ]:
        if type(candidate) is not ReleasedPayload or candidate not in issued:
            raise ReleaseSourceError("payload transaction requires an admitted ReleasedPayload")
        candidate._verify_integrity()
        return (
            candidate._claim_blobs(),
            candidate.version,
            candidate.receipt_sha256,
            candidate.receipt,
            candidate.sidecar,
        )

    def admit(
        repository: os.PathLike[str] | str,
        *,
        payload_paths: Iterable[str],
        trust_anchor: os.PathLike[str] | str,
        publication: publication.PublishedRelease,
        git_path: os.PathLike[str] | str,
        ssh_keygen_path: os.PathLike[str] | str,
    ) -> ReleasedPayload:
        """Admit exact signed release objects bound to successful dual-Forge publication."""

        return _admit_verified(
            mint,
            repository,
            payload_paths=payload_paths,
            trust_anchor=trust_anchor,
            publication=publication,
            git_path=git_path,
            ssh_keygen_path=ssh_keygen_path,
        )

    return ReleasedPayload, consume, admit


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
    publication: publication.PublishedRelease,
    git_path: os.PathLike[str] | str,
    ssh_keygen_path: os.PathLike[str] | str,
) -> ReleasedPayload:
    """Admit exact signed release objects bound to successful dual-forge publication."""

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
    evidence = publication_module_evidence(publication)
    identity = {
        "tag_object_oid": tag_object,
        "commit_oid": commit,
        "tree_oid": tree,
    }
    _validate_publication(evidence, tag_name, **identity)
    _validate_anchor_binding(evidence, anchor=anchor, **identity)
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
        "verification_scope": "published-signed-release-source",
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
        "publication": evidence,
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
    gitlab, github = (forges.get(provider) for provider in ("gitlab", "github"))
    if not isinstance(gitlab, Mapping) or not isinstance(github, Mapping):
        raise ReleaseSourceError("publication authority requires GitLab and GitHub evidence")
    expectations = (
        ("tag", tag, "tag"),
        ("tag_object_oid", tag_object_oid, "tag object"),
        ("commit_oid", commit_oid, "commit"),
        ("tree_oid", tree_oid, "tree"),
    )
    mismatch = next(
        (label for field, expected, label in expectations if gitlab.get(field) != expected),
        None,
    )
    if mismatch:
        raise ReleaseSourceError(f"GitLab publication {mismatch} differs from local release")
    if (github.get("tag"), github.get("tree_oid")) != (tag, tree_oid):
        raise ReleaseSourceError("GitHub publication identity differs from local release tree")


def _validate_anchor_binding(
    evidence: Mapping[str, Any],
    tag_object_oid: str,
    commit_oid: str,
    tree_oid: str,
    anchor: Path,
) -> None:
    """Bind the local released checkout to exactly one already-verified Forge plane."""

    forges = evidence.get("forges")
    assert isinstance(forges, Mapping)
    expected = {
        "anchor_sha256": _sha256_file(anchor),
        "tag_object_oid": tag_object_oid,
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "signature_verified": True,
    }
    matches = sum(
        isinstance(forge, Mapping) and expected.items() <= forge.items()
        for forge in forges.values()
    )
    if matches != 1:
        raise ReleaseSourceError(
            "local release identity and trust anchor must match exactly one verified Forge plane"
        )


def _read_blob(git: Path, repo: Path, commit: str, relative: str) -> ReleasedBlob:
    entry = _git_text(git, repo, ("ls-tree", commit, "--", relative))
    metadata, separator, path = entry.partition("\t")
    mode, kind, blob_oid = (*metadata.split(), "", "")[:3]
    if (mode, kind, separator, path) not in {
        ("100644", "blob", "\t", relative),
        ("100755", "blob", "\t", relative),
    } or re.fullmatch(r"[0-9a-f]{40,64}", blob_oid) is None:
        raise ReleaseSourceError(f"payload must have a committed regular blob mode: {relative}")
    content = _git_bytes(git, repo, ("cat-file", "blob", blob_oid))
    return ReleasedBlob(
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


ReleasedPayload, claim, admit = _authority_kernel()
del _authority_kernel
