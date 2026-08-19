"""Read-only exact-object parity evidence for optional Forge peers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Annotated, Any

from cyclopts import App, Parameter

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_POLICY = ROOT / ".ethos/workspace.toml"
PERSISTENT_BRANCHES = ("main", "dev")


def _environment() -> dict[str, str]:
    """Return a Git environment independent from personal configuration."""

    environment = os.environ.copy()
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return environment


def command(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a captured subprocess and raise a concise error when requested."""

    result = subprocess.run(
        args,
        cwd=cwd,
        env=_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "command failed")
    return result


def output(*args: str, cwd: Path = ROOT) -> str:
    """Return stripped standard output for a successful command."""

    return command(*args, cwd=cwd).stdout.strip()


def branches_for_audit(
    path: Path = WORKSPACE_POLICY,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return persistent local and remote branches from repository policy."""

    try:
        roles = tomllib.loads(path.read_text(encoding="utf-8"))["branch_roles"]
        release = roles["release_branch"]
        accepted = roles["accepted_branch"]
        candidate = roles["candidate_branch"]
    except (KeyError, OSError, TypeError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError("repository branch-role policy is unavailable or invalid") from error
    if not all(isinstance(branch, str) and branch for branch in (release, accepted, candidate)):
        raise RuntimeError("repository branch-role policy is incomplete")
    return frozenset((release, accepted, candidate)), frozenset((release, accepted))


def remote_branches(root: Path, remote: str, expected: frozenset[str]) -> list[str]:
    """Return provider branches outside the declared persistent roles."""

    refs = output("git", "ls-remote", "--heads", remote, cwd=root).splitlines()
    return sorted(
        ref.removeprefix("refs/heads/")
        for line in refs
        if len(parts := line.split("\t", 1)) == 2
        for ref in [parts[1]]
        if ref.removeprefix("refs/heads/") not in expected
    )


def local_branches(root: Path, expected: frozenset[str]) -> list[str]:
    """Return local branches outside the declared persistent roles."""

    return sorted(
        branch
        for branch in output(
            "git", "for-each-ref", "refs/heads", "--format=%(refname:short)", cwd=root
        ).splitlines()
        if branch not in expected
    )


def local_branch_oids(root: Path) -> dict[str, str]:
    """Return exact local persistent branch commits."""

    return {
        branch: output("git", "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}", cwd=root)
        for branch in PERSISTENT_BRANCHES
    }


def remote_branch_oids(root: Path, remote: str) -> dict[str, str]:
    """Return exact remote persistent branch commits."""

    refs = output(
        "git",
        "ls-remote",
        "--heads",
        remote,
        *(f"refs/heads/{branch}" for branch in PERSISTENT_BRANCHES),
        cwd=root,
    ).splitlines()
    observed = {
        ref.removeprefix("refs/heads/"): oid
        for line in refs
        if len(parts := line.split("\t", 1)) == 2
        for oid, ref in [parts]
    }
    if set(observed) != set(PERSISTENT_BRANCHES):
        raise RuntimeError(f"{remote} does not expose exact main and dev refs")
    return observed


def exact_branch_parity(
    local: dict[str, str], gitlab: dict[str, str], github: dict[str, str]
) -> bool:
    """Return whether every persistent ref names one product commit."""

    values = [
        mapping[branch] for mapping in (local, gitlab, github) for branch in PERSISTENT_BRANCHES
    ]
    return len(set(values)) == 1


def _tag_names(repository: Path) -> list[str]:
    """Return local SemVer tag names."""

    return output("git", "tag", "--list", "v[0-9]*", cwd=repository).splitlines()


def _tag_evidence(repository: Path, tags: list[str], anchor: Path) -> dict[str, dict[str, object]]:
    """Describe and verify exact annotated tag objects in one repository."""

    evidence: dict[str, dict[str, object]] = {}
    for tag in tags:
        reference = f"refs/tags/{tag}"
        annotated = output("git", "cat-file", "-t", reference, cwd=repository) == "tag"
        signature = (
            annotated
            and command(
                "git",
                "-c",
                "gpg.format=ssh",
                "-c",
                "gpg.ssh.program=ssh-keygen",
                "-c",
                f"gpg.ssh.allowedSignersFile={anchor.resolve()}",
                "verify-tag",
                tag,
                cwd=repository,
                check=False,
            ).returncode
            == 0
        )
        evidence[tag] = {
            "tag_object_oid": output("git", "rev-parse", reference, cwd=repository),
            "commit_oid": output("git", "rev-parse", f"{reference}^{{commit}}", cwd=repository),
            "tree_oid": output("git", "rev-parse", f"{reference}^{{tree}}", cwd=repository),
            "annotated": annotated,
            "signature_verified": signature,
        }
    return evidence


def local_release_evidence(root: Path, anchor: Path) -> dict[str, dict[str, object]]:
    """Return local release-tag object evidence."""

    return _tag_evidence(root, _tag_names(root), anchor)


def provider_release_evidence(
    root: Path, remote: str, anchor: Path
) -> dict[str, dict[str, object]]:
    """Fetch and verify one peer's release-tag objects in isolation."""

    remote_url = output("git", "config", "--local", "--get", f"remote.{remote}.url", cwd=root)
    with tempfile.TemporaryDirectory(prefix="codex-responses-proxy-parity-") as name:
        repository = Path(name) / "repository.git"
        command("git", "init", "--quiet", "--bare", str(repository), cwd=root)
        command(
            "git",
            "-C",
            str(repository),
            "fetch",
            "--quiet",
            "--force",
            "--no-tags",
            remote_url,
            "+refs/tags/*:refs/tags/*",
            cwd=root,
        )
        return _tag_evidence(repository, _tag_names(repository), anchor)


def exact_tag_parity(
    local: dict[str, dict[str, object]],
    gitlab: dict[str, dict[str, object]],
    github: dict[str, dict[str, object]],
) -> bool:
    """Return whether all peers expose the same verified annotated tag objects."""

    if not local or set(local) != set(gitlab) or set(local) != set(github):
        return False
    return all(
        local[tag] == gitlab[tag] == github[tag]
        and local[tag]["annotated"] is True
        and local[tag]["signature_verified"] is True
        for tag in local
    )


def _verify_product_commit(root: Path, commit: str, anchor: Path, email: str) -> bool:
    """Verify the shared commit identity once at the local authority."""

    identities = output("git", "show", "-s", "--format=%ae%n%ce", commit, cwd=root).splitlines()
    return (
        identities == [email, email]
        and command(
            "git",
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.ssh.program=ssh-keygen",
            "-c",
            f"gpg.ssh.allowedSignersFile={anchor.resolve()}",
            "verify-commit",
            commit,
            cwd=root,
            check=False,
        ).returncode
        == 0
    )


def audit(
    *,
    root: Path,
    commit_anchor: Path,
    author_email: str,
    tag_anchor: Path,
    gitlab_remote: str,
    github_remote: str,
) -> dict[str, Any]:
    """Collect exact local/GitLab/GitHub parity and housekeeping evidence."""

    local_refs = local_branch_oids(root)
    gitlab_refs = remote_branch_oids(root, gitlab_remote)
    github_refs = remote_branch_oids(root, github_remote)
    branches_equal = exact_branch_parity(local_refs, gitlab_refs, github_refs)
    local_tags = local_release_evidence(root, tag_anchor)
    gitlab_tags = provider_release_evidence(root, gitlab_remote, tag_anchor)
    github_tags = provider_release_evidence(root, github_remote, tag_anchor)
    tags_equal = exact_tag_parity(local_tags, gitlab_tags, github_tags)
    local_roles, remote_roles = branches_for_audit(root / ".ethos/workspace.toml")
    housekeeping = {
        "local_unexpected_branches": local_branches(root, local_roles),
        "gitlab_unexpected_branches": remote_branches(root, gitlab_remote, remote_roles),
        "github_unexpected_branches": remote_branches(root, github_remote, remote_roles),
        "worktrees": output("git", "worktree", "list", "--porcelain", cwd=root).splitlines(),
    }
    commit_verified = _verify_product_commit(root, local_refs["main"], commit_anchor, author_email)
    result: dict[str, Any] = {
        "branches": {"local": local_refs, "gitlab": gitlab_refs, "github": github_refs},
        "branch_object_parity": branches_equal,
        "product_commit_verified": commit_verified,
        "tags": {"local": local_tags, "gitlab": gitlab_tags, "github": github_tags},
        "tag_object_parity": tags_equal,
        "housekeeping": housekeeping,
    }
    result["ok"] = (
        branches_equal
        and commit_verified
        and tags_equal
        and not housekeeping["local_unexpected_branches"]
        and not housekeeping["gitlab_unexpected_branches"]
        and not housekeeping["github_unexpected_branches"]
    )
    return result


def _command(
    *,
    commit_anchor: Path,
    author_email: str,
    tag_anchor: Path,
    gitlab_remote: str = "origin",
    github_remote: str = "github",
    root: Path | None = None,
    as_json: Annotated[bool, Parameter(name="--json", negative=False)] = False,
) -> None:
    """Collect live exact-object parity from explicit product trust inputs."""

    root = (root or Path.cwd()).resolve()
    for path in (commit_anchor, tag_anchor):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"required publication trust input is unavailable: {path}")
    try:
        evidence = audit(
            root=root,
            commit_anchor=commit_anchor,
            author_email=author_email,
            tag_anchor=tag_anchor,
            gitlab_remote=gitlab_remote,
            github_remote=github_remote,
        )
    except RuntimeError as error:
        raise SystemExit(f"ERROR: {error}") from error
    if as_json:
        print(json.dumps(evidence, sort_keys=True))
    else:
        print(f"commit objects: {'identical' if evidence['branch_object_parity'] else 'different'}")
        print(f"tag objects: {'identical' if evidence['tag_object_parity'] else 'different'}")
        print(f"housekeeping: {'OK' if evidence['ok'] else 'FAILED'}")
    if not evidence["ok"]:
        raise SystemExit(1)


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run Forge parity audit through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
