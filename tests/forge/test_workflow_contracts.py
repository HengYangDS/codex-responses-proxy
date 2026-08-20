"""Portable contracts for GitHub verification and release workflows."""

import importlib
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GITLAB_LOCKED_PYTHON = "uv run --locked --no-sync --python python --no-python-downloads"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load one workflow while preserving GitHub's literal ``on`` key."""

    class WorkflowLoader(yaml.SafeLoader):
        pass

    for key, resolvers in tuple(WorkflowLoader.yaml_implicit_resolvers.items()):
        WorkflowLoader.yaml_implicit_resolvers[key] = [
            resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
        ]
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=WorkflowLoader)
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _mapping(value: object) -> Mapping[str, Any]:
    """Narrow one parsed workflow mapping for typed contract assertions."""

    assert isinstance(value, Mapping)
    return cast(Mapping[str, Any], value)


def test_forge_workflows_partition_review_accepted_and_release_proof() -> None:
    """Execute each expensive proof once in the lifecycle context that owns it."""

    github = _load_yaml(ROOT / ".github/workflows/verify.yml")
    github_triggers = github["on"]
    assert github_triggers == {
        "pull_request": {"branches": ["dev"]},
        "push": {"branches": ["dev", "main"], "tags": ["v*"]},
    }
    github_jobs = _mapping(github["jobs"])
    assert github_jobs["python-matrix"]["if"] == (
        "github.event_name == 'pull_request' || github.ref_type == 'tag'"
    )
    for job_id in ("python", "python-windows", "python-quality"):
        assert _mapping(github_jobs[job_id])["if"] == "github.event_name == 'pull_request'"
    assert _mapping(github_jobs["accepted-source"])["if"] == (
        "github.event_name == 'push' && github.ref_type == 'branch'"
    )
    assert _mapping(github_jobs["tag-metadata"])["if"] == "github.ref_type == 'tag'"
    for job_id in ("native-assets", "native-linux", "release-assets"):
        assert _mapping(github_jobs[job_id])["if"] == "github.ref_type == 'tag'"

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert '$CI_PIPELINE_SOURCE == "merge_request_event"' in gitlab
    assert '$CI_COMMIT_BRANCH == "dev" || $CI_COMMIT_BRANCH == "main"' in gitlab
    assert "$CI_COMMIT_TAG" in gitlab
    assert "$CI_OPEN_MERGE_REQUESTS" in gitlab
    assert "when: never" in gitlab
    for job in ("verify-python-matrix", "verify-python-quality"):
        block = gitlab.split(f"\n{job}:", 1)[1].split("\n\n", 1)[0]
        assert '$CI_PIPELINE_SOURCE == "merge_request_event"' in block
    accepted = gitlab.split("\nverify-accepted-source:", 1)[1].split("\n\n", 1)[0]
    assert '$CI_COMMIT_BRANCH == "dev" || $CI_COMMIT_BRANCH == "main"' in accepted
    tag_block = gitlab.split("\nverify-release-tag:", 1)[1].split("\n\n", 1)[0]
    assert "$CI_COMMIT_TAG" in tag_block
    assert "build-gitlab-native-asset:" not in gitlab
    assert "publish-gitlab-release:" not in gitlab


def test_python_matrix_output_comes_from_the_repository_ssot(tmp_path: Path) -> None:
    module = importlib.import_module("tools.quality.python_matrix")
    versions = tmp_path / ".python-versions"
    metadata = tmp_path / "pyproject.toml"
    output = tmp_path / "github-output"
    versions.write_text("3.12\n3.13\n3.14\n", encoding="ascii")
    release = tmp_path / ".python-release"
    release.write_text("3.14.7\n", encoding="ascii")
    metadata.write_text(
        '[tool.codex-responses-proxy]\nlinux-release-image = "python:3.14.7-bookworm@sha256:'
        + "a" * 64
        + '"\n',
        encoding="ascii",
    )

    module.write(versions=versions, release=release, metadata=metadata, output=output)

    assert output.read_text(encoding="utf-8") == (
        'value=["3.12", "3.13", "3.14"]\nfloor=3.12\nlatest=3.14\nrelease=3.14.7\n'
        f"linux-release-image=python:3.14.7-bookworm@sha256:{'a' * 64}\n"
    )


