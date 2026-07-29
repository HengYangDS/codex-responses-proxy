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
    "require-verify:", "runs-on: ubuntu-24.04", "timeout-minutes: 45",
    "actions: read", "contents: read",
    'test "$GITHUB_REF_TYPE" = tag',
    "actions/workflows/verify.yml/runs?branch=$GITHUB_REF_NAME&event=push&per_page=100",
    'run.get("path") == ".github/workflows/verify.yml"',
    'run.get("head_branch") == tag', 'run.get("head_sha") == sha',
    'if len(matches) > 1:', 'not matches or matches[0].get("status") != "completed"',
    'print(matches[0].get("conclusion") or "failed")',
    "deadline=$((SECONDS + 2400))", "sleep 10", "needs: require-verify",
    "runs-on: [self-hosted, macOS, ARM64, codex-dmx-proxy-github-macos-arm64]",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    'git fetch --force --no-tags origin "+refs/tags/$SELECTED_TAG:refs/tags/$SELECTED_TAG"',
    'git cat-file -t "refs/tags/$SELECTED_TAG"',
    'target=$(git rev-parse "refs/tags/$SELECTED_TAG^{commit}")',
    'test "$target" = "$VERIFIED_SHA"', 'git checkout --detach "$target"',
    'python=/opt/homebrew/bin/python3.14',
    '"$python" scripts/check_release_metadata.py --provider github --tag "$SELECTED_TAG"',
    "check-release-tag-signature.sh", "expected_sha=$(git rev-parse 'HEAD^{commit}')",
    'git rev-parse "$SELECTED_TAG^{tag}"', 'test "$tag_oid" = "$expected_tag_oid"',
    'release.get("published_at")', 'releases?per_page=100',
    "duplicate GitHub release records for exact tag",
    "GitHub release tag does not resolve to the checked-out commit",
    "gh release create", "--verify-tag", "--generate-notes",
    "existing GitHub release does not match exact release identity",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions release contract is missing {token!r}")
for retired in ("workflow_run:", "workflow_dispatch:"):
    if retired in text:
        raise SystemExit(f"GitHub release workflow retains deadlocking trigger or polling: {retired!r}")
gate_start = text.index("\n  require-verify:")
release_start = text.index("\n  verify-and-publish:")
gate = text[gate_start:release_start]
release = text[release_start:]
if "actions/checkout@" in gate or "contents: write" in gate:
    raise SystemExit("GitHub-hosted release gate must not checkout source or receive write permission")
if "runs-on: ubuntu-24.04" in release:
    raise SystemExit("GitHub-hosted runner must not execute release source")
if "sleep 10" in release or "deadline=" in release:
    raise SystemExit("trusted release publisher must not wait for another workflow")
if "--allow-unpublished-history" in text:
    raise SystemExit("GitHub release workflow must not bypass provider chronology")
if "actions/setup-python@" in text:
    raise SystemExit("self-hosted release must use the declared Homebrew Python")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub Actions must use immutable action revisions")
print("GitHub Actions release contract: OK")
PYTHON
