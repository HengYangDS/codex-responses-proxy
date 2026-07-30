#!/usr/bin/env python3
"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Callable


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


def require(condition: object, message: str) -> None:
    """Fail one metadata contract with its exact diagnostic."""

    if not condition:
        raise SystemExit(message)


def require_success(completed: subprocess.CompletedProcess[str]) -> None:
    """Require one repository command to succeed."""

    require(completed.returncode == 0, completed.stderr)


def ci_block(source: str, job: str, next_job: str | None = None) -> str:
    """Return one exact top-level CI job or template block."""

    start = source.index(job)
    end = source.index(next_job, start) if next_job else source.find("\n\n", start)
    return source[start : end if end >= 0 else None]


def require_tokens(source: str, tokens: tuple[str, ...], context: str) -> None:
    """Require every literal contract token in one source surface."""

    missing = [token for token in tokens if token not in source]
    require(not missing, f"{context} is missing {missing[0] if missing else ''}")


def expect_rejection(text: str, description: str, *args: str) -> None:
    """Require the release metadata checker to reject a Changelog fixture."""

    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
        handle.write(text)
    try:
        completed = _run(sys.executable, str(CHECKER), *args, "--changelog", str(path))
        require(completed.returncode != 0, f"release metadata checker accepted {description}")
    finally:
        path.unlink(missing_ok=True)


def load_checker() -> ModuleType:
    """Load the checker so pure policy units can replace Git observations."""

    spec = importlib.util.spec_from_file_location("check_release_metadata", CHECKER)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load release metadata checker")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def expect_value_error(action: Callable[[], object], message: str, description: str) -> None:
    """Require a zero-argument policy action to fail with a useful diagnostic."""

    try:
        action()
    except ValueError as exc:
        require(message in str(exc), f"{description} returned an unclear error: {exc}")
    else:
        raise SystemExit(f"release metadata checker accepted {description}")


def test_cross_provider_changelog_provenance() -> None:
    """Keep GitLab strict while validating GitHub's native tag subset."""

    checker = load_checker()
    releases = [
        ("1.0.3", "2026-07-03"),
        ("1.0.2", "2026-07-02"),
        ("1.0.1", "2026-07-01"),
    ]
    original_known = getattr(checker, "known_release_versions")
    original_git = getattr(checker, "_git")
    original_tag_date = getattr(checker, "tag_creation_date")
    try:
        setattr(checker, "known_release_versions", lambda: ["1.0.2"])
        checker.check_changelog_provenance(releases, provider="github")
        setattr(checker, "known_release_versions", lambda: ["1.0.2", "1.0.1"])
        setattr(checker, "_git", lambda *args: "false")
        setattr(
            checker,
            "tag_creation_date",
            lambda version: {"1.0.2": "2026-07-02", "1.0.1": "2026-07-01"}[version],
        )
        checker.check_changelog_provenance(releases, pending_version="1.0.3")
        setattr(checker, "known_release_versions", lambda: ["1.0.2"])
        expect_value_error(
            lambda: checker.check_changelog_provenance(
                [("1.0.3", "2026-07-03"), ("1.0.1", "2026-07-01")],
                provider="github",
            ),
            "must appear once",
            "a GitHub-native tag without a canonical heading",
        )
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases, provider="gitbucket"),
            "unsupported release provider",
            "an invalid provider",
        )
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases),
            "1.0.3",
            "a provider-external heading on canonical GitLab",
        )
        setattr(checker, "known_release_versions", lambda: ["1.0.3", "1.0.2", "1.0.1"])
        setattr(checker, "tag_creation_date", lambda version: "2000-01-01")
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases),
            "was created on",
            "GitLab canonical date drift",
        )
        setattr(checker, "_git", lambda *args: "true")
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases, pending_version="1.0.3"),
            "non-shallow",
            "canonical chronology from a shallow repository",
        )
        setattr(checker, "known_release_versions", lambda: ["1.0.2"])
        checker.check_active_release_train("1.0.3", releases, provider="github")
        checker.check_active_release_train(
            "1.0.4",
            [("1.0.3", "2026-07-03"), ("1.0.2", "2026-07-02")],
            provider="github",
        )
        expect_value_error(
            lambda: checker.check_active_release_train("1.0.1", releases, provider="github"),
            "exists before its Git tag",
            "a stale GitHub VERSION",
        )
        setattr(checker, "known_release_versions", lambda: [])
        checker.check_changelog_provenance(releases, provider="github")
        checker.check_active_release_train("1.0.3", releases, provider="github")
        expect_value_error(
            lambda: checker.check_active_release_train("1.0.2", releases, provider="github"),
            "exists before its Git tag",
            "a stale VERSION in a zero-tag GitHub projection",
        )
        setattr(checker, "_git", lambda *args: "false")
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases),
            "cannot find a gitlab release SemVer tag",
            "a zero-tag canonical GitLab projection",
        )
    finally:
        setattr(checker, "known_release_versions", original_known)
        setattr(checker, "_git", original_git)
        setattr(checker, "tag_creation_date", original_tag_date)


