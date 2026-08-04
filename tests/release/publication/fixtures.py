"""Test fixture that exercises live dual-Forge publication evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from tools.release.publication import verification as publication


class VerifyArguments(TypedDict):
    """Exact keyword contract for the publication verifier."""

    tag: str
    gitlab_remote: str
    gitlab_api_base: str
    gitlab_repo: str
    github_remote: str
    github_repo: str
    gitlab_anchor: Path
    github_anchor: Path
    policy_path: Path


VERIFY_ARGUMENTS: VerifyArguments = dict(
    tag="v1.2.3",
    gitlab_remote="gitlab-remote",
    gitlab_api_base="https://gitlab.example/api/v4",
    gitlab_repo="gitlab/repository",
    github_remote="github-remote",
    github_repo="github/repository",
    gitlab_anchor=Path("gitlab-anchor"),
    github_anchor=Path("github-anchor"),
    policy_path=Path("publication-policy.toml"),
)


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


def verified_evidence(evidence: Mapping[str, Any], *, mocker) -> Mapping[str, Any]:
    """Run ``publication.verify`` with offline Forge adapters."""

    forges = evidence["forges"]
    assert isinstance(forges, Mapping)

    def collect_git(*, provider: str, **_: object) -> Mapping[str, Any]:
        forge = forges[provider]
        assert isinstance(forge, Mapping)
        return forge

    def collect_hosted(*, repository: str, **_: object) -> Mapping[str, Any]:
        provider = "github" if repository == "github/repository" else "gitlab"
        forge = forges[provider]
        assert isinstance(forge, Mapping)
        return forge

    mocker.patch.object(publication.git, "collect", side_effect=collect_git)
    mocker.patch.object(publication.gitlab, "collect", side_effect=collect_hosted)
    mocker.patch.object(publication.github, "collect", side_effect=collect_hosted)
    mocker.patch.object(
        publication.evaluator,
        "evaluate",
        side_effect=lambda tag, gitlab, github, policy: {
            "verified": True,
            "tree_equal": True,
            "assets_equal": True,
            "forges": {"gitlab": gitlab, "github": github},
        },
    )
    mocker.patch.object(
        publication,
        "load_policy",
        return_value={"gitlab_jobs": ("required",), "github_jobs": ("required",)},
    )
    return publication.verify(
        tag=str(evidence["tag"]),
        gitlab_remote="gitlab-remote",
        gitlab_api_base="https://gitlab.example/api/v4",
        gitlab_repo="gitlab/repository",
        github_remote="github-remote",
        github_repo="github/repository",
        gitlab_anchor=Path("gitlab-anchor"),
        github_anchor=Path("github-anchor"),
        policy_path=Path("publication-policy.toml"),
    )
