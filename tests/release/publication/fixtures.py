"""Test fixture that exercises live dual-Forge publication evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

from tools.release import product_assets
from tools.release.publication import verification as publication


class VerifyArguments(TypedDict):
    """Exact keyword contract for the publication verifier."""

    tag: str
    gitlab_git_url: str
    gitlab_api_base: str
    gitlab_repo: str
    github_git_url: str
    github_repo: str
    gitlab_anchor: Path
    github_anchor: Path


VERIFY_ARGUMENTS: VerifyArguments = {
    "tag": "v1.2.3",
    "gitlab_git_url": "https://gitlab.example/team/repository.git",
    "gitlab_api_base": "https://gitlab.example/api/v4",
    "gitlab_repo": "gitlab/repository",
    "github_git_url": "https://github.example/team/repository.git",
    "github_repo": "github/repository",
    "gitlab_anchor": Path("gitlab-anchor"),
    "github_anchor": Path("github-anchor"),
}


def forge_evidence(*, items: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Return minimal matching dual-Forge evidence for authority tests."""
    identity: dict[str, object] = {
        "tag_object_oid": "a" * 40,
        "commit_oid": "b" * 40,
        "tree_oid": "c" * 40,
        "assets": {
            **{
                f"codex-responses-proxy-1.2.3-{platform}.tar.gz": "1" * 64
                for platform in ("linux-x86_64", "macos-arm64", "windows-x86_64")
            },
            **{
                f"codex-responses-proxy-{platform}.manifest.json": "2" * 64
                for platform in ("linux-x86_64", "macos-arm64", "windows-x86_64")
            },
            "SHA256SUMS": "3" * 64,
            "SHA256SUMS.sig": "4" * 64,
        },
    }
    if items is not None:
        identity["items"] = items
    return {
        "verified": True,
        "tag": "v1.2.3",
        "forges": {
            provider: {"provider": provider, **identity} for provider in ("gitlab", "github")
        },
    }


def verified_evidence(evidence: Mapping[str, object], *, mocker) -> Mapping[str, object]:
    """Run ``publication.verify`` with offline Forge adapters."""

    forges = evidence["forges"]
    assert isinstance(forges, Mapping)
    assert all(isinstance(key, str) for key in forges)
    forge_map = {str(key): value for key, value in forges.items()}

    def collect_git(*, provider: str, **_: object) -> Mapping[str, object]:
        forge = forge_map[provider]
        assert isinstance(forge, Mapping)
        assert all(isinstance(key, str) for key in forge)
        return {str(key): value for key, value in forge.items()}

    def collect_hosted(*, repository: str, **_: object) -> Mapping[str, object]:
        provider = "github" if repository == "github/repository" else "gitlab"
        forge = forge_map[provider]
        assert isinstance(forge, Mapping)
        assert all(isinstance(key, str) for key in forge)
        commit = forge["commit_oid"]
        hosted: dict[str, object] = {
            "repository": repository,
            "ci": {
                "id": 42,
                "revision_oid": commit,
                "status": "success",
                "jobs": {"required": "success"},
            },
            "release": {
                "id": 99,
                "tag": evidence["tag"],
                "commit_oid": commit,
                "name": "Codex Responses Proxy v1.2.3",
                "draft": False,
                "prerelease": False,
            },
            "assets": forge["assets"],
        }
        if "items" in forge:
            hosted["items"] = forge["items"]
        return hosted

    mocker.patch.object(publication.git, "collect", side_effect=collect_git)
    mocker.patch.object(publication.gitlab, "collect", side_effect=collect_hosted)
    mocker.patch.object(publication.github, "collect", side_effect=collect_hosted)
    mocker.patch.object(
        publication.evaluator,
        "evaluate",
        side_effect=lambda _tag, gitlab, github: {
            "verified": True,
            "tree_equal": True,
            "assets_equal": True,
            "forges": {"gitlab": gitlab, "github": github},
        },
    )
    return publication.verify(
        tag=str(evidence["tag"]),
        gitlab_git_url="https://gitlab.example/team/repository.git",
        gitlab_api_base="https://gitlab.example/api/v4",
        gitlab_repo="gitlab/repository",
        github_git_url="https://github.example/team/repository.git",
        github_repo="github/repository",
        gitlab_anchor=Path("gitlab-anchor"),
        github_anchor=Path("github-anchor"),
    )


def release_bundle(
    platforms: tuple[str, ...] = product_assets.RELEASE_PLATFORMS,
) -> dict[str, bytes]:
    version = "1.2.3"
    platform_assets: dict[str, bytes] = {}
    for platform in platforms:
        executable = (
            "codex-responses-proxy.exe"
            if platform.startswith("windows-")
            else "codex-responses-proxy"
        )
        files = {
            f"bin/{executable}": product_assets.ArchiveFile(
                f"native-{platform}".encode(), mode=0o755
            )
        }
        archive_name = product_assets.archive_name(version, platform)
        archive = product_assets.archive_bytes(files, version, platform)
        platform_assets[archive_name] = archive
        platform_assets[product_assets.manifest_name(platform)] = product_assets.asset_manifest(
            version=version,
            platform=platform,
            archive_name=archive_name,
            archive=archive,
            files=files,
        )
    unsigned = {
        **platform_assets,
        product_assets.CHECKSUM_NAME: product_assets.checksums(platform_assets),
    }
    return {**unsigned, product_assets.SIGNATURE_NAME: b"fixture-signature\n"}