def test_tag_creation_date_uses_utc() -> None:
    """Normalize a local-midnight tagger timestamp to its UTC release date."""

    checker = load_checker()
    original_git = getattr(checker, "_git")
    try:
        setattr(checker, "_git", lambda *args: "1785342943")
        require(
            checker.tag_creation_date("1.0.29") == "2026-07-29",
            "tag creation date followed the tagger offset instead of UTC",
        )
    finally:
        setattr(checker, "_git", original_git)


def test_prepare_release_requires_current_utc_date() -> None:
    """Reject a pending release whose heading date is not current in UTC."""

    checker = load_checker()
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


def test_exact_release_tag_contract() -> None:
    """Reject lightweight, misnamed, nested, and wrong-target release tags."""

    checker = load_checker()
    original_git = getattr(checker, "_git")
    cases = (
        (
            lambda *args: "commit" if args[:2] == ("cat-file", "-t") else "v1.2.3",
            "annotated tag object",
            "a lightweight release tag",
        ),
        (
            lambda *args: {
                ("cat-file", "-t", "refs/tags/v1.2.3"): "tag",
                ("cat-file", "tag", "refs/tags/v1.2.3"): (
                    "object same-commit\ntype commit\ntag v9.9.9\n\nmessage"
                ),
            }[args],
            "embeds tag name",
            "an annotated tag with the wrong embedded name",
        ),
        (
            lambda *args: {
                ("cat-file", "-t", "refs/tags/v1.2.3"): "tag",
                ("cat-file", "tag", "refs/tags/v1.2.3"): (
                    "object inner-tag\ntype tag\ntag v1.2.3\n\nmessage"
                ),
            }[args],
            "directly name a commit",
            "a nested annotated release tag",
        ),
        (
            lambda *args: {
                ("cat-file", "-t", "refs/tags/v1.2.3"): "tag",
                ("cat-file", "tag", "refs/tags/v1.2.3"): (
                    "object tagged-commit\ntype commit\ntag v1.2.3\n\nmessage"
                ),
                ("rev-parse", "HEAD^{commit}"): "head-commit",
            }[args],
            "not HEAD commit",
            "an annotated tag that directly names the wrong commit",
        ),
    )
    try:
        for git_observation, message, description in cases:
            setattr(checker, "_git", git_observation)
            expect_value_error(
                lambda: checker.check_release_tag("v1.2.3", "1.2.3"),
                message,
                description,
            )
        setattr(
            checker,
            "_git",
            lambda *args: {
                ("cat-file", "-t", "refs/tags/v1.2.3"): "tag",
                ("cat-file", "tag", "refs/tags/v1.2.3"): (
                    "object same-commit\ntype commit\ntag v1.2.3\n\nmessage"
                ),
                ("rev-parse", "HEAD^{commit}"): "same-commit",
            }[args],
        )
        checker.check_release_tag("v1.2.3", "1.2.3")
    finally:
        setattr(checker, "_git", original_git)


def test_retired_cli_is_rejected() -> None:
    """Keep the deleted unpublished-history bypass outside the parser grammar."""

    completed = _run(sys.executable, str(CHECKER), "--allow-unpublished-history")
    require(completed.returncode != 0, "retired unpublished-history parser flag was accepted")
    require(
        "unrecognized arguments" in completed.stderr,
        "retired unpublished-history parser flag returned an unclear error",
    )
    completed = _run(
        sys.executable,
        str(CHECKER),
        "--provider",
        "github",
        "--prepare-release",
    )
    require(completed.returncode != 0, "GitHub accepted canonical release preparation")
    require("reserved for" in completed.stderr, "GitHub preparation returned an unclear error")


