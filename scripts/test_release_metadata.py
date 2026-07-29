#!/usr/bin/env python3
"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_release_metadata.py"
TAG_REFRESH = "git fetch --tags --force --prune --prune-tags origin"
GITLAB_RUNNER_TAG = "tags: [codex-dmx-proxy-gitlab-ci]"


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def expect_rejection(text: str, description: str, *args: str) -> None:
    """Require the release metadata checker to reject a Changelog fixture."""

    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
        handle.write(text)
    try:
        completed = _run(sys.executable, str(CHECKER), *args, "--changelog", str(path))
        if completed.returncode == 0:
            raise SystemExit(f"release metadata checker accepted {description}")
    finally:
        path.unlink(missing_ok=True)


def test_prepare_release_requires_current_utc_date() -> None:
    """Reject a pending release whose heading date is not current in UTC."""

    spec = importlib.util.spec_from_file_location("check_release_metadata", CHECKER)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load release metadata checker")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    current = date(2026, 7, 27)
    checker.check_pending_release_date("1.2.3", [("1.2.3", "2026-07-27")], today=current)
    try:
        checker.check_pending_release_date("1.2.3", [("1.2.3", "2026-07-26")], today=current)
    except ValueError as exc:
        if "current UTC date" not in str(exc):
            raise SystemExit(
                f"stale pending-release date returned an unclear error: {exc}"
            ) from exc
    else:
        raise SystemExit("release metadata checker accepted a stale pending-release date")


def test_provider_tag_scripts_preflight_before_signing() -> None:
    """Require provider tag scripts to validate metadata before signing."""

    cases = (
        ("tag-gitlab-release.sh", "--prepare-release"),
        ("tag-github-release.sh", '--tag "$tag"'),
    )
    for script_name, expected_argument in cases:
        source = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        preflight = (
            f'"$release_python" "$root/scripts/check_release_metadata.py" {expected_argument}'
        )
        if preflight not in source:
            raise SystemExit(f"{script_name} does not run its release metadata preflight")
        if source.index(preflight) > source.index("tag -s -a"):
            raise SystemExit(f"{script_name} runs its release metadata preflight after signing")


def test_provider_projection_re_signs_every_commit() -> None:
    """Reject identity-only history rewriting that strips commit signatures."""

    github = (ROOT / "scripts" / "project-github-forge.sh").read_text(encoding="utf-8")
    gitlab = (ROOT / "scripts" / "project-gitlab-forge.sh").read_text(encoding="utf-8")
    rewriter = (ROOT / "scripts" / "rewrite-provider-history.py").read_text(encoding="utf-8")
    if "filter-branch" in github:
        raise SystemExit("GitHub projection must not use signature-stripping filter-branch")
    for source in (github, gitlab):
        if "rewrite-provider-history.py" not in source or "--force-with-lease" not in source:
            raise SystemExit("each provider projection must use the signed rewriter under a lease")
    for script_name in ("test-gitlab-provider-projection.sh", "test-github-provider-projection.sh"):
        fixture = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        if "verify-commit" not in fixture or "allowedSignersFile" not in fixture:
            raise SystemExit(f"{script_name} must verify every projected commit")
    for token in (
        "commit-tree",
        '"-S"',
        "verify-commit",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_EMAIL",
    ):
        if token not in rewriter:
            raise SystemExit(f"provider history rewriter is missing {token}")


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
            "git",
            "fetch",
            "--tags",
            "--force",
            "--prune",
            "--prune-tags",
            "origin",
            cwd=reused_runner,
        )
        if completed.returncode:
            raise SystemExit(completed.stderr)
        if (
            _run("git", "rev-parse", "--verify", "refs/tags/v9.9.9", cwd=reused_runner).returncode
            == 0
        ):
            raise SystemExit("tag-pruning fetch retained a tag deleted from origin")


def test_gitlab_ci_refreshes_tags_before_every_release_gate() -> None:
    """Require every GitLab release gate to prune stale runner tags."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if ci.count(TAG_REFRESH) != 3:
        raise SystemExit("every GitLab release gate must refresh and prune origin tags")
    for job in ("verify-release-metadata:", "verify-release-tag:", "publish-gitlab-release:"):
        start = ci.index(job)
        next_job = ci.find("\n\n", start)
        block = ci[start : next_job if next_job >= 0 else None]
        if TAG_REFRESH not in block:
            raise SystemExit(f"{job} does not refresh and prune origin tags")


def test_gitlab_release_metadata_gate_has_complete_history() -> None:
    """Require full Git history for release metadata provenance checks."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    start = ci.index("verify-release-metadata:")
    end = ci.index("\n\nverify-release-tag:", start)
    block = ci[start:end]
    if 'GIT_DEPTH: "0"' not in block:
        raise SystemExit("verify-release-metadata must fetch complete Git history")


