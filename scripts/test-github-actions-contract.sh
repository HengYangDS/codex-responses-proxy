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
    '"$python" tests/test_package.py',
    '"$python" tests/test_empty_response_recovery.py',
    '"$python" tests/test_rolling_handoff.py',
    "python-windows:", "windows-2025",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", "# v7.0.0",
    "shell: bash",
    'python=/opt/homebrew/bin/python3.14',
    '"$python" scripts/check_release_metadata.py --allow-unpublished-history',
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
for test in (
    '"$python" tests/test_package.py',
    '"$python" tests/test_empty_response_recovery.py',
    '"$python" tests/test_rolling_handoff.py',
):
    if test not in mac_block:
        raise SystemExit(f"macOS Python matrix must run {test}")
for token in (
    "runs-on: windows-2025",
    'python-version: ["3.12", "3.13", "3.14"]',
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "shell: bash",
    "python tests/test_package.py",
    "python tests/test_empty_response_recovery.py",
    "python tests/test_rolling_handoff.py",
):
    if token not in windows_block:
        raise SystemExit(f"Windows Python matrix must contain {token!r}")
if "actions/setup-python@" in rest:
    raise SystemExit("only the Windows verification job may use actions/setup-python")
if windows_block.count("actions/setup-python@") != 1:
    raise SystemExit("Windows verification must use exactly one pinned setup-python action")
if "secrets:" in windows_block or "permissions:" in windows_block:
    raise SystemExit("Windows verification must inherit the read-only, secret-free workflow contract")
print("GitHub Actions verification contract: OK")
PYTHON