def test_provider_tag_scripts_preflight_before_signing() -> None:
    """Require canonical preparation before GitLab signs its release tag."""

    source = (ROOT / "scripts" / "tag-gitlab-release.sh").read_text(encoding="utf-8")
    preflight = (
        '"$release_python" "$root/scripts/check_release_metadata.py" '
        "--provider gitlab --prepare-release"
    )
    require(preflight in source, "tag-gitlab-release.sh lacks canonical metadata preparation")
    require(
        source.index(preflight) < source.index("tag -s -a"),
        "tag-gitlab-release.sh prepares metadata after signing",
    )
    github = (ROOT / "scripts" / "tag-github-release.sh").read_text(encoding="utf-8")
    exact = (
        '"$release_python" "$projection/scripts/check_release_metadata.py" '
        '--provider github --tag "$tag"'
    )
    require(exact in github, "tag-github-release.sh lacks exact projected tag validation")
    require(
        github.index("tag -s -a") < github.index(exact) < github.index("push origin"),
        "tag-github-release.sh must validate the new native tag before pushing it",
    )


def test_provider_projection_re_signs_every_commit() -> None:
    """Reject identity-only history rewriting that strips commit signatures."""

    github = (ROOT / "scripts" / "project-github-forge.sh").read_text(encoding="utf-8")
    gitlab = (ROOT / "scripts" / "project-gitlab-forge.sh").read_text(encoding="utf-8")
    rewriter = (ROOT / "scripts" / "rewrite-provider-history.py").read_text(encoding="utf-8")
    require(
        "filter-branch" not in github,
        "GitHub projection must not use signature-stripping filter-branch",
    )
    for source in (github, gitlab):
        require_tokens(
            source,
            ("rewrite-provider-history.py", "--force-with-lease"),
            "each provider projection",
        )
    for script_name in ("test-gitlab-provider-projection.sh", "test-github-provider-projection.sh"):
        fixture = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        require_tokens(fixture, ("verify-commit", "allowedSignersFile"), script_name)
    require_tokens(
        rewriter,
        ("commit-tree", '"-S"', "verify-commit", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"),
        "provider history rewriter",
    )


def test_prune_tags_removes_deleted_remote_tag() -> None:
    """Reproduce the reused-runner stale-tag failure without network access."""

    with tempfile.TemporaryDirectory(prefix="codex-dmx-proxy-prune-tags-") as temp:
        temp_root = Path(temp)
        remote = temp_root / "remote.git"
        publisher = temp_root / "publisher"
        reused_runner = temp_root / "reused-runner"

        for args in (("git", "init", "--bare", str(remote)), ("git", "init", str(publisher))):
            require_success(_run(*args, cwd=temp_root))
        for args in (
            ("git", "config", "user.name", "Release Test"),
            ("git", "config", "user.email", "release@example.test"),
            ("git", "config", "user.useConfigOnly", "true"),
        ):
            require_success(_run(*args, cwd=publisher))
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
            require_success(_run(*args, cwd=publisher))
        require_success(_run("git", "clone", str(remote), str(reused_runner), cwd=temp_root))
        require_success(_run("git", "push", "origin", ":refs/tags/v9.9.9", cwd=publisher))
        require(
            _run("git", "rev-parse", "--verify", "refs/tags/v9.9.9", cwd=reused_runner).returncode
            == 0,
            "fixture did not retain the stale local tag",
        )
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
        require_success(completed)
        require(
            _run("git", "rev-parse", "--verify", "refs/tags/v9.9.9", cwd=reused_runner).returncode
            != 0,
            "tag-pruning fetch retained a tag deleted from origin",
        )


def test_gitlab_ci_refreshes_tags_before_every_release_gate() -> None:
    """Require every GitLab release gate to prune stale runner tags."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    require(
        ci.count(TAG_REFRESH) == 3,
        "every GitLab release gate must refresh and prune origin tags",
    )
    for job in ("verify-release-metadata:", "verify-release-tag:", "publish-gitlab-release:"):
        require(TAG_REFRESH in ci_block(ci, job), f"{job} does not refresh and prune origin tags")


def test_github_governance_fetches_complete_provider_tags() -> None:
    """Require GitHub governance to check the current provider tag namespace."""

    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    start = workflow.index("\n  governance:")
    end = workflow.index("\n  python-quality:", start)
    checkout = workflow[start:end].split("- name: Verify release", 1)[0]
    require_tokens(checkout, ("fetch-depth: 0", "fetch-tags: true"), "GitHub governance checkout")


def test_github_release_metadata_is_strict() -> None:
    """Forbid the retired broad bypass in exact GitHub tag validation."""

    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    require(
        '"$python" scripts/check_release_metadata.py --provider github --tag "$SELECTED_TAG"'
        in workflow,
        "GitHub release must validate its exact provider tag",
    )
    require(
        "--allow-unpublished-history" not in workflow,
        "GitHub release must not bypass provider chronology",
    )


def test_gitlab_release_metadata_gate_selects_validation_by_ref() -> None:
    """Require complete history and branch/tag-specific metadata validation."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-release-metadata:", "\n\nverify-release-tag:")
    require('GIT_DEPTH: "0"' in block, "verify-release-metadata must fetch complete Git history")
    require_tokens(
        block,
        (
            'if [ -n "${CI_COMMIT_TAG:-}" ]; then',
            'python scripts/check_release_metadata.py --provider gitlab --tag "$CI_COMMIT_TAG"',
            "else",
            "python scripts/check_release_metadata.py --provider gitlab --prepare-release",
        ),
        "GitLab release metadata ref dispatch",
    )
    require(
        block.index('--tag "$CI_COMMIT_TAG"') < block.index("--prepare-release"),
        "GitLab release metadata must select tag validation before the branch fallback",
    )


