#!/usr/bin/env python3
"""Read-only GitLab pipeline and Release evidence for one exact tag commit."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

DEFAULT_REQUIRED_JOBS: Final = (
    "verify-python-3.12",
    "verify-python-3.13",
    "verify-python-3.14",
    "verify-release-metadata",
    "verify-release-tag",
    "verify-python-quality",
    "publish-gitlab-release",
)


class GitLabProofError(RuntimeError):
    """GitLab hosted evidence is missing, ambiguous, or mismatched."""


def normalize(
    *,
    repository: str,
    tag: str,
    commit_oid: str,
    pipeline: Mapping[str, object],
    jobs: Sequence[Mapping[str, object]],
    release: Mapping[str, object],
    required_jobs: Sequence[str] = DEFAULT_REQUIRED_JOBS,
) -> dict[str, object]:
    """Normalize one exact successful tag pipeline and release record."""

    if not (
        pipeline.get("sha") == commit_oid
        and pipeline.get("ref") == tag
        and pipeline.get("tag") is True
        and pipeline.get("source") == "push"
        and pipeline.get("status") == "success"
        and pipeline.get("yaml_errors") in (None, "")
    ):
        raise GitLabProofError("GitLab tag pipeline identity does not match")
    statuses: dict[str, str] = {}
    duplicate_jobs: set[str] = set()
    for job in jobs:
        name = job.get("name")
        if not isinstance(name, str):
            continue
        if name not in required_jobs:
            continue
        if job.get("allow_failure") is not False:
            raise GitLabProofError("GitLab required job permits failure")
        nested_pipeline = job.get("pipeline")
        commit = job.get("commit")
        if (
            job.get("ref") != tag
            or job.get("tag") is not True
            or not isinstance(nested_pipeline, Mapping)
            or nested_pipeline.get("id") != pipeline.get("id")
            or nested_pipeline.get("sha") != commit_oid
            or nested_pipeline.get("ref") != tag
            or nested_pipeline.get("source") != "push"
            or not isinstance(commit, Mapping)
            or commit.get("id") != commit_oid
        ):
            raise GitLabProofError("GitLab required job identity does not match the tag pipeline")
        if name in statuses:
            duplicate_jobs.add(name)
        statuses[name] = str(job.get("status"))
    if duplicate_jobs:
        raise GitLabProofError("GitLab required job identity is ambiguous")
    if any(statuses.get(name) != "success" for name in required_jobs):
        raise GitLabProofError("GitLab required jobs are incomplete or unsuccessful")
    release_commit = release.get("commit")
    if not isinstance(release_commit, Mapping):
        raise GitLabProofError("GitLab release commit is unavailable")
    typed_release_commit = cast(Mapping[str, object], release_commit)
    if (
        release.get("tag_name") != tag
        or release.get("name") != f"Codex DMX Proxy {tag}"
        or typed_release_commit.get("id") != commit_oid
        or release.get("upcoming_release") is not False
    ):
        raise GitLabProofError("GitLab release identity does not match")
    evidences = release.get("evidences")
    if not isinstance(evidences, list) or len(evidences) != 1:
        raise GitLabProofError("GitLab release evidence identity is unavailable")
    evidence = evidences[0]
    if not isinstance(evidence, dict):
        raise GitLabProofError("GitLab release evidence identity is unavailable")
    typed_evidence = cast(Mapping[str, object], evidence)
    if not isinstance(typed_evidence.get("sha"), str):
        raise GitLabProofError("GitLab release evidence identity is unavailable")
    return {
        "repository": repository,
        "ci": {
            "id": pipeline.get("id"),
            "revision_oid": commit_oid,
            "status": "success",
            "jobs": statuses,
        },
        "release": {
            "id": typed_evidence["sha"],
            "tag": tag,
            "commit_oid": commit_oid,
            "name": release["name"],
            "draft": False,
            "prerelease": False,
        },
    }


def collect(
    *,
    api_base: str,
    repository: str,
    tag: str,
    tag_object_oid: str,
    commit_oid: str,
    required_jobs: Sequence[str] = DEFAULT_REQUIRED_JOBS,
) -> dict[str, object]:
    """Query GitLab through authenticated read-only API calls."""

    base = api_base.rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise GitLabProofError("GitLab API base must be HTTP(S)")
    project = urllib.parse.quote(repository, safe="")
    encoded_tag = urllib.parse.quote(tag, safe="")
    tag_record = _api(f"{base}/projects/{project}/repository/tags/{encoded_tag}")
    if not isinstance(tag_record, dict):
        raise GitLabProofError("GitLab API tag object differs from fetched tag")
    typed_tag_record = cast(Mapping[str, object], tag_record)
    if typed_tag_record.get("target") != tag_object_oid:
        raise GitLabProofError("GitLab API tag object differs from fetched tag")
    commit = typed_tag_record.get("commit")
    if not isinstance(commit, Mapping):
        raise GitLabProofError("GitLab API tag commit differs from fetched tag")
    typed_commit = cast(Mapping[str, object], commit)
    if typed_commit.get("id") != commit_oid:
        raise GitLabProofError("GitLab API tag commit differs from fetched tag")
    pipelines = _api_pages(
        f"{base}/projects/{project}/pipelines?ref={encoded_tag}&sha={commit_oid}&source=push&per_page=100"
    )
    matches: list[Mapping[str, object]] = []
    for item in pipelines:
        if not isinstance(item, Mapping):
            continue
        typed_item = cast(Mapping[str, object], item)
        if (
            typed_item.get("ref") == tag
            and typed_item.get("sha") == commit_oid
            and typed_item.get("source") == "push"
            and typed_item.get("status") == "success"
        ):
            matches.append(typed_item)
    if len(matches) != 1:
        raise GitLabProofError("GitLab successful tag pipeline is missing or ambiguous")
    listed_pipeline = matches[0]
    listed_id = listed_pipeline.get("id")
    if isinstance(listed_id, bool) or not isinstance(listed_id, int):
        raise GitLabProofError("GitLab pipeline has no stable id")
    detail = _api(f"{base}/projects/{project}/pipelines/{listed_id}")
    if not isinstance(detail, dict):
        raise GitLabProofError("GitLab tag pipeline detail is malformed")
    pipeline = cast(Mapping[str, object], detail)
    pipeline_id = pipeline.get("id")
    if isinstance(pipeline_id, bool) or not isinstance(pipeline_id, int):
        raise GitLabProofError("GitLab pipeline has no stable id")
    jobs = _api_pages(
        f"{base}/projects/{project}/pipelines/{pipeline_id}/jobs?per_page=100&include_retried=false"
    )
    releases = _api_pages(f"{base}/projects/{project}/releases?per_page=100")
    release_matches: list[Mapping[str, object]] = []
    for item in releases:
        if isinstance(item, Mapping) and item.get("tag_name") == tag:
            release_matches.append(cast(Mapping[str, object], item))
    if len(release_matches) != 1:
        raise GitLabProofError("GitLab release record is missing or ambiguous")
    release = release_matches[0]
    if not isinstance(jobs, list) or not isinstance(release, Mapping):
        raise GitLabProofError("GitLab hosted evidence is malformed")
    return normalize(
        repository=repository,
        tag=tag,
        commit_oid=commit_oid,
        pipeline=pipeline,
        jobs=cast(list[Mapping[str, object]], jobs),
        release=release,
        required_jobs=required_jobs,
    )


def _api(endpoint: str) -> object:
    executable = _executable("glab")
    try:
        completed = subprocess.run(
            (executable, "api", "--method", "GET", endpoint),
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise GitLabProofError("GitLab API evidence is unavailable") from error


def _api_pages(endpoint: str) -> list[object]:
    executable = _executable("glab")
    try:
        completed = subprocess.run(
            (executable, "api", "--method", "GET", "--paginate", "--output", "ndjson", endpoint),
            check=True,
            capture_output=True,
            text=True,
        )
        pages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise GitLabProofError("GitLab paginated API evidence is unavailable") from error
    items: list[object] = []
    for page in pages:
        if isinstance(page, list):
            items.extend(page)
        elif isinstance(page, dict):
            items.append(page)
        else:
            raise GitLabProofError("GitLab paginated API response is malformed")
    return items


def _executable(name: str) -> str:
    import shutil

    candidate = shutil.which(name)
    if not candidate:
        raise GitLabProofError(f"{name} is unavailable")
    return str(Path(candidate).resolve())
