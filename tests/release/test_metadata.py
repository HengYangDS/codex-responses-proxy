"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools" / "release" / "metadata.py"
TAG_REFRESH = "git fetch --tags --force --prune --prune-tags origin"
APT_INSTALL = "apt-get install -qq -y --no-install-recommends"


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


def test_each_provider_validates_its_native_tags_against_shared_history() -> None:
    """Treat GitLab and GitHub as independent projections of one release history."""

    checker = load_checker()
    releases = [
        ("1.0.3", "2026-07-03"),
        ("1.0.2", "2026-07-02"),
        ("1.0.1", "2026-07-01"),
    ]
    original_known = getattr(checker, "known_release_versions")
    try:
        for provider in ("gitlab", "github"):
            setattr(checker, "known_release_versions", lambda: ["1.0.2", "1.0.1"])
            checker.check_changelog_provenance(releases, provider=provider, pending_version="1.0.3")
            setattr(checker, "known_release_versions", lambda: ["1.0.2"])
            expect_value_error(
                lambda provider=provider: checker.check_changelog_provenance(
                    [("1.0.3", "2026-07-03"), ("1.0.1", "2026-07-01")],
                    provider=provider,
                ),
                "must appear once",
                f"a {provider}-native tag without a shared heading",
            )
        expect_value_error(
            lambda: checker.check_changelog_provenance(releases, provider="gitbucket"),
            "unsupported release provider",
            "an invalid provider",
        )
    finally:
        setattr(checker, "known_release_versions", original_known)


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


def test_github_can_independently_prepare_the_release() -> None:
    """Keep release preparation provider-parametric without bypass flags."""

    completed = _run(
        sys.executable,
        str(CHECKER),
        "--provider",
        "github",
        "--prepare-release",
    )
    require(completed.returncode == 0, "GitHub could not independently prepare the same release")


def test_provider_tag_scripts_preflight_before_signing() -> None:
    """Require canonical preparation before GitLab signs its release tag."""

    source = (ROOT / "tools" / "release" / "tag-gitlab.sh").read_text(encoding="utf-8")
    preflight = (
        '"$release_python" "$root/tools/release/metadata.py" --provider gitlab --prepare-release'
    )
    require(preflight in source, "tag-gitlab.sh lacks canonical metadata preparation")
    require(
        source.index(preflight) < source.index("tag -s -a"),
        "tag-gitlab.sh prepares metadata after signing",
    )
    github = (ROOT / "tools" / "release" / "tag-github.sh").read_text(encoding="utf-8")
    exact = (
        '"$release_python" "$repository/tools/release/metadata.py" --provider github --tag "$tag"'
    )
    require(exact in github, "tag-github.sh lacks exact projected tag validation")
    require(
        github.index("tag -s -a") < github.index(exact) < github.index("push --quiet origin"),
        "tag-github.sh must validate the new native tag before pushing it",
    )


def test_forward_only_forge_publication_contract() -> None:
    """Require one provider-parametric, append-only identity projector."""

    source = (ROOT / "tools" / "forge" / "project.sh").read_text(encoding="utf-8")
    require_tokens(
        source,
        (
            "--provider",
            "refs/heads/main",
            "GIT_CONFIG_GLOBAL=/dev/null",
            "verify-commit",
            "COMMIT_ALLOWED_SIGNERS",
            "commit-tree -S",
            "runner_admission.py",
            "CODEX_RESPONSES_PROXY_GITLAB_PROJECT",
            "CODEX_RESPONSES_PROXY_GITHUB_REPOSITORY",
            "--map-output",
        ),
        "provider identity projector",
    )
    require(
        "canonical GitLab" not in source and "GitLab receives" not in source,
        "Forge projection still treats GitLab as source authority",
    )
    context_source = (ROOT / "tools" / "forge" / "context.sh").read_text(encoding="utf-8")
    require(
        "CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT" in context_source,
        "provider identity context is not externally supplied",
    )
    require(
        all(token not in source for token in ("filter-branch", "--force", "--force-with-lease")),
        "forge projector can rewrite or force-update history",
    )
    context = (ROOT / "tools" / "forge" / "context.sh").read_text(encoding="utf-8")
    require_tokens(
        context,
        (
            "CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT",
            "active-signing-fingerprint",
            "command -v ssh-add",
            "command -v ssh-keygen",
            '"$ssh_add" -L',
            '"$ssh_add" -T',
        ),
        "provider publication context",
    )
    require(
        all(
            token not in context
            for token in ("/Users/", "$HOME/.ssh", "security", "SSH_ASKPASS", "pty", "ssh-agent")
        ),
        "provider publication must not hard-code a workstation or manage credentials",
    )
    for script_name in ("tag-gitlab.sh", "tag-github.sh"):
        tagger = (ROOT / "tools" / "release" / script_name).read_text(encoding="utf-8")
        require_tokens(
            tagger,
            (
                "tools/forge/context.sh",
                "load_publication_context",
                "select_agent_signing_key",
            ),
            "provider tagger",
        )
        require(
            all(
                token not in tagger
                for token in (
                    "/Users/",
                    "$HOME/.ssh",
                    "id_" + "ed25519",
                    "AUTHOR_NAME",
                    "AUTHOR_EMAIL",
                )
            ),
            "provider tagger contains a personal or host-specific default",
        )


