#!/usr/bin/env python3
"""Read-only parity evidence for independent GitLab and GitHub release planes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GITLAB_EMAIL = "heng.yang.ds@hotmail.com"
GITHUB_EMAIL = "hengyang.2003@tsinghua.org.cn"


def command(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "command failed")
    return result


def output(*args: str, cwd: Path = ROOT) -> str:
    return command(*args, cwd=cwd).stdout.strip()


def remote_url(remote: str) -> str:
    return output("git", "config", "--local", "--get", f"remote.{remote}.url")


def remote_branches(remote: str) -> list[str]:
    refs = output("git", "ls-remote", "--heads", remote).splitlines()
    return sorted(
        ref.removeprefix("refs/heads/")
        for line in refs
        if (parts := line.split("\t", 1)) and len(parts) == 2
        for ref in [parts[1]]
        if ref != "refs/heads/main"
    )


def local_non_main_branches() -> list[str]:
    return sorted(
        branch
        for branch in output("git", "for-each-ref", "refs/heads", "--format=%(refname:short)").splitlines()
        if branch != "main"
    )


def branch_identities(ref: str) -> list[str]:
    return [entry for entry in output("git", "log", ref, "--format=%ae%n%ce").splitlines() if entry]


def provider_release_evidence(remote: str, provider: str) -> dict[str, dict[str, object]]:
    """Inspect provider-native reachable tags in an isolated temporary clone."""
    workspace = Path(tempfile.mkdtemp(prefix="codex-dmx-proxy-parity-"))
    clone = workspace / "repository"
    try:
        command("git", "clone", "--quiet", "--no-local", "--no-tags", f"file://{ROOT}", str(clone))
        command("git", "-C", str(clone), "remote", "remove", "origin")
        command("git", "-C", str(clone), "remote", "add", "provider", remote_url(remote))
        command(
            "git", "-C", str(clone), "fetch", "--quiet", "--no-tags", "provider",
            "refs/heads/main:refs/remotes/provider/main",
        )
        remote_tags = command(
            "git", "-C", str(clone), "ls-remote", "--tags", "provider", "v[0-9]*",
        ).stdout.splitlines()
        evidence: dict[str, dict[str, object]] = {}
        for line in remote_tags:
            _, ref = line.split("\t", 1)
            if ref.endswith("^{}"):
                continue
            tag = ref.removeprefix("refs/tags/")
            command(
                "git", "-C", str(clone), "fetch", "--quiet", "--no-tags", "provider",
                f"refs/tags/{tag}:refs/tags/{tag}",
            )
            if command(
                "git", "-C", str(clone), "merge-base", "--is-ancestor", f"{tag}^{{}}",
                "refs/remotes/provider/main", check=False,
            ).returncode:
                continue
            signature = command(
                str(ROOT / "scripts" / "check-release-tag-signature.sh"), str(clone), tag, provider,
                check=False,
            ).returncode == 0
            evidence[tag] = {
                "tree": output("git", "-C", str(clone), "rev-parse", f"{tag}^{{}}^{{tree}}"),
                "signature": signature,
            }
        return evidence
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def audit() -> dict:
    gitlab_main = output("git", "rev-parse", "origin/main")
    github_main = output("git", "rev-parse", "github/main")
    gitlab_tree = output("git", "rev-parse", f"{gitlab_main}^{{tree}}")
    github_tree = output("git", "rev-parse", f"{github_main}^{{tree}}")
    gitlab_tags = provider_release_evidence("origin", "gitlab")
    github_tags = provider_release_evidence("github", "github")
    overlapping = [
        {
            "tag": tag,
            "same_tree": gitlab_tags[tag]["tree"] == github_tags[tag]["tree"],
            "gitlab_signature": gitlab_tags[tag]["signature"],
            "github_signature": github_tags[tag]["signature"],
        }
        for tag in sorted(set(gitlab_tags) & set(github_tags))
    ]
    result = {
        "gitlab_main": gitlab_main,
        "github_main": github_main,
        "main_tree_equal": gitlab_tree == github_tree,
        "gitlab_identity_only": set(branch_identities("origin/main")) == {GITLAB_EMAIL},
        "github_identity_only": set(branch_identities("github/main")) == {GITHUB_EMAIL},
        "overlapping_tags": overlapping,
        "housekeeping": {
            "local_non_main_branches": local_non_main_branches(),
            "gitlab_non_main_branches": remote_branches("origin"),
            "github_non_main_branches": remote_branches("github"),
            "worktrees": output("git", "worktree", "list", "--porcelain").splitlines(),
        },
    }
    result["ok"] = (
        result["main_tree_equal"]
        and result["gitlab_identity_only"]
        and result["github_identity_only"]
        and not result["housekeeping"]["local_non_main_branches"]
        and not result["housekeeping"]["gitlab_non_main_branches"]
        and not result["housekeeping"]["github_non_main_branches"]
        and bool(overlapping)
        and all(item["same_tree"] and item["gitlab_signature"] and item["github_signature"] for item in overlapping)
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only dual-forge parity audit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        evidence = audit()
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.json:
        print(json.dumps(evidence, sort_keys=True))
    else:
        print(f"main tree parity: {'OK' if evidence['main_tree_equal'] else 'FAILED'}")
        print(f"GitLab identity domain: {'OK' if evidence['gitlab_identity_only'] else 'FAILED'}")
        print(f"GitHub identity domain: {'OK' if evidence['github_identity_only'] else 'FAILED'}")
        print(f"housekeeping: {'OK' if evidence['ok'] else 'FAILED'}")
    if not evidence["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
