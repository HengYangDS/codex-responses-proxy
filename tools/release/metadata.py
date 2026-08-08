#!/usr/bin/env python3
"""Verify release identity, changelog provenance, and governance contracts."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter


ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_HEADING = re.compile(
    r"^## \[(?P<version>Unreleased|(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$"
)
PROVIDERS = frozenset({"gitlab", "github"})


def read_version() -> str:
    """Return the repository release version after strict SemVer validation."""

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise ValueError(f"VERSION is not a release SemVer: {version!r}")
    return version


def check_python_metadata() -> None:
    """Keep Python support metadata aligned without duplicating release ownership."""

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata.get("project", {})
    if project.get("requires-python") != ">=3.12":
        raise ValueError("pyproject.toml must require Python >=3.12 without an upper bound")
    if project.get("dynamic") != ["version"]:
        raise ValueError("pyproject.toml must keep VERSION as the sole version owner")
    hatch_version = metadata.get("tool", {}).get("hatch", {}).get("version", {})
    if hatch_version.get("path") != "VERSION":
        raise ValueError("pyproject.toml must read package version from VERSION")
    if metadata.get("tool", {}).get("codex-responses-proxy", {}).get("distribution") != (
        "native-executable"
    ):
        raise ValueError("the product distribution must be the native executable")


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def known_release_versions() -> list[str]:
    """Return this checkout's provider-native tags in descending SemVer order."""

    tags = _git("tag", "--list", "v[0-9]*", "--sort=-version:refname").splitlines()
    return [
        tag.removeprefix("v")
        for tag in sorted(
            tags, key=lambda value: _version_key(value.removeprefix("v")), reverse=True
        )
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


def check_provider(provider: str) -> None:
    """Reject programmatic callers that bypass the command grammar."""

    if provider not in PROVIDERS:
        raise ValueError(f"unsupported release provider: {provider!r}")


def check_changelog_provenance(
    releases: list[tuple[str, str]],
    *,
    provider: str = "gitlab",
    pending_version: str | None = None,
) -> None:
    """Validate one provider's native tags against the shared Changelog."""

    check_provider(provider)
    actual_versions = [version for version, _ in releases]
    expected_versions = known_release_versions()
    if len(actual_versions) != len(set(actual_versions)):
        raise ValueError("released CHANGELOG headings must not duplicate a version")
    missing_headings = [version for version in expected_versions if version not in actual_versions]
    if missing_headings:
        raise ValueError(
            "locally available release tags must appear once in CHANGELOG.md: "
            + ", ".join(missing_headings)
        )
    if pending_version in expected_versions:
        raise ValueError(f"release tag v{pending_version} already exists")


def check_active_release_train(
    version: str,
    releases: list[tuple[str, str]],
    *,
    provider: str = "gitlab",
    pending_release: bool = False,
) -> None:
    """Accept an untagged next version without treating it as published.

    A deployed source tree may contain several ordinary commits between releases.
    The active ``VERSION`` names that next release train, while the dated
    Changelog headings remain an immutable record of tags that already exist.
    """
    check_provider(provider)
    known = known_release_versions()
    published = {released for released, _ in releases}
    if version in known:
        if version not in published:
            raise ValueError(f"CHANGELOG.md lacks dated release heading ## [{version}]")
        return
    if version in published:
        latest_heading = releases[0][0] if releases else ""
        if (
            pending_release
            or version == latest_heading
            and (not known or _version_key(version) > max(map(_version_key, known)))
        ):
            return
        raise ValueError(f"CHANGELOG release {version} exists before its Git tag")
    comparison_set = known + [released for released, _ in releases]
    if not comparison_set:
        raise ValueError("cannot identify an existing release version")
    if _version_key(version) <= max(map(_version_key, comparison_set)):
        raise ValueError(
            f"untagged VERSION {version} must be newer than the latest released version"
        )


def check_release_tag(tag: str, version: str) -> None:
    """Bind an exact annotated tag directly to the ``HEAD`` commit."""

    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"tag {tag!r} does not match expected {expected!r}")
    reference = f"refs/tags/{tag}"
    try:
        object_type = _git("cat-file", "-t", reference)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"release tag {tag!r} does not exist") from exc
    if object_type != "tag":
        raise ValueError(f"release tag {tag!r} must be an annotated tag object")
    headers = _git("cat-file", "tag", reference).split("\n\n", 1)[0].splitlines()
    embedded_name = next(
        (line.removeprefix("tag ") for line in headers if line.startswith("tag ")), ""
    )
    if embedded_name != tag:
        raise ValueError(f"release tag {tag!r} embeds tag name {embedded_name!r}, expected {tag!r}")
    target_type = next(
        (line.removeprefix("type ") for line in headers if line.startswith("type ")), ""
    )
    if target_type != "commit":
        raise ValueError(f"release tag {tag!r} must directly name a commit")
    tag_commit = next(
        (line.removeprefix("object ") for line in headers if line.startswith("object ")), ""
    )
    head_commit = _git("rev-parse", "HEAD^{commit}")
    if tag_commit != head_commit:
        raise ValueError(
            f"release tag {tag!r} directly names commit {tag_commit}, not HEAD commit {head_commit}"
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
        "docs/decisions/README.md",
        "docs/decisions/dr-0001-control-plane-data-plane-boundary.md",
        "docs/evidence/README.md",
        "docs/operations/forge-operations.md",
        "LICENSE",
        "tools/forge/project.sh",
        "tools/forge/context.sh",
        "tools/forge/audit.py",
        "tools/release/tag-gitlab.sh",
        "tools/release/tag-github.sh",
        "tools/forge/check-tag-signature.sh",
        "tools/release/publish-gitlab.sh",
        "tools/reliability/observe.py",
        ".github/workflows/verify.yml",
        ".github/workflows/release.yml",
    )
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    if missing:
        raise ValueError("missing governance documents: " + ", ".join(missing))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.startswith("# Codex Responses Proxy\n"):
        raise ValueError("README.md must use the formal Project Name as its title")
    identity_statement = (
        "Licensed under [MIT](LICENSE). Forge coordinates and publication actors are\n"
        "deployment context, not product identity."
    )
    if identity_statement not in readme:
        raise ValueError("README.md must separate product identity from Forge deployment context")
    ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    if "python tools/release/metadata.py" not in ci:
        raise ValueError("GitLab CI must execute the release and governance checker")
    if "publish-gitlab-release:" not in ci or "tools/release/publish-gitlab.sh" not in ci:
        raise ValueError("GitLab CI must publish a formal provider-native release record")
    if "CI_COMMIT_BRANCH =~ /^release\\/" not in ci:
        raise ValueError("GitLab CI must suppress untagged release-preparation branches")
    operations = (ROOT / "docs" / "operations" / "forge-operations.md").read_text(encoding="utf-8")
    if "tools/forge/audit.py" not in operations or "--json" not in operations:
        raise ValueError("forge operations must document the read-only parity audit")
    for token in (
        "CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS",
        "CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS",
        "may admit multiple authorized",
        "provider-specific commit identities",
        "forward-only",
        "fast-forward",
    ):
        if token not in operations:
            raise ValueError(f"forge operations must document provider commit trust: {token}")
    for token in ("commit-author-name", "commit-author-email"):
        if token in operations:
            raise ValueError(f"forge operations couple shared history to one actor: {token}")


