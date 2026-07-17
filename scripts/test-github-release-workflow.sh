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
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "check-release-tag-signature.sh", "check_release_metadata.py --tag",
    "gh release create", "--verify-tag", "--generate-notes",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions release contract is missing {token!r}")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub release workflow must use immutable action revisions")
print("GitHub Actions release contract: OK")
PYTHON
