"""Test fixture that exercises the live publication authority minter boundary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from platform_adapters import publication


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

    modules = {
        "publication_proof_git": SimpleNamespace(GitProofError=RuntimeError, collect=collect_git),
        "publication_proof_gitlab": SimpleNamespace(
            GitLabProofError=RuntimeError,
            collect=collect_hosted,
        ),
        "publication_proof_github": SimpleNamespace(
            GitHubProofError=RuntimeError,
            collect=collect_hosted,
        ),
        "publication_proof": SimpleNamespace(
            evaluate=lambda tag, gitlab, github, policy: {
                "verified": True,
                "tree_equal": True,
                "forges": {"gitlab": gitlab, "github": github},
            }
        ),
    }
    with (
        mock.patch.object(publication, "_script_module", side_effect=modules.__getitem__),
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
