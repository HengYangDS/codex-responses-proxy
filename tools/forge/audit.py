#!/usr/bin/env python3
"""Read-only parity evidence for independently configured Forge planes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def command(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a captured subprocess and raise a concise error when requested."""

    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "command failed")
    return result


def output(*args: str, cwd: Path = ROOT) -> str:
    """Return stripped standard output for a successful command."""

    return command(*args, cwd=cwd).stdout.strip()


def remote_url(remote: str) -> str:
    """Return the repository-local URL configured for a Git remote."""

    return output("git", "config", "--local", "--get", f"remote.{remote}.url")


def remote_branches(remote: str) -> list[str]:
    """Return provider branches other than the canonical main branch."""

    refs = output("git", "ls-remote", "--heads", remote).splitlines()
    return sorted(
        ref.removeprefix("refs/heads/")
        for line in refs
        if len(parts := line.split("\t", 1)) == 2
        for ref in [parts[1]]
        if ref != "refs/heads/main"
    )


def local_non_main_branches() -> list[str]:
    """Return local branches other than the canonical main branch."""

    return sorted(
        branch
        for branch in output(
            "git", "for-each-ref", "refs/heads", "--format=%(refname:short)"
        ).splitlines()
        if branch != "main"
    )


def branch_provenance(
    ref: str, allowed_signers: Path, expected_email: str, *, cwd: Path = ROOT
) -> dict[str, object]:
    """Verify every reachable commit against one Forge identity and trust policy."""

    commits = output("git", "rev-list", ref, cwd=cwd).splitlines()
    untrusted: list[str] = []
    identity_mismatches: list[str] = []
    for commit in commits:
        identities = command(
            "git", "show", "-s", "--format=%ae%n%ce", commit, cwd=cwd
        ).stdout.splitlines()
        if identities != [expected_email, expected_email]:
            identity_mismatches.append(commit)
        if command(
            "git",
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.ssh.program=ssh-keygen",
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed_signers}",
            "verify-commit",
            commit,
            cwd=cwd,
            check=False,
        ).returncode:
            untrusted.append(commit)
    return {
        "commit_count": len(commits),
        "all_commits_trusted": not untrusted,
        "untrusted_commits": untrusted,
        "all_commits_use_provider_email": not identity_mismatches,
        "identity_mismatches": identity_mismatches,
    }


def provider_release_evidence(
    remote: str, provider: str, allowed_signers: Path
) -> dict[str, dict[str, object]]:
    """Inspect provider-native tags through an isolated temporary clone."""

    workspace = Path(tempfile.mkdtemp(prefix="codex-responses-proxy-parity-"))
    clone = workspace / "repository"
    try:
        command("git", "clone", "--quiet", "--no-local", "--no-tags", f"file://{ROOT}", str(clone))
        command("git", "-C", str(clone), "remote", "remove", "origin")
        command("git", "-C", str(clone), "remote", "add", "provider", remote_url(remote))
        command(
            "git",
            "-C",
            str(clone),
            "fetch",
            "--quiet",
            "--no-tags",
            "provider",
            "refs/heads/main:refs/remotes/provider/main",
        )
        remote_tags = command(
            "git", "-C", str(clone), "ls-remote", "--tags", "provider", "v[0-9]*"
        ).stdout.splitlines()
        evidence: dict[str, dict[str, object]] = {}
        for line in remote_tags:
            _, ref = line.split("\t", 1)
            if ref.endswith("^{}"):
                continue
            tag = ref.removeprefix("refs/tags/")
            command(
                "git",
                "-C",
                str(clone),
                "fetch",
                "--quiet",
                "--no-tags",
                "provider",
                f"refs/tags/{tag}:refs/tags/{tag}",
            )
            reachable = (
                command(
                    "git",
                    "-C",
                    str(clone),
                    "merge-base",
                    "--is-ancestor",
                    f"{tag}^{{}}",
                    "refs/remotes/provider/main",
                    check=False,
                ).returncode
                == 0
            )
            signature = (
                command(
                    "git",
                    "-C",
                    str(clone),
                    "-c",
                    "gpg.format=ssh",
                    "-c",
                    f"gpg.ssh.allowedSignersFile={allowed_signers.resolve()}",
                    "verify-tag",
                    tag,
                    check=False,
                ).returncode
                == 0
            )
            evidence[tag] = {
                "tree": output("git", "-C", str(clone), "rev-parse", f"{tag}^{{}}^{{tree}}"),
                "signature": signature,
                "reachable_from_main": reachable,
            }
        return evidence
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def live_main(
    remote: str, anchor: Path, expected_email: str
) -> tuple[str, str, list[str], dict[str, object]]:
    """Fetch and verify the provider's current main in an isolated clone."""

    with tempfile.TemporaryDirectory(prefix="codex-responses-proxy-main-") as directory:
        clone = Path(directory) / "repository"
        command("git", "clone", "--quiet", "--no-local", "--no-tags", f"file://{ROOT}", str(clone))
        command("git", "-C", str(clone), "remote", "remove", "origin")
        command("git", "-C", str(clone), "remote", "add", "provider", remote_url(remote))
        command(
            "git",
            "-C",
            str(clone),
            "fetch",
            "--quiet",
            "--no-tags",
            "provider",
            "refs/heads/main:refs/remotes/provider/main",
        )
        ref = "refs/remotes/provider/main"
        return (
            output("git", "rev-parse", ref, cwd=clone),
            output("git", "rev-parse", f"{ref}^{{tree}}", cwd=clone),
            output(
                "git", "log", "--reverse", "--topo-order", "--format=%T", ref, cwd=clone
            ).splitlines(),
            branch_provenance(ref, anchor.resolve(), expected_email, cwd=clone),
        )