def test_prune_tags_removes_deleted_remote_tag() -> None:
    """Reproduce the reused-runner stale-tag failure without network access."""

    with tempfile.TemporaryDirectory(prefix="codex-responses-proxy-prune-tags-") as temp:
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
    release_jobs = (
        "verify-release-metadata:",
        "verify-release-tag:",
        "build-gitlab-native-asset:",
        "publish-gitlab-release:",
    )
    require(ci.count(TAG_REFRESH) == len(release_jobs), "GitLab tag refresh count drifted")
    for job in release_jobs:
        require(TAG_REFRESH in ci_block(ci, job), f"{job} does not refresh and prune origin tags")


def test_github_governance_fetches_complete_provider_tags() -> None:
    """Require GitHub governance to check the current provider tag namespace."""

    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    start = workflow.index("\n  governance:")
    end = workflow.index("\n  python-quality:", start)
    checkout = workflow[start:end].split("- name: Verify release", 1)[0]
    require_tokens(checkout, ("fetch-depth: 0", "fetch-tags: true"), "GitHub governance checkout")


def test_github_release_metadata_is_strict() -> None:
    """Require exact provider-tag validation in the GitHub release path."""

    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    require(
        'python tools/release/metadata.py --provider github --tag "$SELECTED_TAG"' in workflow,
        "GitHub release must validate its exact provider tag",
    )
    require(
        "--allow-unpublished-history" not in workflow,
        "GitHub release must not bypass provider chronology",
    )


def test_gitlab_release_metadata_gate_selects_validation_by_ref() -> None:
    """Require tag, published-main, and pending-main metadata validation."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-release-metadata:", "\n\nverify-release-tag:")
    require('GIT_DEPTH: "0"' in block, "verify-release-metadata must fetch complete Git history")
    require_tokens(
        block,
        (
            'if [ -n "${CI_COMMIT_TAG:-}" ]; then',
            'uv run --locked --no-sync python tools/release/metadata.py --provider gitlab --tag "$CI_COMMIT_TAG"',
            'elif git show-ref --verify --quiet "refs/tags/v$(cat VERSION)"; then',
            "uv run --locked --no-sync python tools/release/metadata.py --provider gitlab",
            "else",
            "uv run --locked --no-sync python tools/release/metadata.py --provider gitlab --prepare-release",
        ),
        "GitLab release metadata ref dispatch",
    )
    require(
        block.index('--tag "$CI_COMMIT_TAG"')
        < block.index('show-ref --verify --quiet "refs/tags/v$(cat VERSION)"')
        < block.index("--prepare-release"),
        "GitLab release metadata modes are not ordered by exact release state",
    )


def test_gitlab_tag_gates_require_exact_tag_validation() -> None:
    """Keep tag verification strict after admitting main release candidates."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    strict = (
        "uv run --locked --no-sync python tools/release/metadata.py "
        '--provider gitlab --tag "$CI_COMMIT_TAG"'
    )
    for job, next_job in (
        ("verify-release-tag:", "\n\nverify-python-quality:"),
        ("publish-gitlab-release:", None),
    ):
        block = ci_block(ci, job, next_job)
        require('GIT_DEPTH: "0"' in block, f"{job} must fetch complete Git history")
        require(strict in block, f"{job} must validate the exact provider tag")
        require("--prepare-release" not in block, f"{job} must not accept a pending release")
    tag_gate = ci_block(ci, "verify-release-tag:", "\n\nverify-python-quality:")
    require_tokens(
        tag_gate,
        (
            "CODEX_RESPONSES_PROXY_GITLAB_TAG_TRUST",
            "CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS",
        ),
        "GitLab external tag trust",
    )