def test_gitlab_ci_uses_only_the_project_runner_tag() -> None:
    """Require every GitLab job family to select the project runner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if ci.count(GITLAB_RUNNER_TAG) != 5:
        raise SystemExit(
            "every Codex DMX Proxy GitLab job family must select its project runner tag"
        )
    for job in (
        ".python-verify:",
        "verify-release-metadata:",
        "verify-release-tag:",
        "verify-python-quality:",
        "publish-gitlab-release:",
    ):
        start = ci.index(job)
        next_job = ci.find("\n\n", start)
        block = ci[start : next_job if next_job >= 0 else None]
        if GITLAB_RUNNER_TAG not in block:
            raise SystemExit(f"{job} must select the Codex DMX Proxy GitLab runner tag")


def test_gitlab_ci_runs_full_regression_matrix() -> None:
    """Require GitLab's Python matrix to use the canonical test owner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    start = ci.index(".python-verify:")
    end = ci.index("\n\nverify-python-3.12:", start)
    block = ci[start:end]
    owner = "python scripts/run-python-tests.py"
    if owner not in block:
        raise SystemExit(f".python-verify template must run {owner}")
    if "apt-get install -y --no-install-recommends git openssh-client" not in block:
        raise SystemExit(".python-verify must install Git and OpenSSH for signed-source tests")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    tests = metadata["tool"]["codex-dmx-proxy"]["quality"]["coverage-tests"]
    expected = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py"))
    if sorted(tests) != expected:
        raise SystemExit(
            "canonical Python test inventory must exactly match tests/test_*.py: "
            f"configured={sorted(tests)!r}, expected={expected!r}"
        )


def test_python_quality_gate_is_cross_forge() -> None:
    """Require both Forge projections to invoke the single repository owner."""

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    owner = "sh scripts/run-python-quality.sh"
    if owner not in gitlab or owner not in github:
        raise SystemExit(f"both Forge quality projections must invoke {owner}")
    quality_start = gitlab.index("verify-python-quality:")
    quality_end = gitlab.index("\n\npublish-gitlab-release:", quality_start)
    quality_block = gitlab[quality_start:quality_end]
    if "apt-get install -y --no-install-recommends git openssh-client" not in quality_block:
        raise SystemExit("GitLab Python quality must install Git and OpenSSH for coverage tests")
    script = (ROOT / "scripts" / "run-python-quality.sh").read_text(encoding="utf-8")
    if '"ty 0.0.56"|"ty 0.0.56 "*' not in script:
        raise SystemExit("Python quality must accept both supported ty 0.0.56 version forms")
    for token in (
        '"$ruff_path" check .',
        '"$ruff_path" format --check .',
        '"$python_path" scripts/check_quality.py',
        '"$ty_path" check',
        '"$python_path" -m coverage erase',
        '"$python_path" -m coverage report',
    ):
        if token not in script:
            raise SystemExit(f"Python quality owner is missing {token}")


def main() -> None:
    test_prepare_release_requires_current_utc_date()
    test_provider_tag_scripts_preflight_before_signing()
    test_provider_projection_re_signs_every_commit()
    test_prune_tags_removes_deleted_remote_tag()
    test_gitlab_ci_refreshes_tags_before_every_release_gate()
    test_gitlab_release_metadata_gate_has_complete_history()
    test_gitlab_ci_uses_only_the_project_runner_tag()
    test_gitlab_ci_runs_full_regression_matrix()
    test_python_quality_gate_is_cross_forge()
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
            expect_rejection(
                source, "a tagged release checked as a pending release", "--prepare-release"
            )
        else:
            expect_rejection(source, "an absent pending release heading", "--prepare-release")
    expect_rejection(
        source.replace("## [1.0.8] - 2026-07-14", "## [1.0.8] - 2000-01-01", 1),
        "a tag/date mismatch",
    )
    expect_rejection(source.replace("## [1.0.4] - 2026-07-14\n", "", 1), "a missing reachable tag")
    expect_rejection(
        source.replace(
            "## [1.0.8] - 2026-07-14", "## [1.0.9] - 2026-07-17\n\n## [1.0.8] - 2026-07-14", 1
        ),
        "an untagged published release",
    )
    print("release metadata chronology contract: OK")


if __name__ == "__main__":
    main()