@pytest.mark.parametrize(
    ("release_value", "image_version", "message"),
    [
        ("3.14", "3.14.7", "native release Python is unavailable or invalid"),
        (
            "not.a.version",
            "not.a.version",
            "native release Python is unavailable or invalid",
        ),
        ("3.14.7", "3.14.6", "Linux release runtime is unavailable or mutable"),
    ],
)
def test_python_matrix_rejects_invalid_or_mismatched_release_runtime(
    tmp_path: Path, release_value: str, image_version: str, message: str
) -> None:
    module = importlib.import_module("tools.quality.python_matrix")
    versions = tmp_path / ".python-versions"
    release = tmp_path / ".python-release"
    metadata = tmp_path / "pyproject.toml"
    versions.write_text("3.12\n3.13\n3.14\n", encoding="ascii")
    release.write_text(f"{release_value}\n", encoding="ascii")
    metadata.write_text(
        '[tool.codex-responses-proxy]\nlinux-release-image = "python:'
        f"{image_version}-bookworm@sha256:{'a' * 64}"
        '"\n',
        encoding="ascii",
    )

    with pytest.raises(ValueError, match=message):
        module.write(
            versions=versions,
            release=release,
            metadata=metadata,
            output=tmp_path / "github-output",
        )


def test_native_release_runtime_is_exact_and_platform_independent() -> None:
    native_runtime = (ROOT / ".python-release").read_text(encoding="ascii").strip()
    image = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "codex-responses-proxy"
    ]["linux-release-image"]
    image_version = re.search(r"python:(\d+\.\d+\.\d+)-", image)
    nox_source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    native_job = workflow.split("\n  native-assets:", 1)[1].split("\n  native-linux:", 1)[0]

    assert re.fullmatch(r"\d+\.\d+\.\d+", native_runtime)
    assert image_version is not None
    assert native_runtime == image_version.group(1)
    assert 'if platform.system() != "Linux":' not in nox_source
    assert "@nox.session(python=RELEASE_PYTHON)" in nox_source
    assert "python-version: ${{ needs.python-matrix.outputs.release }}" in native_job


def test_single_bundle_is_built_once_and_forges_only_project_it() -> None:
    """Keep native construction and product signing in one authoritative workflow."""

    verify = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

    assert verify.count("uv run --locked --no-sync python -m tools.release.assemble_assets") == 1
    assert verify.count("--sign") == 1
    assert "container: ${{ needs.python-matrix.outputs.linux-release-image }}" in verify
    assert "python -m tools.release.publish_github publish" in release
    assert '--assets "$RUNNER_TEMP/github-release/source"' in release
    assert "workflow_run:" in release
    for forbidden in (
        "tools.release.publish_gitlab",
        "nox -s release",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY",
    ):
        assert forbidden not in gitlab


def test_gitlab_verification_bootstrap_is_bounded_and_cached() -> None:
    """Start verification from immutable UV/Python executors, not pip bootstrap."""

    gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    default = gitlab.split("\ndefault:", 1)[1].split("\nverify-python-matrix:", 1)[0]
    quality = gitlab.split("\nverify-python-quality:", 1)[1]

    assert "name: $UV_PYTHON_LATEST_IMAGE" in default
    assert "docker: { platform: linux/amd64 }" in default
    assert "UV_CACHE_DIR: $CI_PROJECT_DIR/.cache/uv" in gitlab
    assert "UV_PYTHON_INSTALL_DIR: $CI_PROJECT_DIR/.cache/uv/python" in gitlab
    assert "CODEX_RESPONSES_PROXY_CI_TARGET: linux-amd64" in gitlab
    assert "key: uv-$CODEX_RESPONSES_PROXY_CI_TARGET" in default
    assert "paths: [.cache/uv/]" in default
    assert "name: $UV_PYTHON_FLOOR_IMAGE" in quality
    assert "docker: { platform: linux/amd64 }" in quality
    assert gitlab.count("&assert-uv-version") == 1
    assert gitlab.count("*assert-uv-version") == 4
    assert "python -m pip install" not in gitlab
    assert "uv sync --locked --group quality --no-install-project" in gitlab
    assert "uv python install --no-bin $(tr '\\n' ' ' < .python-versions)" in gitlab