def test_gitlab_tag_gates_require_exact_tag_validation() -> None:
    """Keep tag verification strict after admitting main release candidates."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    strict = 'python scripts/check_release_metadata.py --provider gitlab --tag "$CI_COMMIT_TAG"'
    for job, next_job in (
        ("verify-release-tag:", "\n\nverify-python-quality:"),
        ("publish-gitlab-release:", None),
    ):
        block = ci_block(ci, job, next_job)
        require('GIT_DEPTH: "0"' in block, f"{job} must fetch complete Git history")
        require(strict in block, f"{job} must validate the exact provider tag")
        require("--prepare-release" not in block, f"{job} must not accept a pending release")


def test_gitlab_ci_uses_only_the_project_runner_tag() -> None:
    """Require every GitLab job family to select the project runner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    require(
        ci.count(GITLAB_RUNNER_TAG) == 5,
        "every Codex DMX Proxy GitLab job family must select its project runner tag",
    )
    for job in (
        ".python-verify:",
        "verify-release-metadata:",
        "verify-release-tag:",
        "verify-python-quality:",
        "publish-gitlab-release:",
    ):
        require(
            GITLAB_RUNNER_TAG in ci_block(ci, job),
            f"{job} must select the Codex DMX Proxy GitLab runner tag",
        )


def test_gitlab_ci_runs_full_regression_matrix() -> None:
    """Require GitLab's Python matrix to use the canonical test owner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, ".python-verify:", "\n\nverify-python-3.12:")
    require_tokens(
        block,
        (
            "python scripts/run-python-tests.py",
            "apt-get install -y --no-install-recommends git openssh-client",
        ),
        ".python-verify template",
    )


def test_python_quality_gate_is_cross_forge() -> None:
    """Require both Forge projections to invoke the single repository owner."""

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    owner = "sh scripts/run-python-quality.sh"
    require_tokens(gitlab, (owner,), "GitLab quality projection")
    require_tokens(github, (owner,), "GitHub quality projection")
    require_tokens(
        ci_block(gitlab, "verify-python-quality:", "\n\npublish-gitlab-release:"),
        ("apt-get install -y --no-install-recommends git openssh-client",),
        "GitLab Python quality",
    )
    script = (ROOT / "scripts" / "run-python-quality.sh").read_text(encoding="utf-8")
    require_tokens(
        script,
        (
            '"ty 0.0.64"|"ty 0.0.64 "*',
            "Coverage.py, version 7.13.5 with C extension",
            'COVERAGE_FILE="$coverage_dir/.coverage"',
            '"$ruff_path" check --no-cache .',
            '"$ruff_path" format --no-cache --check .',
            '"$python_path" scripts/check_quality.py',
            '"$ty_path" check',
            '"$python_path" -m coverage erase',
            '"$python_path" scripts/run-python-tests.py --coverage',
            '"$python_path" -m coverage report',
            '"$python_path" scripts/check_branch_coverage.py',
        ),
        "Python quality owner",
    )


def main() -> None:
    test_cross_provider_changelog_provenance()
    test_tag_creation_date_uses_utc()
    test_prepare_release_requires_current_utc_date()
    test_exact_release_tag_contract()
    test_retired_cli_is_rejected()
    test_provider_tag_scripts_preflight_before_signing()
    test_provider_projection_re_signs_every_commit()
    test_prune_tags_removes_deleted_remote_tag()
    test_gitlab_ci_refreshes_tags_before_every_release_gate()
    test_github_governance_fetches_complete_provider_tags()
    test_github_release_metadata_is_strict()
    test_gitlab_release_metadata_gate_selects_validation_by_ref()
    test_gitlab_tag_gates_require_exact_tag_validation()
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
    subprocess.run(
        [sys.executable, str(CHECKER), "--provider", "github"],
        cwd=ROOT,
        check=True,
    )
    print("release metadata chronology contract: OK")


if __name__ == "__main__":
    main()
