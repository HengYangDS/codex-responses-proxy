"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools" / "release" / "metadata.py"
TAG_REFRESH = "git fetch --tags --force --prune --prune-tags origin"
APT_INSTALL = "apt-get install -qq -y --no-install-recommends"
GITLAB_LOCKED_PYTHON = "uv run --locked --no-sync --python python --no-python-downloads"


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
        require(
            completed.returncode != 0,
            f"release metadata checker accepted {description}",
        )
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


def test_product_release_history_is_provider_neutral(*, mocker) -> None:
    """Validate the one local release history without a Forge semantic input."""

    checker = load_checker()
    releases = [
        ("1.0.3", "2026-07-03"),
        ("1.0.2", "2026-07-02"),
        ("1.0.1", "2026-07-01"),
    ]
    known = mocker.patch.object(checker, "known_release_versions", return_value=["1.0.2", "1.0.1"])
    checker.check_changelog_provenance(releases, pending_version="1.0.3")
    known.return_value = ["1.0.2"]
    expect_value_error(
        lambda: checker.check_changelog_provenance(
            [("1.0.3", "2026-07-03"), ("1.0.1", "2026-07-01")]
        ),
        "must appear once",
        "a local tag without a shared heading",
    )


def test_prepare_release_rejects_only_future_dates() -> None:
    """Keep prepared metadata stable across days while rejecting impossible chronology."""

    checker = load_checker()
    current = date(2026, 7, 27)
    checker.check_pending_release_date("1.2.3", [("1.2.3", "2026-07-27")], today=current)
    checker.check_pending_release_date("1.2.3", [("1.2.3", "2026-07-26")], today=current)
    expect_value_error(
        lambda: checker.check_pending_release_date(
            "1.2.3", [("1.2.3", "2026-07-28")], today=current
        ),
        "future UTC date",
        "a pending release dated in the future",
    )


def test_exact_release_tag_contract(*, mocker) -> None:
    """Reject lightweight, misnamed, nested, and wrong-target release tags."""

    checker = load_checker()
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
    git = mocker.patch.object(checker, "_git")
    for git_observation, message, description in cases:
        git.side_effect = git_observation
        expect_value_error(
            lambda: checker.check_release_tag("v1.2.3", "1.2.3"),
            message,
            description,
        )
    git.side_effect = lambda *args: {
        ("cat-file", "-t", "refs/tags/v1.2.3"): "tag",
        (
            "cat-file",
            "tag",
            "refs/tags/v1.2.3",
        ): "object same-commit\ntype commit\ntag v1.2.3\n\nmessage",
        ("rev-parse", "HEAD^{commit}"): "same-commit",
    }[args]
    checker.check_release_tag("v1.2.3", "1.2.3")


def test_release_metadata_command_has_no_forge_semantics() -> None:
    """Keep ordinary product validation independent from publication peers."""

    completed = _run(sys.executable, str(CHECKER))
    require_success(completed)
    legacy = _run(sys.executable, str(CHECKER), "--provider", "gitlab")
    require(legacy.returncode != 0, "metadata retained a Forge-specific compatibility flag")


def test_local_tag_owner_signs_once_then_publishes_the_exact_object() -> None:
    """Require one local tag object with provider-parametric validation and push."""

    source = (ROOT / "tools" / "release" / "tag.py").read_text(encoding="utf-8")
    prepare = '_metadata(root, "--prepare-release")'
    exact = '_metadata(root, "--tag", tag)'
    signing = '"tag",\n                "-s",'
    push = '"push", "--quiet", remote'
    require_tokens(
        source,
        (prepare, exact, signing, push, '"ls-remote", "--tags", remote'),
        "local tag owner",
    )
    require(
        source.index(prepare) < source.index(signing) < source.index(exact) < source.index(push),
        "local tag validation order is unsafe",
    )
    require(
        "clone" not in source,
        "tag publication must not clone a peer or recreate a provider-native tag",
    )


