#!/usr/bin/env python3
"""Verify release identity and the repository's minimal governance contract."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_HEADING = re.compile(
    r"^## \[(?P<version>Unreleased|(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$"
)


def read_version() -> str:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise ValueError(f"VERSION is not a release SemVer: {version!r}")
    return version


def _version_key(version: str) -> tuple[int, int, int]:
    return tuple(map(int, version.split(".")))


def changelog_releases() -> list[str]:
    headings: list[tuple[str, str | None]] = []
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        match = CHANGELOG_HEADING.match(line)
        if match:
            headings.append((match.group("version"), match.group("date")))
    if not headings or headings[0][0] != "Unreleased":
        raise ValueError("CHANGELOG.md must start its release sections with ## [Unreleased]")
    if sum(1 for version, _ in headings if version == "Unreleased") != 1:
        raise ValueError("CHANGELOG.md must contain exactly one Unreleased section")
    released = headings[1:]
    if any(version == "Unreleased" or date is None for version, date in released):
        raise ValueError("released CHANGELOG headings must be dated and follow Unreleased")
    versions = [version for version, _ in released]
    if versions != sorted(versions, key=_version_key, reverse=True):
        raise ValueError("released CHANGELOG headings must be in descending SemVer order")
    return versions


def check_governance_contract() -> None:
    required = (
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docs/README.md",
        "docs/architecture/authority-and-runtime-boundary.md",
        "docs/governance/release-and-change-policy.md",
        "docs/decisions/0001-control-plane-data-plane-boundary.md",
        "docs/evidence/README.md",
    )
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        raise ValueError("missing governance documents: " + ", ".join(missing))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith("# Codex DMX Proxy\n"):
        raise ValueError("README.md must use the formal Project Name as its title")
    if "**GitLab Project Name:** `Codex DMX Proxy`" not in readme:
        raise ValueError("README.md must declare the formal GitLab Project Name")
    if "**Stable repository Path:** `codex-dmx-proxy`" not in readme:
        raise ValueError("README.md must declare the stable GitLab Path separately")
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if "python scripts/check_release_metadata.py" not in ci:
        raise ValueError("GitLab CI must execute the release and governance checker")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="require an exact v<version> tag")
    args = parser.parse_args()
    version = read_version()
    releases = changelog_releases()
    if version not in releases:
        raise SystemExit(f"CHANGELOG.md lacks dated release heading ## [{version}]")
    proxy = (ROOT / "proxy" / "dmx_responses_proxy.py").read_text(encoding="utf-8")
    if "release_version()" not in proxy:
        raise SystemExit("proxy runtime header does not read VERSION")
    try:
        check_governance_contract()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.tag:
        expected = f"v{version}"
        if args.tag != expected:
            raise SystemExit(f"tag {args.tag!r} does not match expected {expected!r}")
        subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{args.tag}"], cwd=ROOT, check=True)
    print(f"release and governance metadata: {version} OK")


if __name__ == "__main__":
    main()
