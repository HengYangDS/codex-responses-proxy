#!/usr/bin/env python3
"""Verify release identity, changelog provenance, and governance contracts."""

from __future__ import annotations

import argparse
import re
import subprocess
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_HEADING = re.compile(
    r"^## \[(?P<version>Unreleased|(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$"
)


def read_version() -> str:
    """Return the repository release version after strict SemVer validation."""

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise ValueError(f"VERSION is not a release SemVer: {version!r}")
    return version


def check_python_metadata() -> None:
    """Keep Python support metadata aligned without duplicating release ownership."""

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if "project" in metadata or "build-system" in metadata:
        raise ValueError("pyproject.toml is tool metadata, not a Python distribution contract")
    repository = metadata.get("tool", {}).get("codex-dmx-proxy", {})
    if repository.get("supported-python") != ">=3.12" or "python-requires" in repository:
        raise ValueError("pyproject.toml must support Python >=3.12 without an upper bound")
    if repository.get("version-source") != "VERSION" or "version" in repository:
        raise ValueError("VERSION must remain the only release-version owner")
    if repository.get("distribution-mode") != "runtime-file-payload":
        raise ValueError("the repository must declare its explicit runtime-file payload model")
    if repository.get("build-system-allowed") is not False:
        raise ValueError("a Python build system requires a separate complete packaging contract")


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def known_release_versions() -> list[str]:
    """Return locally known final-release tags in descending SemVer order."""

    return [
        tag.removeprefix("v")
        for tag in _git("tag", "--list", "v[0-9]*", "--sort=-version:refname").splitlines()
        if re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag)
    ]


def changelog_releases(path: Path | None = None) -> list[tuple[str, str]]:
    """Return dated Changelog releases after validating section structure."""

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


def check_changelog_provenance(
    releases: list[tuple[str, str]],
    *,
    allow_unpublished_history: bool = False,
    pending_version: str | None = None,
) -> None:
    """Require exact, dated Changelog coverage for every locally known release tag."""

    actual_versions = [version for version, _ in releases]
    expected_versions = known_release_versions()
    if not expected_versions:
        if allow_unpublished_history:
            return
        raise ValueError("cannot find a release SemVer tag")
    shallow = _git("rev-parse", "--is-shallow-repository") == "true"
    missing = [
        version
        for version in actual_versions
        if version not in expected_versions and version != pending_version
    ]
    if missing and not shallow and not allow_unpublished_history:
        raise ValueError("release heading has no matching Git tag: " + ", ".join(missing))
    if len(actual_versions) != len(set(actual_versions)):
        raise ValueError("released CHANGELOG headings must not duplicate a version")
    missing_headings = [version for version in expected_versions if version not in actual_versions]
    if missing_headings:
        raise ValueError(
            "locally available release tags must appear once in CHANGELOG.md: "
            + ", ".join(missing_headings)
        )
    for version, release_date in releases:
        if version not in expected_versions:
            continue
        tag_date = _git("for-each-ref", f"refs/tags/v{version}", "--format=%(creatordate:short)")
        if release_date != tag_date:
            raise ValueError(
                f"CHANGELOG release {version} is dated {release_date}, but tag v{version} was created on {tag_date}"
            )


def check_active_release_train(
    version: str,
    releases: list[tuple[str, str]],
    *,
    allow_unpublished_history: bool = False,
    pending_release: bool = False,
) -> None:
    """Accept an untagged next version without treating it as published.

    A deployed source tree may contain several ordinary commits between releases.
    The active ``VERSION`` names that next release train, while the dated
    Changelog headings remain an immutable record of tags that already exist.
    """
    known = known_release_versions()
    published = {released for released, _ in releases}
    if version in known:
        if version not in published:
            raise ValueError(f"CHANGELOG.md lacks dated release heading ## [{version}]")
        return
    if version in published:
        if allow_unpublished_history or pending_release:
            return
        raise ValueError(f"CHANGELOG release {version} exists before its Git tag")
    comparison_set = known + [released for released, _ in releases]
    if not comparison_set:
        raise ValueError("cannot identify an existing release version")
    if _version_key(version) <= max(map(_version_key, comparison_set)):
        raise ValueError(
            f"untagged VERSION {version} must be newer than the latest released version"
        )


def check_pending_release_date(
    version: str,
    releases: list[tuple[str, str]],
    *,
    today: date | None = None,
) -> None:
    """Require a pending release heading to use the current UTC date."""

    current_date = today or datetime.now(timezone.utc).date()
    release_date = next((item_date for item, item_date in releases if item == version), None)
    if release_date != current_date.isoformat():
        raise ValueError(
            f"pending release {version} must use the current UTC date {current_date.isoformat()}"
        )


