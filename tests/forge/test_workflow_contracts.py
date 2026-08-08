"""Portable contracts for GitHub verification and release workflows."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
        'versions = Path(".python-versions").read_text(encoding="utf-8").splitlines()',
        "python-version: ${{ fromJSON(needs.python-matrix.outputs.versions) }}",
        'uv run --locked --no-sync nox -s "tests-${{ matrix.python-version }}"',
        "python-windows:",
        "windows-2025",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "# v7.0.0",
        "shell: pwsh",
        "fetch-tags: true",
        "if: github.ref_type == 'tag'",
        'git fetch --force --no-tags origin "+refs/tags/$GITHUB_REF_NAME:refs/tags/$GITHUB_REF_NAME"',
        'git cat-file -t "refs/tags/$GITHUB_REF_NAME"',
        'git rev-parse "refs/tags/$GITHUB_REF_NAME^{commit}"',
        'git checkout --detach "$GITHUB_SHA"',
        'if [[ "$GITHUB_REF_TYPE" == tag ]]; then',
        'uv run --locked --no-sync python tools/release/metadata.py --provider github --tag "$GITHUB_REF_NAME"',
        "uv run --locked --no-sync python tools/release/metadata.py --provider github",
        "python-quality:",
        "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
        "uv sync --locked --only-group quality",
        "uv run --locked --no-sync nox -s quality",
        "tests/forge/test_tagging.py",
        "tests/release/test_publish_gitlab.py",
        "native-assets:",
        "name: Native asset (${{ matrix.platform }})",
        "platform: linux-x86_64",
        "platform: macos-arm64",
        "platform: windows-x86_64",
        'uv run --locked --no-sync nox -s release -- "$RUNNER_TEMP/native-assets"',
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "# v7.0.1",
        "release-assets:",
        "name: Release assets",
        "needs: [python-matrix, native-assets]",
        "python-version: ${{ needs.python-matrix.outputs.latest }}",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "# v8.0.1",
        "uv run --locked --no-sync python tools/release/assemble_assets.py",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
        "ssh-keygen -Y sign",
        'uv run --locked --no-sync python tools/release/assemble_assets.py --verify "$release"',
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
    test_owner = 'uv run --locked --no-sync nox -s "tests-${{ matrix.python-version }}"'
    if test_owner not in mac_block:
        raise AssertionError(f"macOS Python matrix must run {test_owner}")
    for token in (
        "runs-on: windows-2025",
        "python-version: ${{ fromJSON(needs.python-matrix.outputs.versions) }}",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "shell: pwsh",
        'uv run --locked --no-sync nox -s "tests-${{ matrix.python-version }}"',
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
    checkout_block = governance_block.split("- name: Verify release", 1)[0]
    for token in ("fetch-depth: 0", "fetch-tags: true"):
        if token not in checkout_block:
            raise AssertionError(f"governance checkout must contain {token!r}")
    tag_check = 'uv run --locked --no-sync python tools/release/metadata.py --provider github --tag "$GITHUB_REF_NAME"'
    branch_check = "uv run --locked --no-sync python tools/release/metadata.py --provider github"
    for token in ('if [[ "$GITHUB_REF_TYPE" == tag ]]; then', tag_check, "else", branch_check):
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
    if "shell: bash" in windows_block or ".sh" in windows_block:
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
        'test "$GITHUB_REF_TYPE" = tag',
        "actions/workflows/verify.yml/runs?branch=$GITHUB_REF_NAME&event=push&per_page=100",
        'run.get("path") == ".github/workflows/verify.yml"',
        'run.get("head_branch") == tag',
        'run.get("head_sha") == sha',
        "if len(matches) > 1:",
        'not matches or matches[0].get("status") != "completed"',
        'print(matches[0].get("conclusion") or "failed")',
        "deadline=$((SECONDS + 2400))",
        "sleep 10",
        "needs: require-verify",
        "runs-on: ubuntu-24.04",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        'git fetch --force --no-tags origin "+refs/tags/$SELECTED_TAG:refs/tags/$SELECTED_TAG"',
        'git cat-file -t "refs/tags/$SELECTED_TAG"',
        'target=$(git rev-parse "refs/tags/$SELECTED_TAG^{commit}")',
        'test "$target" = "$VERIFIED_SHA"',
        'git checkout --detach "$target"',
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        'uv run --locked --no-sync python tools/release/metadata.py --provider github --tag "$SELECTED_TAG"',
        "CODEX_RESPONSES_PROXY_GITHUB_TAG_TRUST",
        'anchor="$RUNNER_TEMP/github-tag-allowed-signers"',
        "tools.forge.tag_signature",
        "expected_sha=$(git rev-parse 'HEAD^{commit}')",
        'git rev-parse "$SELECTED_TAG^{tag}"',
        'test "$tag_oid" = "$expected_tag_oid"',
        'release.get("published_at")',
        "releases?per_page=100",
        "duplicate GitHub release records for exact tag",
        "GitHub release tag does not resolve to the checked-out commit",
        "gh release create",
        "--verify-tag",
        "--generate-notes",
        "run-id: ${{ steps.verify.outputs.run-id }}",
        "VERIFIED_RUN_ID: ${{ needs.require-verify.outputs.run-id }}",
        'gh run download "$VERIFIED_RUN_ID"',
        "--name release-assets",
        "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
        "ssh-keygen -Y find-principals",
        "ssh-keygen -Y verify",
        'uv run --locked --no-sync python tools/release/assemble_assets.py --verify "$assets"',
        '"$assets"/*',
        'gh release download "$SELECTED_TAG"',
        'uv run --locked --no-sync python tools/release/assemble_assets.py --verify "$downloaded"',
        'diff -qr "$assets" "$downloaded"',
        "existing GitHub release does not match exact release identity",
    ]
    for token in required:
        if token not in text:
            raise AssertionError(f"GitHub Actions release contract is missing {token!r}")
    for retired in ("workflow_run:", "workflow_dispatch:"):
        if retired in text:
            raise AssertionError(
                f"GitHub release workflow retains deadlocking trigger or polling: {retired!r}"
            )
    gate_start = text.index("\n  require-verify:")
    release_start = text.index("\n  verify-and-publish:")
    gate = text[gate_start:release_start]
    release = text[release_start:]
    if "actions/checkout@" in gate or "contents: write" in gate:
        raise AssertionError(
            "GitHub-hosted release gate must not checkout source or receive write permission"
        )
    if "sleep 10" in release or "deadline=" in release:
        raise AssertionError("trusted release publisher must not wait for another workflow")
    if "--allow-unpublished-history" in text:
        raise AssertionError("GitHub release workflow must not bypass provider chronology")
    if text.count("actions/setup-python@") != 1:
        raise AssertionError("release workflow must use one pinned portable Python setup")
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
    print("GitHub Actions release contract: OK")
