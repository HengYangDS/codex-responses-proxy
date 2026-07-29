#!/usr/bin/env python3
"""Read-only GitHub Actions and Release evidence for one exact tag commit."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

DEFAULT_REQUIRED_JOBS: Final = (
    "Python 3.12",
    "Python 3.13",
    "Python 3.14",
    "Python 3.12 (Windows)",
    "Python 3.13 (Windows)",
    "Python 3.14 (Windows)",
    "Governance and presentation",
    "Python quality",
    "Verify tag and publish record",
)


class GitHubProofError(RuntimeError):
    """GitHub hosted evidence is missing, ambiguous, or mismatched."""


def normalize(
    *,
    repository: str,
    tag: str,
    commit_oid: str,
    runs: Sequence[Mapping[str, object]],
    jobs: Mapping[int, Sequence[Mapping[str, object]]],
    release: Mapping[str, object],
    required_jobs: Sequence[str] = DEFAULT_REQUIRED_JOBS,
) -> dict[str, object]:
    """Normalize exact successful Verify and Release workflow evidence."""

    selected: dict[str, Mapping[str, object]] = {}
    expected_paths = {
        "Verify": ".github/workflows/verify.yml",
        "Release": ".github/workflows/release.yml",
    }
    for name, path in expected_paths.items():
        matches = [
            run
            for run in runs
            if run.get("name") == name
            and run.get("path") == path
            and run.get("event") == "push"
            and run.get("head_branch") == tag
            and run.get("head_sha") == commit_oid
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ]
        if len(matches) != 1:
            raise GitHubProofError(f"GitHub {name} run is missing or ambiguous")
        selected[name] = matches[0]
    statuses: dict[str, str] = {}
    duplicate_jobs: set[str] = set()
    workflow_jobs = {
        "Verify": tuple(required_jobs[:-1]),
        "Release": tuple(required_jobs[-1:]),
    }
    for workflow, run in selected.items():
        run_id = run.get("id")
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            raise GitHubProofError("GitHub workflow run has no stable id")
        allowed = set(workflow_jobs[workflow])
        for job in jobs.get(run_id, ()):
            name = job.get("name")
            if not isinstance(name, str) or job.get("status") != "completed":
                continue
            if name in required_jobs and name not in allowed:
                raise GitHubProofError("GitHub required job belongs to the wrong workflow")
            if name in statuses:
                duplicate_jobs.add(name)
            statuses[name] = str(job.get("conclusion"))
    if duplicate_jobs.intersection(required_jobs):
        raise GitHubProofError("GitHub required job identity is ambiguous")
    if any(statuses.get(name) != "success" for name in required_jobs):
        raise GitHubProofError("GitHub required jobs are incomplete or unsuccessful")
    if (
        release.get("tag_name") != tag
        or release.get("name") != f"Codex DMX Proxy {tag}"
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise GitHubProofError("GitHub release identity does not match")
    return {
        "repository": repository,
        "ci": {
            "id": {name.lower(): selected[name]["id"] for name in ("Verify", "Release")},
            "revision_oid": commit_oid,
            "status": "success",
            "jobs": statuses,
        },
        "release": {
            "id": release.get("id"),
            "tag": tag,
            "commit_oid": commit_oid,
            "name": release["name"],
            "draft": False,
            "prerelease": False,
        },
    }


def collect(
    *,
    repository: str,
    tag: str,
    tag_object_oid: str,
    commit_oid: str,
    required_jobs: Sequence[str] = DEFAULT_REQUIRED_JOBS,
) -> dict[str, object]:
    """Query GitHub and bind API identity to independently fetched Git objects."""

    ref = _api(f"repos/{repository}/git/ref/tags/{tag}")
    if not isinstance(ref, dict):
        raise GitHubProofError("GitHub tag ref response is malformed")
    typed_ref = cast(Mapping[str, object], ref)
    ref_object = typed_ref.get("object")
    if not isinstance(ref_object, dict):
        raise GitHubProofError("GitHub tag ref object is unavailable")
    typed_ref_object = cast(Mapping[str, object], ref_object)
    if typed_ref_object.get("type") != "tag" or typed_ref_object.get("sha") != tag_object_oid:
        raise GitHubProofError("GitHub API tag object differs from fetched tag")
    tag_object = _api(f"repos/{repository}/git/tags/{tag_object_oid}")
    if not isinstance(tag_object, dict):
        raise GitHubProofError("GitHub tag object response is malformed")
    typed_tag_object = cast(Mapping[str, object], tag_object)
    target = typed_tag_object.get("object")
    if not isinstance(target, dict):
        raise GitHubProofError("GitHub tag target is unavailable")
    typed_target = cast(Mapping[str, object], target)
    if (
        typed_tag_object.get("tag") != tag
        or typed_tag_object.get("sha") != tag_object_oid
        or typed_target.get("type") != "commit"
        or typed_target.get("sha") != commit_oid
    ):
        raise GitHubProofError("GitHub tag identity does not match fetched Git objects")

    runs: list[Mapping[str, object]] = []
    for workflow in ("verify.yml", "release.yml"):
        run_pages = _api_pages(
            f"repos/{repository}/actions/workflows/{workflow}/runs?branch={tag}&event=push&per_page=100"
        )
        for page in run_pages:
            if not isinstance(page, dict):
                raise GitHubProofError("GitHub workflow response is malformed")
            typed_page = cast(Mapping[str, object], page)
            workflow_runs = typed_page.get("workflow_runs")
            if not isinstance(workflow_runs, list):
                raise GitHubProofError("GitHub workflow response is malformed")
            runs.extend(cast(list[Mapping[str, object]], workflow_runs))
    jobs: dict[int, Sequence[Mapping[str, object]]] = {}
    for run in runs:
        run_id = run.get("id")
        if isinstance(run_id, int) and not isinstance(run_id, bool):
            collected_jobs: list[Mapping[str, object]] = []
            for page in _api_pages(f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"):
                if not isinstance(page, dict):
                    raise GitHubProofError("GitHub jobs response is malformed")
                typed_page = cast(Mapping[str, object], page)
                page_jobs = typed_page.get("jobs")
                if not isinstance(page_jobs, list):
                    raise GitHubProofError("GitHub jobs response is malformed")
                collected_jobs.extend(cast(list[Mapping[str, object]], page_jobs))
            jobs[run_id] = collected_jobs
    release_pages = _api_pages(f"repos/{repository}/releases?per_page=100")
    releases: list[Mapping[str, object]] = []
    for page in release_pages:
        if not isinstance(page, list):
            raise GitHubProofError("GitHub release response is malformed")
        releases.extend(cast(list[Mapping[str, object]], page))
    matches = [release for release in releases if release.get("tag_name") == tag]
    if len(matches) != 1:
        raise GitHubProofError("GitHub release record is missing or ambiguous")
    typed_release = matches[0]
    return normalize(
        repository=repository,
        tag=tag,
        commit_oid=commit_oid,
        runs=runs,
        jobs=jobs,
        release=typed_release,
        required_jobs=required_jobs,
    )


def _api(endpoint: str) -> object:
    executable = _executable("gh")
    try:
        completed = subprocess.run(
            (executable, "api", "--method", "GET", endpoint),
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise GitHubProofError("GitHub API evidence is unavailable") from error


def _api_pages(endpoint: str) -> list[object]:
    executable = _executable("gh")
    try:
        completed = subprocess.run(
            (executable, "api", "--method", "GET", "--paginate", "--slurp", endpoint),
            check=True,
            capture_output=True,
            text=True,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise GitHubProofError("GitHub paginated API evidence is unavailable") from error
    if not isinstance(value, list):
        raise GitHubProofError("GitHub paginated API response is malformed")
    return value


def _executable(name: str) -> str:
    import shutil

    candidate = shutil.which(name)
    if not candidate:
        raise GitHubProofError(f"{name} is unavailable")
    return str(Path(candidate).resolve())