def check_governance_contract() -> None:
    """Validate the repository's release and dual-forge governance surfaces."""

    required = (
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docs/README.md",
        "docs/architecture/authority-and-runtime-boundary.md",
        "docs/governance/release-and-change-policy.md",
        "docs/decisions/0001-control-plane-data-plane-boundary.md",
        "docs/evidence/README.md",
        "docs/operations/forge-operations.md",
        "LICENSE",
        "governance.py",
        "scripts/project-github-forge.sh",
        "scripts/project-gitlab-forge.sh",
        "scripts/rewrite-provider-history.py",
        "scripts/test-gitlab-provider-projection.sh",
        "scripts/test-github-provider-projection.sh",
        "scripts/audit-dual-forge-parity.py",
        "scripts/tag-gitlab-release.sh",
        "scripts/tag-github-release.sh",
        "scripts/check-release-tag-signature.sh",
        "scripts/publish-gitlab-release.sh",
        "scripts/observe-reliability.py",
        "packaging/release/gitlab-allowed-signers",
        "packaging/release/github-allowed-signers",
        ".github/workflows/verify.yml",
        ".github/workflows/release.yml",
    )
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        raise ValueError("missing governance documents: " + ", ".join(missing))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith("# Codex DMX Proxy\n"):
        raise ValueError("README.md must use the formal Project Name as its title")
    project_identity = (
        "| Project identity | Value |\n"
        "| --- | --- |\n"
        "| **GitLab Project Name** | `Codex DMX Proxy` |\n"
        "| **GitLab repository path** | `codex-dmx-proxy` |\n"
        "| **GitHub repository** | `HengYangDS/codex-dmx-proxy` |\n"
        "| **License** | [MIT](LICENSE) |"
    )
    if project_identity not in readme:
        raise ValueError(
            "README.md must declare formal dual-forge identity and MIT license in its metadata table"
        )
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if "python scripts/check_release_metadata.py" not in ci:
        raise ValueError("GitLab CI must execute the release and governance checker")
    if "publish-gitlab-release:" not in ci or "publish-gitlab-release.sh" not in ci:
        raise ValueError("GitLab CI must publish a formal provider-native release record")
    if "CI_COMMIT_BRANCH =~ /^release\\/" not in ci:
        raise ValueError("GitLab CI must suppress untagged release-preparation branches")
    operations = (ROOT / "docs" / "operations" / "forge-operations.md").read_text(encoding="utf-8")
    if "audit-dual-forge-parity.py --json" not in operations:
        raise ValueError("forge operations must document the read-only parity audit")
    for token in ("author", "committer", "every reachable commit", "Verified"):
        if token not in operations:
            raise ValueError(f"forge operations must document commit provenance: {token}")
    retired_paths = (
        "docs/history",
        "docs/reviews",
        "docs/specs",
        "docs/superpowers",
        "docs/design",
    )
    present = [path for path in retired_paths if (ROOT / path).exists()]
    if present:
        raise ValueError(
            "retired execution-document paths must not remain in the canonical tree: "
            + ", ".join(present)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="require an exact v<version> tag")
    parser.add_argument(
        "--allow-unpublished-history",
        action="store_true",
        help="allow a provider bootstrap branch with no locally native historical tags",
    )
    parser.add_argument(
        "--prepare-release",
        action="store_true",
        help="validate a signed-release commit before its provider-native tag exists",
    )
    parser.add_argument("--changelog", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_release and args.tag:
        raise SystemExit("--prepare-release cannot be combined with --tag")
    version = read_version()
    check_python_metadata()
    releases = changelog_releases(args.changelog)
    check_changelog_provenance(
        releases,
        allow_unpublished_history=args.allow_unpublished_history,
        pending_version=version if args.prepare_release else None,
    )
    if args.prepare_release:
        if version in known_release_versions():
            raise SystemExit(f"release tag v{version} already exists; use --tag validation instead")
        current_heading = f"## [{version}] - "
        heading = next((f"## [{item}] - {date}" for item, date in releases if item == version), "")
        if not heading.startswith(current_heading):
            raise SystemExit(
                f"CHANGELOG.md lacks pending release heading ## [{version}] - YYYY-MM-DD"
            )
        first_published = releases[0][0] if releases else ""
        if first_published != version:
            raise SystemExit(
                f"pending release {version} must be the first published CHANGELOG section"
            )
        try:
            check_pending_release_date(version, releases)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    try:
        check_active_release_train(
            version,
            releases,
            allow_unpublished_history=args.allow_unpublished_history,
            pending_release=args.prepare_release,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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
        subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/tags/{args.tag}"], cwd=ROOT, check=True
        )
        if version not in {released for released, _ in releases}:
            raise SystemExit(f"CHANGELOG.md lacks dated release heading ## [{version}]")
    print(f"release and governance metadata: {version} OK")


if __name__ == "__main__":
    main()
