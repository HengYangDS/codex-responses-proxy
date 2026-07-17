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
    "name: Verify", "pull_request:", "push:", "workflow_dispatch:",
    "permissions:\n  contents: read",
    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "python-version: [\"3.12\", \"3.13\", \"3.14\"]",
    "python tests/test_package.py", "check_release_metadata.py",
    "test-github-provider-projection.sh", "test-github-tagging.sh",
]
for token in required:
    if token not in text:
        raise SystemExit(f"GitHub Actions verification contract is missing {token!r}")
if "contents: write" in text:
    raise SystemExit("verification workflow must use read-only repository permissions")
if "@main" in text or "@master" in text:
    raise SystemExit("GitHub Actions must use immutable action revisions")
print("GitHub Actions verification contract: OK")
PYTHON
