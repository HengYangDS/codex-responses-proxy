"""Live dual-Forge publication verification.

The evaluator and provider adapters produce immutable, secret-free evidence for
release governance.  Installation has a separate signed-source trust boundary
and never consumes this evidence as authority.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codex_responses_proxy.service import digest
from tools.release.publication import evaluator
from tools.release.publication import git
from tools.release.publication import github
from tools.release.publication import gitlab

_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


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
    policy_path: Path,
) -> Mapping[str, Any]:
    """Return immutable evidence for exact signed releases on both Forges."""

    if _TAG.fullmatch(tag) is None:
        raise PublicationError("publication tag must be exact vMAJOR.MINOR.PATCH")
    policy = load_policy(policy_path)
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
            required_jobs=policy["gitlab_jobs"],
        )
        github_hosted = github.collect(
            repository=github_repo,
            tag=tag,
            tag_object_oid=str(github_git["tag_object_oid"]),
            commit_oid=str(github_git["commit_oid"]),
            required_jobs=policy["github_jobs"],
        )
        gitlab_assets = gitlab_hosted.get("assets")
        github_assets = github_hosted.get("assets")
        result = evaluator.evaluate(
            tag,
            {**gitlab_git, **gitlab_hosted, "assets": gitlab_assets},
            {**github_git, **github_hosted, "assets": github_assets},
            policy,
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


def load_policy(path: Path) -> evaluator.PublicationPolicy:
    """Load the single repository-owned required-job policy fail closed."""

    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        if value.get("schema-version") != 1:
            raise ValueError("unsupported publication policy schema")
        gitlab = tuple(value["gitlab"]["required-jobs"])
        github = tuple(value["github"]["required-jobs"])
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        raise PublicationError("publication policy is unavailable or invalid") from error
    for provider, jobs in (("gitlab", gitlab), ("github", github)):
        if (
            not jobs
            or len(set(jobs)) != len(jobs)
            or any(not isinstance(job, str) or not job for job in jobs)
        ):
            raise PublicationError(f"{provider} publication jobs must be unique and nonempty")
    return {"gitlab_jobs": gitlab, "github_jobs": github}
