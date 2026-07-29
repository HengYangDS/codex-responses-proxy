#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
workflow="$root/.github/workflows/verify.yml"

[ -f "$workflow" ] || { echo "GitHub Actions verification workflow is missing" >&2; exit 1; }
python3 - "$workflow" <<'PYTHON'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "name: Verify", "push:", "workflow_dispatch:", "branches: [main]", 'tags: ["v*"]',
    "permissions:\n  contents: read",
    "runs-on: [self-hosted, macOS, ARM64, codex-dmx-proxy-github-macos-arm64]",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "python-version: [\"3.12\", \"3.13\", \"3.14\"]",
    'python="/opt/homebrew/bin/python${{ matrix.python-version }}"',
    '"$python" -m compileall -q',
    '"$python" scripts/run-python-tests.py',
    "python-windows:", "windows-2025",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", "# v7.0.0",
    "shell: bash",
    'python=/opt/homebrew/bin/python3.14',
    'fetch-tags: true',
    'if: github.ref_type == \'tag\'',
    'git fetch --force --no-tags origin "+refs/tags/$GITHUB_REF_NAME:refs/tags/$GITHUB_REF_NAME"',
    'git cat-file -t "refs/tags/$GITHUB_REF_NAME"',
    'git rev-parse "refs/tags/$GITHUB_REF_NAME^{commit}"',
    'git checkout --detach "$GITHUB_SHA"',
    'if [[ "$GITHUB_REF_TYPE" == tag ]]; then',
    '"$python" scripts/check_release_metadata.py --provider github --tag "$GITHUB_REF_NAME"',
    '"$python" scripts/check_release_metadata.py --provider github',
    "python-quality:", "scripts/run-python-quality.sh",
    "test-github-provider-projection.sh", "test-gitlab-tagging.sh", "test-github-tagging.sh", "test-publish-gitlab-release.sh",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions verification contract is missing {token!r}")
if "contents: write" in text:
    raise SystemExit("verification workflow must use read-only repository permissions")
if "pull_request:" in text or "pull_request_target:" in text:
    raise SystemExit("verification workflow must not execute pull-request workflow code")
if "ubuntu-24.04" in text or "codex-dmx-proxy-github-verify-macos-arm64" in text or "codex-dmx-proxy-github-release-macos-arm64" in text:
    raise SystemExit("verification workflow must use only its dedicated trusted runner")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub Actions must use immutable action revisions")

mac_start = text.index("\n  python:")
windows_start = text.index("\n  python-windows:")
governance_start = text.index("\n  governance:")
mac_block = text[mac_start:windows_start]
windows_block = text[windows_start:governance_start]
rest = text[:windows_start] + text[governance_start:]
test_owner = '"$python" scripts/run-python-tests.py'
if test_owner not in mac_block:
    raise SystemExit(f"macOS Python matrix must run {test_owner}")
for token in (
    "runs-on: windows-2025",
    'python-version: ["3.12", "3.13", "3.14"]',
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "shell: bash",
    "python scripts/run-python-tests.py",
):
    if token not in windows_block:
        raise SystemExit(f"Windows Python matrix must contain {token!r}")
if "actions/setup-python@" in rest:
    raise SystemExit("only the Windows verification job may use actions/setup-python")
if windows_block.count("actions/setup-python@") != 1:
    raise SystemExit("Windows verification must use exactly one pinned setup-python action")
governance_end = text.index("\n  python-quality:", governance_start)
governance_block = text[governance_start:governance_end]
checkout_block = governance_block.split("- name: Verify release", 1)[0]
for token in ("fetch-depth: 0", "fetch-tags: true"):
    if token not in checkout_block:
        raise SystemExit(f"governance checkout must contain {token!r}")
tag_check = '"$python" scripts/check_release_metadata.py --provider github --tag "$GITHUB_REF_NAME"'
branch_check = '"$python" scripts/check_release_metadata.py --provider github'
for token in ('if [[ "$GITHUB_REF_TYPE" == tag ]]; then', tag_check, "else", branch_check):
    if token not in governance_block:
        raise SystemExit(f"governance ref dispatch must contain {token!r}")
if governance_block.count(branch_check) != 2:
    raise SystemExit("governance must use one exact-tag and one ordinary GitHub check")
if "--provider github --prepare-release" in governance_block:
    raise SystemExit("ordinary GitHub main verification must not require same-day release preparation")
if governance_block.index(tag_check) > governance_block.rindex(branch_check):
    raise SystemExit("governance ref dispatch must select tag validation before branch fallback")
if "secrets:" in windows_block or "permissions:" in windows_block:
    raise SystemExit("Windows verification must inherit the read-only, secret-free workflow contract")
for retired in (
    "tests/test_package.py",
    "tests/test_empty_response_recovery.py",
    "tests/test_rolling_handoff.py",
):
    if retired in text:
        raise SystemExit(f"verification workflow retains retired test owner {retired!r}")
print("GitHub Actions verification contract: OK")
PYTHON