def test_exact_local_object_forge_publication_contract() -> None:
    """Require one provider-parametric projector that never recreates Git objects."""

    source = (ROOT / "tools" / "forge" / "project.py").read_text(encoding="utf-8")
    require_tokens(
        source,
        (
            "provider: str",
            '("main", source), ("dev", source)',
            '"GIT_CONFIG_GLOBAL": os.devnull',
            "verify-commit",
            "runner_admission",
            '"push", "--atomic"',
            "--force-with-lease=refs/heads/",
        ),
        "exact local-object projector",
    )
    require(
        "canonical GitLab" not in source and "GitLab receives" not in source,
        "Forge projection still treats GitLab as source authority",
    )
    context_source = (ROOT / "tools" / "forge" / "context.py").read_text(encoding="utf-8")
    require(
        "publication context" in context_source,
        "provider identity context is not externally supplied",
    )
    require(
        all(token not in source for token in ("filter-branch", "commit-tree", '"-S"')),
        "forge projector can recreate Git objects",
    )
    context = (ROOT / "tools" / "forge" / "context.py").read_text(encoding="utf-8")
    require_tokens(
        context,
        (
            "active-signing-fingerprint",
            'shutil.which("ssh-add")',
            'shutil.which("ssh-keygen")',
            '(ssh_add, "-L")',
            '(ssh_add, "-T", str(destination))',
        ),
        "provider publication context",
    )
    require(
        all(
            token not in context
            for token in (
                "/Users/",
                "$HOME/.ssh",
                "security",
                "SSH_ASKPASS",
                "pty",
                "ssh-agent",
            )
        ),
        "provider publication must not hard-code a workstation or manage credentials",
    )
    tagger = (ROOT / "tools" / "release" / "tag.py").read_text(encoding="utf-8")
    require_tokens(tagger, ("context.load", "context.select_signing_key"), "provider tagger")
    require(
        all(
            token not in tagger
            for token in ("/Users/", "$HOME/.ssh", "id_" + "ed25519", "AUTHOR_EMAIL")
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

        for args in (
            ("git", "init", "--bare", str(remote)),
            ("git", "init", str(publisher)),
        ):
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


def test_gitlab_tag_gate_refreshes_provider_tags() -> None:
    """Bind the GitLab tag verifier to the provider's current tag namespace."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-release-tag:", "\n\nverify-python-quality:")
    require(TAG_REFRESH in block, "GitLab tag verifier does not prune stale tags")


def test_github_tag_metadata_fetches_complete_provider_tags() -> None:
    """Require the tag proof to observe the complete provider tag namespace."""

    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    start = workflow.index("\n  tag-metadata:")
    end = workflow.index("\n  python-quality:", start)
    checkout = workflow[start:end].split("- name: Fetch the exact", 1)[0]
    require_tokens(checkout, ("fetch-depth: 0", "fetch-tags: true"), "GitHub tag checkout")


def test_github_release_metadata_is_strict() -> None:
    """Publish only the exact successful Verify tag run and its signed bundle."""

    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    require_tokens(
        workflow,
        (
            "workflow_run:",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.conclusion == 'success'",
            "python -m tools.release.publish_github publish",
            "${{ github.event.workflow_run.head_branch }}",
            "${{ github.event.workflow_run.head_sha }}",
            '--assets "$RUNNER_TEMP/github-release/source"',
        ),
        "GitHub exact release projection",
    )
    require(
        "--allow-unpublished-history" not in workflow,
        "GitHub release bypasses chronology",
    )
    require("wait-verify" not in workflow, "GitHub release retains polling orchestration")


def test_gitlab_proof_contexts_are_partitioned() -> None:
    """Run full source proof on review, accepted confirmation on branches, and tag proof on tags."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    matrix = ci_block(ci, "verify-python-matrix:", "\n\nverify-accepted-source:")
    accepted = ci_block(ci, "verify-accepted-source:", "\n\nverify-release-tag:")
    tag = ci_block(ci, "verify-release-tag:", "\n\nverify-python-quality:")
    require(
        '$CI_PIPELINE_SOURCE == "merge_request_event"' in matrix,
        "matrix is not review-only",
    )
    require(
        '$CI_COMMIT_BRANCH == "dev" || $CI_COMMIT_BRANCH == "main"' in accepted,
        "accepted confirmation is not branch-scoped",
    )
    require("$CI_COMMIT_TAG" in tag, "tag verifier is not tag-scoped")
    require("--prepare-release" not in ci, "CI retains mixed release-state dispatch")


def test_gitlab_tag_gate_requires_exact_external_trust() -> None:
    """Keep GitLab tag verification strict without rebuilding product assets."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-release-tag:", "\n\nverify-python-quality:")
    require_tokens(
        block,
        (
            'GIT_DEPTH: "0"',
            f'{GITLAB_LOCKED_PYTHON} python tools/release/metadata.py --tag "$CI_COMMIT_TAG"',
            "CODEX_RESPONSES_PROXY_GITLAB_TAG_TRUST",
            "tools.forge.tag_signature",
        ),
        "GitLab external tag trust",
    )
    for forbidden in ("publish-gitlab-release:", "nox -s release", "--signing-key"):
        require(
            forbidden not in ci,
            f"GitLab retains duplicate bundle authority: {forbidden}",
        )


def test_gitlab_ci_selects_a_deployment_supplied_runner_tag() -> None:
    """Bind every GitLab job to one explicit adopter-owned runner label."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    require(
        "tags: [$CODEX_RESPONSES_PROXY_GITLAB_LINUX_RUNNER_TAG]" in ci,
        "GitLab CI must use the deployment-supplied runner tag",
    )
    require(
        "codex-responses-proxy-linux-x86_64" not in ci,
        "GitLab CI must not hardcode one installation's runner label",
    )


def test_gitlab_review_runs_full_regression_matrix() -> None:
    """Require the GitLab review context to invoke the canonical test owner."""

    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = ci_block(ci, "verify-python-matrix:", "\n\nverify-accepted-source:")
    require_tokens(
        block,
        (
            'GIT_DEPTH: "0"',
            "git fetch --unshallow --tags --force origin",
            "git fetch --tags --force origin",
            "uv python install --no-bin $(tr '\\n' ' ' < .python-versions)",
            f"{GITLAB_LOCKED_PYTHON} nox -s full",
            f"{APT_INSTALL} binutils git openssh-client",
        ),
        "GitLab review matrix",
    )
    require("PYTHON_VERSION" not in ci, "GitLab duplicated the Python matrix")


def test_native_bundle_has_one_runtime_and_one_signer() -> None:
    """Build every platform once and sign only the complete assembled bundle."""

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    image = metadata["tool"]["codex-responses-proxy"]["linux-release-image"]
    github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    require("@sha256:" in image, "Linux release runtime must be immutable")
    require_tokens(
        github,
        (
            "linux-release-image: ${{ steps.versions.outputs.linux-release-image }}",
            "container: ${{ needs.python-matrix.outputs.linux-release-image }}",
            "platform: macos-arm64",
            "platform: windows-x86_64",
            "python -m tools.release.assemble_assets",
            "--sign",
        ),
        "single native bundle builder",
    )
    require(
        github.count("python -m tools.release.assemble_assets") == 1,
        "bundle assembled twice",
    )
    require(github.count("--sign") == 1, "bundle signed more than once")
    require("nox -s release" not in gitlab, "GitLab independently rebuilds product assets")


def test_python_quality_gate_is_cross_forge() -> None:
    """Require both review projections to invoke the repository quality owner."""

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    require_tokens(gitlab, (f"{GITLAB_LOCKED_PYTHON} nox -s quality",), "GitLab quality")
    require_tokens(github, ("uv run --locked --group quality nox -s quality",), "GitHub quality")
    require(
        "tools/quality/run.sh" not in gitlab + github,
        "CI retains duplicate quality runner",
    )
    require_tokens(
        ci_block(gitlab, "verify-python-quality:"),
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
        subprocess.run(
            [sys.executable, str(CHECKER), "--prepare-release"],
            cwd=ROOT,
            check=True,
        )
    else:
        subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, check=True)
        if tag_exists:
            expect_rejection(
                source,
                "a tagged release checked as a pending release",
                "--prepare-release",
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
    # Forge publication state is audited separately; product chronology has one
    # provider-neutral result for the exact local checkout.
    subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, check=True)
