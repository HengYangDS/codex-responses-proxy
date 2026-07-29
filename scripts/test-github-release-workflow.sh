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
    "name: Release", 'tags: ["v*"]', "permissions:\n  contents: write\n  actions: read",
    "runs-on: [self-hosted, macOS, ARM64, codex-dmx-proxy-github-macos-arm64]",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    'python=/opt/homebrew/bin/python3.14',
    '"$python" scripts/check_release_metadata.py --allow-unpublished-history --tag',
    "check-release-tag-signature.sh",
    "actions/workflows/verify.yml/runs?branch=", "Verify workflow timed out",
    "expected_sha=$(git rev-parse 'HEAD^{commit}')", 'git rev-parse "$SELECTED_TAG^{tag}"',
    'if [ "$GITHUB_EVENT_NAME" = push ]; then', 'test "$GITHUB_SHA" = "$expected_sha"',
    'test "$tag_oid" = "$expected_tag_oid"', 'release.get("published_at")',
    'releases?per_page=100', "duplicate GitHub release records for exact tag",
    "GitHub release tag does not resolve to the checked-out commit",
    "gh release create", "--verify-tag", "--generate-notes",
    "existing GitHub release does not match exact release identity",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions release contract is missing {token!r}")
if "ubuntu-24.04" in text or "codex-dmx-proxy-github-verify-macos-arm64" in text or "codex-dmx-proxy-github-release-macos-arm64" in text:
    raise SystemExit("GitHub release workflow must use only its dedicated trusted runner")
if "actions/setup-python@" in text:
    raise SystemExit("self-hosted release must use the declared Homebrew Python")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub release workflow must use immutable action revisions")
print("GitHub Actions release contract: OK")
PYTHON