def _assert_github_required_tokens(text: str) -> None:
    required = [
        "name: Verify",
        "pull_request:",
        "push:",
        "branches: [dev]",
        "branches: [dev, main]",
        'tags: ["v*"]',
        "permissions:\n  contents: read",
        'GIT_CONFIG_COUNT: "1"',
        "GIT_CONFIG_KEY_0: init.defaultBranch",
        "GIT_CONFIG_VALUE_0: main",
        "runs-on: macos-26",
        "runs-on: ubuntu-24.04",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "uv run --locked --no-sync python -m tools.quality.python_matrix",
        "python-version: ${{ fromJSON(needs.python-matrix.outputs.versions) }}",
        'uv run --locked --group quality nox -s "tests-${{ matrix.python-version }}"',
        "python-windows:",
        "windows-2025",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "# v7.0.0",
        "fetch-tags: true",
        "if: github.ref_type == 'tag'",
        "python -m tools.release.publish_github prepare-checkout",
        'uv run --locked --no-sync python tools/release/metadata.py --tag "$GITHUB_REF_NAME"',
        "uv run --locked --no-sync python tools/release/metadata.py",
        "python-quality:",
        "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
        "uv run --locked --group quality nox -s quality",
        "python -m pytest -q tests/quality/test_contract.py tests/forge/test_workflow_contracts.py tests/forge/test_tagging.py",
        "tests/release/test_publish_gitlab.py",
        "native-assets:",
        "name: Native asset (${{ matrix.platform }})",
        "platform: macos-arm64",
        "platform: windows-x86_64",
        "native-linux:",
        "name: Native asset (linux-x86_64)",
        "container: ${{ needs.python-matrix.outputs.linux-release-image }}",
        'uv run --locked --no-sync nox -s release -- "${{ runner.temp }}/native-assets"',
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "# v7.0.1",
        "release-assets:",
        "name: Release assets",
        "needs: [python-matrix, native-assets, native-linux]",
        "python-version: ${{ needs.python-matrix.outputs.latest }}",
        "name: Download native release assets",
        "GH_TOKEN: ${{ github.token }}",
        """gh run download "$GITHUB_RUN_ID" --pattern 'native-*' """
        """--dir "$RUNNER_TEMP/native" """.rstrip(),
        "uv run --locked --no-sync python -m tools.release.assemble_assets",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
        'install -m 600 /dev/null "$RUNNER_TEMP/release-asset-signing-key"',
        'printf \'%s\\n\' "$RELEASE_ASSET_SIGNING_KEY_TEXT" > "$RUNNER_TEMP/release-asset-signing-key"',
        "RELEASE_ASSET_SIGNING_KEY_PATH: ${{ runner.temp }}/release-asset-signing-key",
        "--sign",
        "name: release-assets",
    ]
    for token in required:
        if token not in text:
            raise AssertionError(f"GitHub Actions verification contract is missing {token!r}")
    if "contents: write" in text:
        raise AssertionError("verification workflow must use read-only repository permissions")


def _assert_github_matrix_contract(text: str, release_text: str) -> None:
    matrix_start = text.index("\n  python-matrix:")
    matrix_end = text.index("\n  python:", matrix_start)
    matrix_block = text[matrix_start:matrix_end]
    for token in (
        "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
        "uv sync --locked --all-groups",
        "uv run --locked --no-sync python -m tools.quality.python_matrix",
    ):
        if token not in matrix_block:
            raise AssertionError(
                f"Python matrix bootstrap must install and use the locked environment: {token!r}"
            )
    if "needs.native-assets.outputs.python-version" in text:
        raise AssertionError(
            "release assembly must read the Python SSOT, not a pass-through job output"
        )
    if (
        "RELEASE_ASSET_SIGNING_KEY_PATH: "
        "${{ secrets.CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY }}"
    ) in text:
        raise AssertionError("the product signer must receive a key path, not secret text")
    if "pull_request_target:" in text:
        raise AssertionError("verification workflow must not execute privileged pull-request code")
    if "@main" in text or "@master" in text:
        raise AssertionError("GitHub Actions must use immutable action revisions")


def _assert_github_platform_contract(text: str, release_text: str) -> None:
    mac_start = text.index("\n  python:")
    windows_start = text.index("\n  python-windows:")
    governance_start = text.index("\n  accepted-source:")
    mac_block = text[mac_start:windows_start]
    windows_block = text[windows_start:governance_start]
    setup_uv = "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9"
    if (
        mac_block.count(setup_uv) != 1
        or "cache-suffix: ${{ matrix.python-version }}" not in mac_block
    ):
        raise AssertionError("macOS Python matrix must isolate setup-uv caches by interpreter")
    test_owner = 'uv run --locked --group quality nox -s "tests-${{ matrix.python-version }}"'
    if test_owner not in mac_block:
        raise AssertionError(f"macOS Python matrix must run {test_owner}")
    for token in (
        "runs-on: windows-2025",
        "python-version: ${{ fromJSON(needs.python-matrix.outputs.versions) }}",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        'uv run --locked --group quality nox -s "tests-${{ matrix.python-version }}"',
    ):
        if token not in windows_block:
            raise AssertionError(f"Windows Python matrix must contain {token!r}")
    if text.count("actions/setup-python@") != 7:
        raise AssertionError(
            "host-native Python jobs must use pinned setup-python; Linux release uses its container"
        )
    if windows_block.count("actions/setup-python@") != 1:
        raise AssertionError("Windows verification must use exactly one pinned setup-python action")
    if (
        windows_block.count(setup_uv) != 1
        or "cache-suffix: ${{ matrix.python-version }}" not in windows_block
    ):
        raise AssertionError("Windows Python matrix must isolate setup-uv caches by interpreter")
    quality_start = text.index("\n  python-quality:")
    quality_end = text.index("\n  native-assets:", quality_start)
    quality_block = text[quality_start:quality_end]
    for token in ("fetch-depth: 0", "fetch-tags: true"):
        if token not in quality_block:
            raise AssertionError(f"quality checkout must contain {token!r}")
    for patch_pin in ("3.12.", "3.13.", "3.14."):
        if patch_pin in text or patch_pin in release_text:
            raise AssertionError(
                f"GitHub workflows must select supported Python lines, not patch releases: {patch_pin!r}"
            )


