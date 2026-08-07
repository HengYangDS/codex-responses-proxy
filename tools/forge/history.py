#!/usr/bin/env python3
"""Index and join identity-neutral Git commit history fingerprints."""

from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

from cyclopts import App


class HistoryError(ValueError):
    """Forge histories cannot be mapped without weakening admission."""


def build_index(repository: Path, commits: list[str]) -> list[tuple[str, str]]:
    """Return one identity-neutral fingerprint for every named commit."""

    object_format = _git_output(repository, "rev-parse", "--show-object-format")
    hash_factory = {"sha1": hashlib.sha1, "sha256": hashlib.sha256}.get(object_format)
    if hash_factory is None:
        raise HistoryError(f"unsupported Git object format: {object_format}")
    result = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "--batch"],
        input="".join(f"{commit}\n" for commit in commits).encode("ascii"),
        capture_output=True,
        check=True,
    )
    stream = BytesIO(result.stdout)
    rows: list[tuple[str, str]] = []
    for commit in commits:
        response = stream.readline().decode("ascii").rstrip("\n").split()
        if len(response) != 3 or response[0] != commit or response[1] != "commit":
            raise HistoryError(f"cannot read commit object: {commit}")
        try:
            size = int(response[2])
            if size < 0:
                raise ValueError
        except ValueError as error:
            raise HistoryError(f"malformed Git batch size: {commit}") from error
        raw = stream.read(size)
        if stream.read(1) != b"\n":
            raise HistoryError(f"malformed Git batch response: {commit}")
        rows.append((_fingerprint(raw, hash_factory), commit))
    if stream.read():
        raise HistoryError("Git batch returned unexpected trailing data")
    return rows


def join_indexes(
    canonical: list[tuple[str, str]],
    projected: list[tuple[str, str]],
    remote_commit: str,
) -> tuple[str, list[tuple[str, str]]]:
    """Return the unique canonical base and existing projection mapping."""

    canonical_by_fingerprint: dict[str, list[str]] = defaultdict(list)
    projected_by_fingerprint: dict[str, list[str]] = defaultdict(list)
    projected_fingerprint_by_commit: dict[str, str] = {}
    for fingerprint, commit in canonical:
        canonical_by_fingerprint[fingerprint].append(commit)
    for fingerprint, commit in projected:
        projected_by_fingerprint[fingerprint].append(commit)
        projected_fingerprint_by_commit[commit] = fingerprint
    if remote_commit not in projected_fingerprint_by_commit:
        raise HistoryError("GitHub remote tip is absent from its history index")
    base_matches = canonical_by_fingerprint[projected_fingerprint_by_commit[remote_commit]]
    if len(base_matches) != 1:
        raise HistoryError(
            "GitHub branch tree diverges from canonical history; "
            f"found {len(base_matches)} identity-neutral matches"
        )
    mapping: list[tuple[str, str]] = []
    for fingerprint, canonical_commit in canonical:
        projected_matches = projected_by_fingerprint.get(fingerprint, [])
        if len(projected_matches) > 1:
            raise HistoryError(
                f"canonical commit has ambiguous GitHub history matches: {canonical_commit}"
            )
        if projected_matches:
            mapping.append((canonical_commit, projected_matches[0]))
    return base_matches[0], mapping


def map_histories(
    repository: Path,
    canonical_commits: list[str],
    projected_commits: list[str],
    remote_commit: str,
) -> tuple[str, list[tuple[str, str]]]:
    """Index both histories once and return their unique admitted mapping."""

    return join_indexes(
        build_index(repository, canonical_commits),
        build_index(repository, projected_commits),
        remote_commit,
    )


def _command(
    *, repository: Path, canonical: Path, projected: Path, remote_commit: str, output: Path
) -> None:
    """Map two commit lists for the Forge projector in one bounded process."""

    try:
        base, mapping = map_histories(
            repository,
            canonical.read_text(encoding="utf-8").splitlines(),
            projected.read_text(encoding="utf-8").splitlines(),
            remote_commit,
        )
        _write_rows(output, mapping)
        print(base)
    except (HistoryError, OSError, subprocess.CalledProcessError, UnicodeError) as error:
        raise SystemExit(str(error)) from error


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run history mapping through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


def _fingerprint(raw: bytes, hash_factory: Callable[[bytes], Any]) -> str:
    try:
        headers, message = raw.split(b"\n\n", 1)
    except ValueError as error:
        raise HistoryError("commit object has no message boundary") from error
    lines = headers.splitlines()
    try:
        tree = next(line[5:] for line in lines if line.startswith(b"tree "))
        author = next(line[7:] for line in lines if line.startswith(b"author "))
        committer = next(line[10:] for line in lines if line.startswith(b"committer "))
    except StopIteration as error:
        raise HistoryError("commit object is missing a required identity header") from error
    payload = (
        f"parents={sum(line.startswith(b'parent ') for line in lines)}\n".encode()
        + tree
        + b"\n"
        + _strict_iso8601(author).encode()
        + b"\n"
        + _strict_iso8601(committer).encode()
        + b"\n---message---\n"
        + message
    )
    return hash_factory(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def _strict_iso8601(identity: bytes) -> str:
    try:
        timestamp_text, offset_text = identity.rsplit(b" ", 2)[-2:]
        if len(offset_text) != 5 or offset_text[:1] not in (b"+", b"-"):
            raise ValueError
        sign = 1 if offset_text[:1] == b"+" else -1
        zone = dt.timezone(
            sign * dt.timedelta(hours=int(offset_text[1:3]), minutes=int(offset_text[3:5]))
        )
        value = dt.datetime.fromtimestamp(int(timestamp_text), zone).isoformat(timespec="seconds")
        return value.replace("+00:00", "Z") if offset_text[1:] == b"0000" else value
    except (OverflowError, ValueError) as error:
        raise HistoryError("commit identity has an invalid Git timestamp") from error


def _git_output(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()


def _write_rows(path: Path, rows: list[tuple[str, str]]) -> None:
    path.write_text("".join(f"{left}\t{right}\n" for left, right in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