def test_gitlab_ci_selects_a_deployment_supplied_runner_tag() -> None:
    """Bind every job to one explicit adopter-owned runner label."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    require(
        "tags: [$CODEX_RESPONSES_PROXY_GITLAB_LINUX_RUNNER_TAG]" in ci,
        "GitLab CI must use the deployment-supplied runner tag",
    )
    require(
        "codex-responses-proxy-linux-x86_64" not in ci,
        "GitLab CI must not hardcode one installation's runner label",
    )


def test_gitlab_ci_runs_full_regression_matrix() -> None:
    """Require GitLab's Python matrix to use the canonical test owner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-python-matrix:", "\n\nverify-release-metadata:")
    require_tokens(
        block,
        (
            'GIT_DEPTH: "0"',
            "git fetch --unshallow --tags --force origin",
            "git fetch --tags --force origin",
            "uv python install $(tr '\\n' ' ' < .python-versions)",
            "uv run --locked --no-sync nox -s full",
            f"{APT_INSTALL} binutils git openssh-client",
        ),
        "GitLab Python matrix job",
    )
    require("PYTHON_VERSION" not in ci, "GitLab duplicated the Python matrix")
    for patch_pin in ("3.12.", "3.13.", "3.14."):
        require(
            patch_pin not in ci,
            f"GitLab CI must select supported Python lines, not patch releases: {patch_pin}",
        )


def test_python_quality_gate_is_cross_forge() -> None:
    """Require both Forge projections to invoke the single repository owner."""

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    owner = "uv run --locked --no-sync nox -s quality"
    require_tokens(gitlab, (owner,), "GitLab quality projection")
    require_tokens(github, (owner,), "GitHub quality projection")
    require("tools/quality/run.sh" not in gitlab, "GitLab retains a duplicate quality runner")
    require("tools/quality/run.sh" not in github, "GitHub retains a duplicate quality runner")
    require_tokens(gitlab, ("DEBIAN_FRONTEND: noninteractive",), "GitLab pipeline")
    require_tokens(
        ci_block(gitlab, "verify-python-quality:", "\n\npublish-gitlab-release:"),
        (f"{APT_INSTALL} binutils git openssh-client",),
        "GitLab Python quality",
    )


def test_current_release_metadata_chronology() -> None:
    """Validate the current release train and representative chronology failures."""

    source = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    heading = f"## [{version}]"
    tag_exists = _run("git", "rev-parse", "--verify", f"refs/tags/v{version}").returncode == 0
    if heading in source and not tag_exists:
        for provider in ("gitlab", "github"):
            subprocess.run(
                [sys.executable, str(CHECKER), "--provider", provider, "--prepare-release"],
                cwd=ROOT,
                check=True,
            )
    else:
        args = ["--provider", "github"] if os.environ.get("GITHUB_ACTIONS") == "true" else []
        subprocess.run([sys.executable, str(CHECKER), *args], cwd=ROOT, check=True)
        if tag_exists:
            expect_rejection(
                source, "a tagged release checked as a pending release", "--prepare-release"
            )
        else:
            expect_rejection(source, "an absent pending release heading", "--prepare-release")
    tagged_version = (
        _run("git", "tag", "--list", "v[0-9]*", "--sort=-version:refname")
        .stdout.splitlines()[0]
        .removeprefix("v")
    )
    tagged_heading = re.compile(
        rf"(?m)^## \[{re.escape(tagged_version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$"
    )
    missing_tag_source = tagged_heading.sub("", source, count=1)
    expect_rejection(missing_tag_source, "a missing reachable tag")
    # A shared Changelog may contain a release published independently on the
    # other Forge. Each provider validates its own native tags; parity is a
    # separate post-publication audit, not a release prerequisite.
    subprocess.run(
        [sys.executable, str(CHECKER), "--provider", "github"],
        cwd=ROOT,
        check=True,
    )