def audit(
    *,
    gitlab_commit_anchor: Path,
    github_commit_anchor: Path,
    gitlab_author_email: str,
    github_author_email: str,
    gitlab_tag_anchor: Path,
    github_tag_anchor: Path,
    gitlab_remote: str,
    github_remote: str,
) -> dict[str, Any]:
    """Collect read-only cross-Forge parity and housekeeping evidence."""

    gitlab_main, gitlab_tree, gitlab_trees, gitlab_provenance = live_main(
        gitlab_remote, gitlab_commit_anchor, gitlab_author_email
    )
    github_main, github_tree, github_trees, github_provenance = live_main(
        github_remote, github_commit_anchor, github_author_email
    )
    gitlab_tags = provider_release_evidence(gitlab_remote, "gitlab", gitlab_tag_anchor)
    github_tags = provider_release_evidence(github_remote, "github", github_tag_anchor)
    overlapping = [
        {
            "tag": tag,
            "same_tree": gitlab_tags[tag]["tree"] == github_tags[tag]["tree"],
            "gitlab_signature": gitlab_tags[tag]["signature"],
            "github_signature": github_tags[tag]["signature"],
        }
        for tag in sorted(set(gitlab_tags) & set(github_tags))
    ]
    result: dict[str, Any] = {
        "gitlab_main": gitlab_main,
        "github_main": github_main,
        "main_commit_distinct": gitlab_main != github_main,
        "main_tree_equal": gitlab_tree == github_tree,
        "main_tree_history_equal": gitlab_trees == github_trees,
        "gitlab_provenance": gitlab_provenance,
        "github_provenance": github_provenance,
        "overlapping_tags": overlapping,
        "housekeeping": {
            "local_non_main_branches": local_non_main_branches(),
            "gitlab_non_main_branches": remote_branches(gitlab_remote),
            "github_non_main_branches": remote_branches(github_remote),
            "worktrees": output("git", "worktree", "list", "--porcelain").splitlines(),
        },
    }
    result["ok"] = (
        result["main_commit_distinct"]
        and result["main_tree_equal"]
        and result["main_tree_history_equal"]
        and gitlab_provenance["all_commits_trusted"] is True
        and github_provenance["all_commits_trusted"] is True
        and gitlab_provenance["all_commits_use_provider_email"] is True
        and github_provenance["all_commits_use_provider_email"] is True
        and not result["housekeeping"]["local_non_main_branches"]
        and not result["housekeeping"]["gitlab_non_main_branches"]
        and not result["housekeeping"]["github_non_main_branches"]
        and bool(overlapping)
        and all(
            item["same_tree"] and item["gitlab_signature"] and item["github_signature"]
            for item in overlapping
        )
    )
    return result


def main() -> None:
    """Parse explicit execution context and print live parity evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gitlab-commit-anchor", type=Path, required=True)
    parser.add_argument("--github-commit-anchor", type=Path, required=True)
    parser.add_argument("--gitlab-author-email", required=True)
    parser.add_argument("--github-author-email", required=True)
    parser.add_argument("--gitlab-tag-anchor", type=Path, required=True)
    parser.add_argument("--github-tag-anchor", type=Path, required=True)
    parser.add_argument("--gitlab-remote", default="origin")
    parser.add_argument("--github-remote", default="github")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    for path in (
        args.gitlab_commit_anchor,
        args.github_commit_anchor,
        args.gitlab_tag_anchor,
        args.github_tag_anchor,
    ):
        if not path.is_file():
            raise SystemExit(f"required publication input is unavailable: {path}")
    try:
        evidence = audit(
            gitlab_commit_anchor=args.gitlab_commit_anchor,
            github_commit_anchor=args.github_commit_anchor,
            gitlab_author_email=args.gitlab_author_email,
            github_author_email=args.github_author_email,
            gitlab_tag_anchor=args.gitlab_tag_anchor,
            github_tag_anchor=args.github_tag_anchor,
            gitlab_remote=args.gitlab_remote,
            github_remote=args.github_remote,
        )
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.json:
        print(json.dumps(evidence, sort_keys=True))
    else:
        print(f"main identity separation: {'OK' if evidence['main_commit_distinct'] else 'FAILED'}")
        print(f"main tree parity: {'OK' if evidence['main_tree_equal'] else 'FAILED'}")
        print(
            f"main tree-history parity: {'OK' if evidence['main_tree_history_equal'] else 'FAILED'}"
        )
        print(f"housekeeping: {'OK' if evidence['ok'] else 'FAILED'}")
    if not evidence["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