def _assert_github_governance_contract(text: str) -> None:
    accepted_start = text.index("\n  accepted-source:")
    tag_start = text.index("\n  tag-metadata:")
    quality_start = text.index("\n  python-quality:", tag_start)
    accepted_block = text[accepted_start:tag_start]
    tag_block = text[tag_start:quality_start]
    for block in (accepted_block, tag_block):
        for token in ("fetch-depth: 0", "fetch-tags: true"):
            if token not in block:
                raise AssertionError(f"governance checkout must contain {token!r}")
    tag_check = (
        'uv run --locked --no-sync python tools/release/metadata.py --tag "$GITHUB_REF_NAME"'
    )
    branch_check = "uv run --locked --no-sync python tools/release/metadata.py"
    if tag_check not in tag_block:
        raise AssertionError("tag metadata must validate the exact annotated tag")
    if branch_check not in accepted_block:
        raise AssertionError("accepted source must validate mainline metadata")
    if "--prepare-release" in accepted_block:
        raise AssertionError("accepted source verification must not require release preparation")


def _assert_github_native_and_forbidden_contract(text: str, release_text: str) -> None:
    windows_start = text.index("\n  python-windows:")
    governance_start = text.index("\n  accepted-source:")
    windows_block = text[windows_start:governance_start]
    native_start = text.index("\n  native-assets:")
    native_end = text.index("\n  release-assets:", native_start)
    native_block = text[native_start:native_end]
    if "shell: bash" in native_block or "set -euo pipefail" in native_block:
        raise AssertionError("native asset builds must use each runner's native command shell")
    if "shell:" in windows_block or ".sh" in windows_block:
        raise AssertionError("Windows verification must not depend on Bash or POSIX shell scripts")
    if "secrets:" in windows_block or "permissions:" in windows_block:
        raise AssertionError(
            "Windows verification must inherit the read-only, secret-free workflow contract"
        )
    for forbidden in (
        "self-hosted",
        "codex-responses-proxy-github-macos-arm64",
        "/opt/homebrew",
        "refs/codex-responses-proxy/runner-checkout-retained",
        "git update-ref",
    ):
        if forbidden in text or forbidden in release_text:
            raise AssertionError(
                f"GitHub workflows must not depend on runner-local state: {forbidden!r}"
            )
    for forbidden in ("git config --global", "GIT_ADVICE", "advice.detachedHead"):
        if forbidden in text or forbidden in release_text:
            raise AssertionError(
                f"GitHub workflows must not suppress Git diagnostics with {forbidden!r}"
            )
    print("GitHub Actions verification contract: OK")


def test_github_verification_workflow_contract() -> None:
    text = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    release_text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    _assert_github_required_tokens(text)
    _assert_github_matrix_contract(text, release_text)
    _assert_github_platform_contract(text, release_text)
    _assert_github_governance_contract(text)
    _assert_github_native_and_forbidden_contract(text, release_text)


def test_gitlab_pytest_invocations_preserve_repository_module_resolution() -> None:
    text = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

    if f"{GITLAB_LOCKED_PYTHON} pytest" in text:
        raise AssertionError("GitLab must not invoke the pytest console script directly")
    assert f"{GITLAB_LOCKED_PYTHON} pytest" not in text


def test_github_release_workflow_contract() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/release.yml")
    assert workflow["on"] == {"workflow_run": {"workflows": ["Verify"], "types": ["completed"]}}
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = _mapping(_mapping(workflow["jobs"])["verify-and-publish"])
    assert job["if"] == (
        "github.event.workflow_run.event == 'push' && "
        "github.event.workflow_run.conclusion == 'success' && "
        "startsWith(github.event.workflow_run.head_branch, 'v')"
    )
    for token in (
        "gh run download",
        "${{ github.event.workflow_run.id }}",
        "python -m tools.release.publish_github publish",
        "${{ github.event.workflow_run.head_branch }}",
        "${{ github.event.workflow_run.head_sha }}",
        '--assets "$RUNNER_TEMP/github-release/source"',
    ):
        assert token in text
    for forbidden in ("wait-verify", "sleep 10", "deadline=", "--run-id"):
        assert forbidden not in text
