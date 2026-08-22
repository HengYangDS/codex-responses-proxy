"""Live dual-Forge publication verification.

The evaluator and provider adapters produce immutable, secret-free evidence for
release governance.  Installation has a separate signed-source trust boundary
and never consumes this evidence as authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from codex_responses_proxy.service import digest
from tools.release import identity
from tools.release.publication import evaluator
from tools.release.publication import git
from tools.release.publication import github
from tools.release.publication import gitlab


class PublicationError(RuntimeError):
    """Report unavailable, ambiguous, or mismatched publication evidence."""


def verify(
    *,
    tag: str,
    gitlab_remote: str,
    gitlab_api_base: str,
    gitlab_repo: str,
    github_remote: str,
    github_repo: str,
    gitlab_anchor: Path,
    github_anchor: Path,
) -> Mapping[str, object]:
    """Return immutable evidence for exact signed releases on both Forges."""
    if not identity.is_tag(tag):
        raise PublicationError("publication tag must be exact vMAJOR.MINOR.PATCH")
    try:
        gitlab_git = git.collect(
            provider="gitlab", remote=gitlab_remote, tag=tag, anchor=gitlab_anchor
        )
        github_git = git.collect(
            provider="github", remote=github_remote, tag=tag, anchor=github_anchor
        )
        gitlab_hosted = gitlab.collect(
            api_base=gitlab_api_base,
            repository=gitlab_repo,
            tag=tag,
            tag_object_oid=str(gitlab_git["tag_object_oid"]),
            commit_oid=str(gitlab_git["commit_oid"]),
        )
        github_hosted = github.collect(
            repository=github_repo,
            tag=tag,
            tag_object_oid=str(github_git["tag_object_oid"]),
            commit_oid=str(github_git["commit_oid"]),
        )
        gitlab_assets = gitlab_hosted.get("assets")
        github_assets = github_hosted.get("assets")
        result = evaluator.evaluate(
            tag,
            {**gitlab_git, **gitlab_hosted, "assets": gitlab_assets},
            {**github_git, **github_hosted, "assets": github_assets},
        )
    except (
        git.GitProofError,
        gitlab.GitLabProofError,
        github.GitHubProofError,
        ValueError,
        KeyError,
        OSError,
    ) as error:
        raise PublicationError("live publication evidence is unavailable or invalid") from error
    if result.get("verified") is not True:
        raise PublicationError("dual-Forge publication proof did not verify")
    forges = result.get("forges")
    if not isinstance(forges, Mapping):
        raise PublicationError("verified publication evidence is malformed")
    if result.get("assets_equal") is not True:
        raise PublicationError("dual-Forge release assets differ")
    return digest.freeze_mapping(
        {
            "schema_version": 1,
            "tag": tag,
            "verified": True,
            "tree_equal": True,
            "assets_equal": True,
            "forges": dict(forges),
        }
    )