def _command(
    *,
    tag: Annotated[str | None, Parameter(help="Require an exact v<version> tag.")] = None,
    provider: Annotated[
        str,
        Parameter(help="Select the provider-native tag plane used for validation."),
    ] = "gitlab",
    prepare_release: Annotated[
        bool,
        Parameter(help="Validate a release commit before its provider-native tag exists."),
    ] = False,
    changelog: Annotated[Path | None, Parameter(show=False)] = None,
) -> None:
    """Validate release identity and repository governance."""

    if prepare_release and tag:
        raise SystemExit("--prepare-release cannot be combined with --tag")
    version = read_version()
    check_python_metadata()
    releases = changelog_releases(changelog)
    check_changelog_provenance(
        releases,
        provider=provider,
        pending_version=version if prepare_release else None,
    )
    if prepare_release:
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
            provider=provider,
            pending_release=prepare_release,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    proxy = (ROOT / "src" / "codex_responses_proxy" / "service" / "entrypoint.py").read_text(
        encoding="utf-8"
    )
    if "release_version()" not in proxy:
        raise SystemExit("proxy runtime header does not read VERSION")
    try:
        check_governance_contract()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if tag:
        try:
            check_release_tag(tag, version)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if version not in {released for released, _ in releases}:
            raise SystemExit(f"CHANGELOG.md lacks dated release heading ## [{version}]")
    print(f"release and governance metadata: {version} OK")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run release validation through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
