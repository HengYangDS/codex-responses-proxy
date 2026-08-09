"""Portable contracts for GitHub verification and release workflows."""

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_python_matrix_output_comes_from_the_repository_ssot(tmp_path: Path) -> None:
    module = importlib.import_module("tools.quality.python_matrix")
    versions = tmp_path / ".python-versions"
    output = tmp_path / "github-output"
    versions.write_text("3.12\n3.13\n3.14\n", encoding="ascii")

    module.write(versions=versions, output=output)

    assert output.read_text(encoding="utf-8") == (
        'value=["3.12", "3.13", "3.14"]\nfloor=3.12\nlatest=3.14\n'
    )


def test_github_verification_workflow_contract() -> None:
    text = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    release_text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    required = [
        "name: Verify",
        "push:",
        "workflow_dispatch:",
        "branches: [main]",
        'tags: ["v*"]',
        "permissions:\n  contents: read",
        'GIT_CONFIG_COUNT: "1"',
        "GIT_CONFIG_KEY_0: init.defaultBranch",
        "GIT_CONFIG_VALUE_0: main",
        "runs-on: macos-26",
        "runs-on: ubuntu-24.04",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "python -m tools.quality.python_matrix",
        "python-version: ${{ fromJSON(needs.python-matrix.outputs.versions) }}",
        'uv run --locked --group quality nox -s "tests-${{ matrix.python-version }}"',
        "python-windows:",
        "windows-2025",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "# v7.0.0",
        "fetch-tags: true",
        "if: github.ref_type == 'tag'",
        "python -m tools.release.publish_github prepare-checkout",
        'uv run --locked --no-sync python tools/release/metadata.py --provider github --tag "$GITHUB_REF_NAME"',
        "uv run --locked --no-sync python tools/release/metadata.py --provider github",
        "python-quality:",
        "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
        "uv run --locked --group quality nox -s quality",
        "tests/quality/test_contract.py tests/forge/test_workflow_contracts.py tests/forge/test_tagging.py",
        "tests/release/test_publish_gitlab.py",
        "native-assets:",
        "name: Native asset (${{ matrix.platform }})",
        "platform: linux-x86_64",
        "platform: macos-arm64",
        "platform: windows-x86_64",
        'uv run --locked --no-sync nox -s release -- "${{ runner.temp }}/native-assets"',
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "# v7.0.1",
        "release-assets:",
        "name: Release assets",
        "needs: [python-matrix, native-assets]",
        "python-version: ${{ needs.python-matrix.outputs.latest }}",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "# v8.0.1",
        "uv run --locked --no-sync python -m tools.release.assemble_assets",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
        "--sign",
        "name: release-assets",
    ]
    for token in required:
        if token not in text:
            raise AssertionError(f"GitHub Actions verification contract is missing {token!r}")
    if "contents: write" in text:
        raise AssertionError("verification workflow must use read-only repository permissions")
    if "needs.native-assets.outputs.python-version" in text:
        raise AssertionError(
            "release assembly must read the Python SSOT, not a pass-through job output"
        )
    if "pull_request:" in text or "pull_request_target:" in text:
        raise AssertionError("verification workflow must not execute pull-request workflow code")
    if "@main" in text or "@master" in text:
        raise AssertionError("GitHub Actions must use immutable action revisions")

    mac_start = text.index("\n  python:")
    windows_start = text.index("\n  python-windows:")
    governance_start = text.index("\n  governance:")
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
    if text.count("actions/setup-python@") != 6:
        raise AssertionError(
            "every Python-bearing verification or asset job must use pinned setup-python"
        )
    if windows_block.count("actions/setup-python@") != 1:
        raise AssertionError("Windows verification must use exactly one pinned setup-python action")
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
    governance_end = text.index("\n  python-quality:", governance_start)
    governance_block = text[governance_start:governance_end]
    checkout_block = governance_block.split("- name: Fetch the exact", 1)[0]
    for token in ("fetch-depth: 0", "fetch-tags: true"):
        if token not in checkout_block:
            raise AssertionError(f"governance checkout must contain {token!r}")
    tag_check = 'uv run --locked --no-sync python tools/release/metadata.py --provider github --tag "$GITHUB_REF_NAME"'
    branch_check = "uv run --locked --no-sync python tools/release/metadata.py --provider github"
    for token in (
        "if: github.ref_type == 'tag'",
        "if: github.ref_type != 'tag'",
        tag_check,
        branch_check,
    ):
        if token not in governance_block:
            raise AssertionError(f"governance ref dispatch must contain {token!r}")
    if governance_block.count(branch_check) != 2:
        raise AssertionError("governance must use one exact-tag and one ordinary GitHub check")
    if "--provider github --prepare-release" in governance_block:
        raise AssertionError(
            "ordinary GitHub main verification must not require same-day release preparation"
        )
    if governance_block.index(tag_check) > governance_block.rindex(branch_check):
        raise AssertionError(
            "governance ref dispatch must select tag validation before branch fallback"
        )
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


