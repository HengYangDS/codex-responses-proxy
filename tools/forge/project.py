"""Publish exact local Git objects to one optional Forge peer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from tools.forge import runner_admission
from tools.git_environment import isolated_config_environment


class ProjectionError(RuntimeError):
    """Exact local-object publication cannot complete safely."""


def _git(
    root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one captured Git operation."""

    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            check=False,
            capture_output=True,
            text=True,
            env=isolated_config_environment(),
        )
    except OSError as error:
        raise ProjectionError("Git publication operation is unavailable") from error
    if check and result.returncode:
        raise ProjectionError((result.stderr or result.stdout).strip() or "Git publication failed")
    return result


def _output(root: Path, *args: str) -> str:
    """Return stripped stdout from one successful Git operation."""

    return _git(root, *args).stdout.strip()


def _local_branch(root: Path, source_ref: str) -> tuple[str, str]:
    """Resolve one admitted local publication branch and its commit."""

    if source_ref != "main" and not source_ref.startswith("proposal/"):
        raise ProjectionError("publication branch must be main or proposal/*")
    ref = _output(root, "rev-parse", "--symbolic-full-name", "--verify", source_ref)
    if ref != f"refs/heads/{source_ref}":
        raise ProjectionError(f"publication source is not a local branch: {source_ref}")
    return ref, _output(root, "rev-parse", "--verify", f"{ref}^{{commit}}")


def _verify_local_identity(root: Path, commit: str, email: str, allowed_signers: Path) -> None:
    """Verify the unchanged product commit against the selected peer policy."""

    if not allowed_signers.is_file() or allowed_signers.is_symlink():
        raise ProjectionError("commit trust anchor is unavailable")
    identities = _output(root, "show", "-s", "--format=%ae%n%ce", commit).splitlines()
    if identities != [email, email]:
        raise ProjectionError("local commit author and committer email do not match peer policy")
    result = _git(
        root,
        "-c",
        "gpg.format=ssh",
        "-c",
        "gpg.ssh.program=ssh-keygen",
        "-c",
        f"gpg.ssh.allowedSignersFile={allowed_signers.resolve()}",
        "verify-commit",
        commit,
        check=False,
    )
    if result.returncode:
        raise ProjectionError("local commit does not have a trusted signature")


def _remote_tip(root: Path, remote: str, branch: str) -> str | None:
    """Read one remote branch without creating a tracking ref."""

    result = _output(root, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
    if not result:
        return None
    fields = result.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        raise ProjectionError(f"remote branch observation is malformed: {branch}")
    return fields[0]


def _fetch_remote_branch(root: Path, remote: str, branch: str) -> None:
    """Materialize one observed remote branch object for an ancestry check."""

    _git(root, "fetch", "--quiet", "--no-tags", remote, f"refs/heads/{branch}")


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Return Git ancestry while preserving operational failures."""

    result = _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode in {0, 1}:
        return result.returncode == 0
    raise ProjectionError(result.stderr.strip() or "Git ancestry check failed")


def _refspecs(source: str, source_ref: str) -> tuple[tuple[str, str], ...]:
    """Return the exact remote refs owned by one publication operation."""

    if source_ref == "main":
        return (("main", source), ("dev", source))
    return ((source_ref, source),)


def project(
    *,
    root: Path,
    provider: str,
    source_ref: str,
    remote: str,
    email: str,
    allowed_signers: Path,
    expected_remote_tips: dict[str, str] | None = None,
    repository_coordinate: str | None = None,
    runner_tag: str | None = None,
) -> str:
    """Atomically publish one exact local commit to one selected Forge."""

    if provider not in {"gitlab", "github"}:
        raise ProjectionError("provider must be gitlab or github")
    if _output(root, "status", "--porcelain"):
        raise ProjectionError("refusing Forge publication with a dirty checkout")
    _, source = _local_branch(root, source_ref)
    _verify_local_identity(root, source, email, allowed_signers)
    if repository_coordinate:
        if provider == "gitlab":
            runner_admission._gitlab(repository_coordinate, runner_tag)
        else:
            runner_admission._github(repository_coordinate)

    refspecs = _refspecs(source, source_ref)
    arguments = ["push", "--atomic"]
    for branch, _ in refspecs:
        remote_tip = _remote_tip(root, remote, branch)
        if not remote_tip:
            arguments.append(f"--force-with-lease=refs/heads/{branch}:{'0' * 40}")
            continue
        if remote_tip == source:
            continue
        _fetch_remote_branch(root, remote, branch)
        if _is_ancestor(root, remote_tip, source):
            continue
        expected = (expected_remote_tips or {}).get(branch)
        if expected != remote_tip:
            raise ProjectionError(
                f"remote {branch} diverges; exact expected tip is required for cutover"
            )
        arguments.append(f"--force-with-lease=refs/heads/{branch}:{remote_tip}")
    arguments.append(remote)
    arguments.extend(f"{commit}:refs/heads/{branch}" for branch, commit in refspecs)
    _git(root, *arguments)

    for branch, _ in refspecs:
        if _remote_tip(root, remote, branch) != source:
            raise ProjectionError(f"remote {branch} does not equal the local product commit")
    return source


def _parse_expected(values: tuple[str, ...]) -> dict[str, str]:
    """Parse explicit branch=OID cutover coordinates."""

    expected: dict[str, str] = {}
    for value in values:
        branch, separator, oid = value.partition("=")
        if not separator or not branch or not oid or branch in expected:
            raise ProjectionError("expected remote tip must be a unique branch=OID value")
        expected[branch] = oid
    return expected


def _command(
    *,
    provider: str,
    email: str,
    allowed_signers: Path,
    source_ref: str = "main",
    remote: str | None = None,
    root: Path | None = None,
    expect_remote_tip: tuple[str, ...] = (),
    repository: str | None = None,
    runner_tag: str | None = None,
    as_json: Annotated[bool, Parameter(name="--json", negative=False)] = False,
) -> None:
    """Publish one local branch to exactly one selected peer."""

    root = (root or Path.cwd()).resolve()
    selected_remote = remote or ("origin" if provider == "gitlab" else "github")
    try:
        published = project(
            root=root,
            provider=provider,
            source_ref=source_ref,
            remote=selected_remote,
            email=email,
            allowed_signers=allowed_signers,
            expected_remote_tips=_parse_expected(expect_remote_tip),
            repository_coordinate=repository,
            runner_tag=runner_tag,
        )
    except (ProjectionError, runner_admission.AdmissionError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    result = {"provider": provider, "commit": published, "source_ref": source_ref}
    print(
        json.dumps(result, sort_keys=True) if as_json else f"{provider} synchronized: {published}"
    )


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run exact publication through the repository parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
