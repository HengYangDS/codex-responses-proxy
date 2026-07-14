#!/usr/bin/env python3
"""Verify the immutable release identity carried by this repository."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def read_version() -> str:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise ValueError(f"VERSION is not a release SemVer: {version!r}")
    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="require an exact v<version> tag")
    args = parser.parse_args()
    version = read_version()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise SystemExit(f"CHANGELOG.md lacks release heading ## [{version}]")
    proxy = (ROOT / "proxy" / "dmx_responses_proxy.py").read_text(encoding="utf-8")
    if "release_version()" not in proxy:
        raise SystemExit("proxy runtime header does not read VERSION")
    if args.tag:
        expected = f"v{version}"
        if args.tag != expected:
            raise SystemExit(f"tag {args.tag!r} does not match expected {expected!r}")
        subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{args.tag}"], cwd=ROOT, check=True)
    print(f"release metadata: {version} OK")


if __name__ == "__main__":
    main()
