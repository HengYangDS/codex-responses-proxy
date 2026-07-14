#!/usr/bin/env python3
"""Verify release identity, changelog provenance, and governance contracts."""

from __future__ import annotations

import argparse
import re
import subprocess
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


def changelog_releases(path: Path | None = None) -> list[tuple[str, str]]:
    headings: list[tuple[str, str | None]] = []
    changelog = path or ROOT / "CHANGELOG.md"
    for line in changelog.read_text(encoding="utf-8").splitlines():
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
    return [(version, date) for version, date in released if date is not None]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def check_changelog_provenance(releases: list[tuple[str, str]]) -> None:
    """Require exact, dated Changelog coverage for every locally known release tag."""

    actual_versions = [version for version, _ in releases]
    expected_versions = [
        tag.removeprefix("v")
        for tag in _git("tag", "--list", "v[0-9]*", "--sort=-version:refname").splitlines()
        if re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag)
    ]
    if not expected_versions:
        raise ValueError("cannot find a release SemVer tag")
    shallow = _git("rev-parse", "--is-shallow-repository") == "true"
    missing = [version for version in actual_versions if version not in expected_versions]
    if missing and not shallow:
        raise ValueError("release heading has no matching Git tag: " + ", ".join(missing))
    if len(actual_versions) != len(set(actual_versions)):
        raise ValueError("released CHANGELOG headings must not duplicate a version")
    missing_headings = [version for version in expected_versions if version not in actual_versions]
    if missing_headings:
        raise ValueError(
            "locally available release tags must appear once in CHANGELOG.md: "
            + ", ".join(missing_headings)
        )
    for version, date in releases:
        if version not in expected_versions:
            continue
        tag_date = _git("for-each-ref", f"refs/tags/v{version}", "--format=%(creatordate:short)")
        if date != tag_date:
            raise ValueError(
                f"CHANGELOG release {version} is dated {date}, but tag v{version} was created on {tag_date}"
            )


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
    gitlab_identity = (
        "| GitLab metadata | Value |\n"
        "| --- | --- |\n"
        "| **Project Name** | `Codex DMX Proxy` |\n"
        "| **Stable repository Path** | `codex-dmx-proxy` |"
    )
    if gitlab_identity not in readme:
        raise ValueError("README.md must declare formal GitLab Project Name and stable Path in its metadata table")
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if "python scripts/check_release_metadata.py" not in ci:
        raise ValueError("GitLab CI must execute the release and governance checker")
    retired_paths = ("docs/reviews", "docs/specs", "docs/superpowers", "docs/design")
    present = [path for path in retired_paths if (ROOT / path).exists()]
    if present:
        raise ValueError("retired execution-document paths must be moved under docs/history: " + ", ".join(present))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="require an exact v<version> tag")
    parser.add_argument("--changelog", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    version = read_version()
    releases = changelog_releases(args.changelog)
    check_changelog_provenance(releases)
    if version not in {released for released, _ in releases}:
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
