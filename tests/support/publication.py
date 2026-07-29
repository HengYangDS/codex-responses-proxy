"""Test fixture that exercises the live publication authority minter boundary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest import mock

from codex_dmx_proxy.release import publication


VERIFY_ARGUMENTS = dict(
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


def verified_authority(evidence: Mapping[str, Any]) -> publication.PublishedRelease:
    """Mint test authority through ``publication.verify`` with offline Forge adapters."""

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

    with (
        mock.patch.object(publication.git, "collect", side_effect=collect_git),
        mock.patch.object(publication.gitlab, "collect", side_effect=collect_hosted),
        mock.patch.object(publication.github, "collect", side_effect=collect_hosted),
        mock.patch.object(
            publication.evaluator,
            "evaluate",
            side_effect=lambda tag, gitlab, github, policy: {
                "verified": True,
                "tree_equal": True,
                "forges": {"gitlab": gitlab, "github": github},
            },
        ),
        mock.patch.object(
            publication,
            "load_policy",
            return_value={"gitlab_jobs": ("required",), "github_jobs": ("required",)},
        ),
    ):
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
