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
    "runs-on: [self-hosted, macOS, ARM64, codex-dmx-proxy-github-verify-macos-arm64]",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "python-version: [\"3.12\", \"3.13\", \"3.14\"]",
    'python="/opt/homebrew/bin/python${{ matrix.python-version }}"',
    '"$python" -m compileall -q',
    '"$python" tests/test_package.py',
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
if "ubuntu-24.04" in text or "codex-dmx-proxy-github-release-macos-arm64" in text:
    raise SystemExit("verification workflow must use only its dedicated trusted runner")
if "actions/setup-python@" in text:
    raise SystemExit("self-hosted verification must use the declared Homebrew Python matrix")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub Actions must use immutable action revisions")
print("GitHub Actions verification contract: OK")
PYTHON
