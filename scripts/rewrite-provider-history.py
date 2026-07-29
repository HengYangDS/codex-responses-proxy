#!/usr/bin/env python3
"""Rebuild one commit DAG with a single provider identity and SSH signature."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommitRecord:
    """Source commit data that must survive provider-specific re-signing."""

    oid: str
    tree: str
    parents: tuple[str, ...]
    author_date: str
    committer_date: str
    message: bytes


def run(
    repository: Path,
    *args: str,
    input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git inside ``repository`` and return its captured byte streams."""

    completed = subprocess.run(
        ("git", "-C", str(repository), *args),
        input=input_bytes,
        capture_output=True,
        check=False,
        env=environment,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).decode(errors="replace").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return completed


def output(repository: Path, *args: str) -> str:
    """Return stripped UTF-8 output from a successful Git command."""

    return run(repository, *args).stdout.decode().strip()


def commit_message(repository: Path, oid: str) -> bytes:
    """Return the exact message bytes from a commit object."""

    raw = run(repository, "cat-file", "commit", oid).stdout
    marker = raw.find(b"\n\n")
    if marker < 0:
        raise RuntimeError(f"commit object lacks a message boundary: {oid}")
    return raw[marker + 2 :]


def records(repository: Path, source_ref: str) -> list[CommitRecord]:
    """Return the source DAG in parent-before-child order."""

    lines = output(repository, "rev-list", "--reverse", "--topo-order", "--parents", source_ref)
    result: list[CommitRecord] = []
    for line in lines.splitlines():
        oid, *parents = line.split()
        fields = output(repository, "show", "-s", "--format=%T%x00%aI%x00%cI", oid).split("\0")
        if len(fields) != 3:
            raise RuntimeError(f"cannot read commit metadata: {oid}")
        result.append(
            CommitRecord(
                oid=oid,
                tree=fields[0],
                parents=tuple(parents),
                author_date=fields[1],
                committer_date=fields[2],
                message=commit_message(repository, oid),
            )
        )
    if not result:
        raise RuntimeError(f"source ref has no commits: {source_ref}")
    return result


def signing_environment(record: CommitRecord, name: str, email: str) -> dict[str, str]:
    """Build the exact author and committer environment for one rewritten commit."""

    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": record.author_date,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": record.committer_date,
        }
    )
    return environment


def rewrite(
    repository: Path,
    source_ref: str,
    target_ref: str,
    name: str,
    email: str,
    signing_key: Path,
    signing_program: Path,
    allowed_signers: Path,
) -> str:
    """Rebuild ``source_ref`` and atomically set ``target_ref`` to its signed tip."""

    source_records = records(repository, source_ref)
    rewritten: dict[str, str] = {}
    for record in source_records:
        parent_arguments = tuple(
            argument for parent in record.parents for argument in ("-p", rewritten[parent])
        )
        completed = run(
            repository,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            "user.useConfigOnly=true",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={signing_program}",
            "-c",
            f"user.signingkey={signing_key}",
            "commit-tree",
            "-S",
            record.tree,
            *parent_arguments,
            input_bytes=record.message,
            environment=signing_environment(record, name, email),
        )
        rewritten[record.oid] = completed.stdout.decode().strip()
    tip = rewritten[source_records[-1].oid]
    run(repository, "update-ref", target_ref, tip)
    verify_rewrite(
        repository,
        source_records=source_records,
        target_ref=target_ref,
        name=name,
        email=email,
        allowed_signers=allowed_signers,
    )
    return tip


def verify_rewrite(
    repository: Path,
    *,
    source_records: list[CommitRecord],
    target_ref: str,
    name: str,
    email: str,
    allowed_signers: Path,
) -> None:
    """Verify topology, semantic metadata, identity, and every rewritten signature."""

    target_records = records(repository, target_ref)
    if len(source_records) != len(target_records):
        raise RuntimeError("rewritten history changed the commit count")
    source_index = {record.oid: index for index, record in enumerate(source_records)}
    target_index = {record.oid: index for index, record in enumerate(target_records)}
    for source, target in zip(source_records, target_records, strict=True):
        source_parent_shape = tuple(source_index[parent] for parent in source.parents)
        target_parent_shape = tuple(target_index[parent] for parent in target.parents)
        if (
            source.tree,
            source_parent_shape,
            source.author_date,
            source.committer_date,
            source.message,
        ) != (
            target.tree,
            target_parent_shape,
            target.author_date,
            target.committer_date,
            target.message,
        ):
            raise RuntimeError(f"rewritten commit changed source semantics: {source.oid}")
        identity = output(repository, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", target.oid)
        if identity.split("\0") != [name, email, name, email]:
            raise RuntimeError(f"rewritten commit has the wrong provider identity: {target.oid}")
        run(
            repository,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed_signers}",
            "verify-commit",
            target.oid,
        )


def main() -> None:
    """Parse the provider contract and print the new signed tip."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--signing-program", type=Path, required=True)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.repository, args.signing_key, args.signing_program, args.allowed_signers):
        if not path.exists():
            raise SystemExit(f"required provider-history input is unavailable: {path}")
    try:
        tip = rewrite(
            args.repository.resolve(),
            args.source_ref,
            args.target_ref,
            args.name,
            args.email,
            args.signing_key.resolve(),
            args.signing_program.resolve(),
            args.allowed_signers.resolve(),
        )
    except RuntimeError as exc:
        raise SystemExit(f"provider history rewrite failed: {exc}") from exc
    print(tip)


if __name__ == "__main__":
    main()
