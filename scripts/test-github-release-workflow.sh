#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
workflow="$root/.github/workflows/release.yml"

[ -f "$workflow" ] || { echo "GitHub Actions release workflow is missing" >&2; exit 1; }
python3 - "$workflow" <<'PYTHON'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "name: Release", 'tags: ["v*"]', "permissions:\n  contents: write",
    "runs-on: [self-hosted, macOS, ARM64, codex-dmx-proxy-github-release-macos-arm64]",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "check-release-tag-signature.sh", "check_release_metadata.py --allow-unpublished-history --tag",
    "gh release create", "--verify-tag", "--generate-notes",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions release contract is missing {token!r}")
if "ubuntu-24.04" in text or "codex-dmx-proxy-github-verify-macos-arm64" in text:
    raise SystemExit("GitHub release workflow must use only its dedicated trusted runner")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub release workflow must use immutable action revisions")
print("GitHub Actions release contract: OK")
PYTHON
