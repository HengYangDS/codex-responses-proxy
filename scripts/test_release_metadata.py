#!/usr/bin/env python3
"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_release_metadata.py"
TAG_REFRESH = "git fetch --tags --force --prune --prune-tags origin"


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def expect_rejection(text: str, description: str, *args: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
        handle.write(text)
    try:
        completed = _run(
            sys.executable, str(CHECKER), *args, "--changelog", str(path)
        )
        if completed.returncode == 0:
            raise SystemExit(f"release metadata checker accepted {description}")
    finally:
        path.unlink(missing_ok=True)


def test_prune_tags_removes_deleted_remote_tag() -> None:
    """Reproduce the reused-runner stale-tag failure without network access."""

    with tempfile.TemporaryDirectory(prefix="codex-dmx-proxy-prune-tags-") as temp:
        temp_root = Path(temp)
        remote = temp_root / "remote.git"
        publisher = temp_root / "publisher"
        reused_runner = temp_root / "reused-runner"

        for args in (("git", "init", "--bare", str(remote)), ("git", "init", str(publisher))):
            completed = _run(*args, cwd=temp_root)
            if completed.returncode:
                raise SystemExit(completed.stderr)
        for args in (
            ("git", "config", "user.name", "Release Test"),
            ("git", "config", "user.email", "release@example.test"),
            ("git", "config", "user.useConfigOnly", "true"),
        ):
            completed = _run(*args, cwd=publisher)
            if completed.returncode:
                raise SystemExit(completed.stderr)
        (publisher / "README.md").write_text("release metadata fixture\n", encoding="utf-8")
        for args in (
            ("git", "add", "README.md"),
            ("git", "commit", "-m", "fixture"),
            ("git", "branch", "-M", "main"),
            ("git", "remote", "add", "origin", str(remote)),
            ("git", "push", "origin", "main"),
            ("git", "tag", "v9.9.9"),
            ("git", "push", "origin", "refs/tags/v9.9.9"),
        ):
            completed = _run(*args, cwd=publisher)
            if completed.returncode:
                raise SystemExit(completed.stderr)
        completed = _run("git", "clone", str(remote), str(reused_runner), cwd=temp_root)
        if completed.returncode:
            raise SystemExit(completed.stderr)
        completed = _run("git", "push", "origin", ":refs/tags/v9.9.9", cwd=publisher)
        if completed.returncode:
            raise SystemExit(completed.stderr)
        if _run("git", "rev-parse", "--verify", "refs/tags/v9.9.9", cwd=reused_runner).returncode:
            raise SystemExit("fixture did not retain the stale local tag")
        completed = _run(
            "git", "fetch", "--tags", "--force", "--prune", "--prune-tags", "origin",
            cwd=reused_runner,
        )
        if completed.returncode:
            raise SystemExit(completed.stderr)
        if _run("git", "rev-parse", "--verify", "refs/tags/v9.9.9", cwd=reused_runner).returncode == 0:
            raise SystemExit("tag-pruning fetch retained a tag deleted from origin")


def test_gitlab_ci_refreshes_tags_before_every_release_gate() -> None:
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if ci.count(TAG_REFRESH) != 3:
        raise SystemExit("every GitLab release gate must refresh and prune origin tags")
    for job in ("verify-release-metadata:", "verify-release-tag:", "publish-gitlab-release:"):
        start = ci.index(job)
        next_job = ci.find("\n\n", start)
        block = ci[start:next_job if next_job >= 0 else None]
        if TAG_REFRESH not in block:
            raise SystemExit(f"{job} does not refresh and prune origin tags")


def test_gitlab_release_metadata_gate_has_complete_history() -> None:
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    start = ci.index("verify-release-metadata:")
    end = ci.index("\n\nverify-release-tag:", start)
    block = ci[start:end]
    if 'GIT_DEPTH: "0"' not in block:
        raise SystemExit("verify-release-metadata must fetch complete Git history")


def main() -> None:
    test_prune_tags_removes_deleted_remote_tag()
    test_gitlab_ci_refreshes_tags_before_every_release_gate()
    test_gitlab_release_metadata_gate_has_complete_history()
    source = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    heading = f"## [{version}]"
    tag_exists = _run("git", "rev-parse", "--verify", f"refs/tags/v{version}").returncode == 0
    if heading in source and not tag_exists:
        expect_rejection(source, "an untagged pending release in ordinary verification")
        subprocess.run([sys.executable, str(CHECKER), "--prepare-release"], cwd=ROOT, check=True)
    else:
        subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, check=True)
        if tag_exists:
            expect_rejection(source, "a tagged release checked as a pending release", "--prepare-release")
        else:
            expect_rejection(source, "an absent pending release heading", "--prepare-release")
    expect_rejection(
        source.replace("## [1.0.8] - 2026-07-14", "## [1.0.8] - 2000-01-01", 1),
        "a tag/date mismatch",
    )
    expect_rejection(source.replace("## [1.0.4] - 2026-07-14\n", "", 1), "a missing reachable tag")
    expect_rejection(
        source.replace("## [1.0.8] - 2026-07-14", "## [1.0.9] - 2026-07-17\n\n## [1.0.8] - 2026-07-14", 1),
        "an untagged published release",
    )
    print("release metadata chronology contract: OK")


if __name__ == "__main__":
    main()
