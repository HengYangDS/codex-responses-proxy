"""Read-only GitHub Actions and Release evidence for one exact tag commit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from codex_responses_proxy.release.publication import hosted
from codex_responses_proxy.release import assets as release_assets

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


def _mapping(value: object, unavailable: str) -> Mapping[str, object]:
    """Require one mapping-shaped GitHub API object."""

    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise GitHubProofError(unavailable)
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _mappings(value: object, malformed: str) -> list[Mapping[str, object]]:
    """Require a JSON array containing only object records."""

    if not isinstance(value, list):
        raise GitHubProofError(malformed)
    return [_mapping(item, malformed) for item in value]


def _one(records: Sequence[Mapping[str, object]], message: str) -> Mapping[str, object]:
    """Require one unambiguous GitHub record."""

    if len(records) != 1:
        raise GitHubProofError(message)
    return records[0]


def _object_pages(endpoint: str, key: str, malformed: str) -> list[Mapping[str, object]]:
    """Flatten paginated object records after validating every envelope."""

    records: list[Mapping[str, object]] = []
    for page in _api_pages(endpoint):
        items = _mapping(page, malformed).get(key)
        records.extend(_mappings(items, malformed))
    return records


def normalize(
    *,
    repository: str,
    tag: str,
    commit_oid: str,
    runs: Sequence[Mapping[str, object]],
    jobs: Mapping[int, Sequence[Mapping[str, object]]],
    release: Mapping[str, object],
    assets: Mapping[str, bytes],
    required_jobs: Sequence[str] = DEFAULT_REQUIRED_JOBS,
) -> dict[str, object]:
    """Normalize exact successful Verify and Release workflow evidence."""

    workflows = (
        ("Verify", ".github/workflows/verify.yml", set(required_jobs[:-1])),
        ("Release", ".github/workflows/release.yml", set(required_jobs[-1:])),
    )
    selected: dict[str, Mapping[str, object]] = {}
    statuses: dict[str, str] = {}
    for workflow, path, allowed_jobs in workflows:
        tagged_runs = [
            run for run in runs if run.get("path") == path and run.get("head_branch") == tag
        ]
        run = _one(tagged_runs, f"GitHub {workflow} run is missing or ambiguous")
        if (
            run.get("name"),
            run.get("event"),
            run.get("head_sha"),
            run.get("status"),
            run.get("conclusion"),
        ) != (workflow, "push", commit_oid, "completed", "success"):
            raise GitHubProofError(f"GitHub {workflow} run identity does not match")
        run_id = run.get("id")
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            raise GitHubProofError("GitHub workflow run has no stable id")
        selected[workflow] = run
        for job in jobs.get(run_id, ()):
            name = job.get("name")
            if not isinstance(name, str) or name not in required_jobs:
                continue
            if name not in allowed_jobs:
                raise GitHubProofError("GitHub required job belongs to the wrong workflow")
            if name in statuses:
                raise GitHubProofError("GitHub required job identity is ambiguous")
            statuses[name] = (
                str(job.get("conclusion")) if job.get("status") == "completed" else "incomplete"
            )
    if any(statuses.get(name) != "success" for name in required_jobs):
        raise GitHubProofError("GitHub required jobs are incomplete or unsuccessful")
    release_id = release.get("id")
    published_at = release.get("published_at")
    if not all(
        (
            isinstance(release_id, int) and not isinstance(release_id, bool),
            release.get("tag_name") == tag,
            release.get("name") == f"Codex Responses Proxy {tag}",
            release.get("draft") is False,
            release.get("prerelease") is False,
            isinstance(published_at, str) and bool(published_at),
        )
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
            "id": release_id,
            "tag": tag,
            "commit_oid": commit_oid,
            "name": release["name"],
            "draft": False,
            "prerelease": False,
        },
        "assets": release_assets.release_digests(assets, tag.removeprefix("v")),
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

    ref = _mapping(
        _api(f"repos/{repository}/git/ref/tags/{tag}"),
        "GitHub tag ref response is malformed",
    )
    ref_object = _mapping(ref.get("object"), "GitHub tag ref object is unavailable")
    if (ref.get("ref"), ref_object.get("type"), ref_object.get("sha")) != (
        f"refs/tags/{tag}",
        "tag",
        tag_object_oid,
    ):
        raise GitHubProofError("GitHub API tag object differs from fetched tag")
    tag_object = _mapping(
        _api(f"repos/{repository}/git/tags/{tag_object_oid}"),
        "GitHub tag object response is malformed",
    )
    target = _mapping(tag_object.get("object"), "GitHub tag target is unavailable")
    if (
        tag_object.get("tag"),
        tag_object.get("sha"),
        target.get("type"),
        target.get("sha"),
    ) != (tag, tag_object_oid, "commit", commit_oid):
        raise GitHubProofError("GitHub tag identity does not match fetched Git objects")

    runs = [
        run
        for workflow in ("verify.yml", "release.yml")
        for run in _object_pages(
            f"repos/{repository}/actions/workflows/{workflow}/runs?branch={tag}&per_page=100",
            "workflow_runs",
            "GitHub workflow response is malformed",
        )
    ]
    jobs = {
        run_id: _object_pages(
            f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
            "jobs",
            "GitHub jobs response is malformed",
        )
        for run in runs
        if isinstance(run_id := run.get("id"), int) and not isinstance(run_id, bool)
    }
    malformed = "GitHub release response is malformed"
    releases = [
        release
        for page in _api_pages(f"repos/{repository}/releases?per_page=100")
        for release in _mappings(page, malformed)
    ]
    matches = [release for release in releases if release.get("tag_name") == tag]
    typed_release = _one(matches, "GitHub release record is missing or ambiguous")
    asset_records = _mappings(typed_release.get("assets"), "GitHub release assets are malformed")
    expected_names = {
        release_assets.ARCHIVE_NAME.format(version=tag.removeprefix("v")),
        release_assets.CHECKSUM_NAME,
    }
    selected_assets = {
        str(record.get("name")): hosted.api_bytes(
            (
                hosted.executable("gh", GitHubProofError),
                "api",
                "--method",
                "GET",
                "-H",
                "Accept: application/octet-stream",
                str(record.get("url")),
            ),
            unavailable="GitHub release asset is unavailable",
            error_type=GitHubProofError,
        )
        for record in asset_records
        if record.get("name") in expected_names and isinstance(record.get("url"), str)
    }
    if set(selected_assets) != expected_names:
        raise GitHubProofError("GitHub release asset set is incomplete or ambiguous")
    return normalize(
        repository=repository,
        tag=tag,
        commit_oid=commit_oid,
        runs=runs,
        jobs=jobs,
        release=typed_release,
        assets=selected_assets,
        required_jobs=required_jobs,
    )


def _api(endpoint: str) -> object:
    return hosted.api_json(
        (hosted.executable("gh", GitHubProofError), "api", "--method", "GET", endpoint),
        unavailable="GitHub API evidence is unavailable",
        error_type=GitHubProofError,
    )


def _api_pages(endpoint: str) -> list[object]:
    value = hosted.api_json(
        (
            hosted.executable("gh", GitHubProofError),
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            endpoint,
        ),
        unavailable="GitHub paginated API evidence is unavailable",
        error_type=GitHubProofError,
    )
    if not isinstance(value, list):
        raise GitHubProofError("GitHub paginated API response is malformed")
    return [item for item in value]