def test_github_release_workflow_contract() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    required = [
        "name: Release",
        'tags: ["v*"]',
        "permissions:\n  contents: write\n  actions: read",
        "require-verify:",
        "runs-on: ubuntu-24.04",
        "timeout-minutes: 45",
        "actions: read",
        "contents: read",
        "python -m tools.release.publish_github wait-verify",
        '--repository "$GITHUB_REPOSITORY"',
        '--tag "$GITHUB_REF_NAME"',
        '--commit-oid "$GITHUB_SHA"',
        '--output "$GITHUB_OUTPUT"',
        "needs: require-verify",
        "runs-on: ubuntu-24.04",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "CODEX_RESPONSES_PROXY_GITHUB_TAG_TRUST",
        "run-id: ${{ steps.verify.outputs.run-id }}",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
        "python -m tools.release.publish_github publish",
        '--repository "$GITHUB_REPOSITORY"',
        '--tag "$GITHUB_REF_NAME"',
        '--commit-oid "$GITHUB_SHA"',
        '--run-id "${{ needs.require-verify.outputs.run-id }}"',
        '--workspace "$RUNNER_TEMP/github-release"',
    ]
    for token in required:
        if token not in text:
            raise AssertionError(f"GitHub Actions release contract is missing {token!r}")
    for forbidden in ("set -euo pipefail", "python3 -", "ssh-keygen -Y", "gh release"):
        if forbidden in text:
            raise AssertionError(
                f"GitHub Actions release logic escaped its Python owner: {forbidden}"
            )
    for retired in ("workflow_run:", "workflow_dispatch:"):
        if retired in text:
            raise AssertionError(
                f"GitHub release workflow retains deadlocking trigger or polling: {retired!r}"
            )
    gate_start = text.index("\n  require-verify:")
    release_start = text.index("\n  verify-and-publish:")
    gate = text[gate_start:release_start]
    release = text[release_start:]
    if "ref: main" not in gate or "persist-credentials: false" not in gate:
        raise AssertionError(
            "GitHub-hosted release gate must execute only the protected main publication owner"
        )
    if "contents: write" in gate:
        raise AssertionError("GitHub-hosted release gate must remain read-only")
    if "sleep 10" in release or "deadline=" in release:
        raise AssertionError("trusted release publisher must not wait for another workflow")
    if "--allow-unpublished-history" in text:
        raise AssertionError("GitHub release workflow must not bypass provider chronology")
    if text.count("actions/setup-python@") != 2:
        raise AssertionError("both release jobs must use pinned portable Python setup")
    for forbidden in (
        "self-hosted",
        "/opt/homebrew",
        "refs/codex-responses-proxy/runner-checkout-retained",
        "git update-ref",
    ):
        if forbidden in text:
            raise AssertionError(
                f"release workflow must not depend on runner-local state: {forbidden!r}"
            )
    if "@main" in text or "@master" in text:
        raise AssertionError("GitHub Actions must use immutable action revisions")
    for forbidden in ("set -euo pipefail", "ssh-keygen -Y", "$ErrorActionPreference"):
        if forbidden in text:
            raise AssertionError(
                f"GitHub Actions verification logic escaped its Python owner: {forbidden}"
            )
    print("GitHub Actions release contract: OK")
