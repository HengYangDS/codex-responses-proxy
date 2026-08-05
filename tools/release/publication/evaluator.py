"""Pure fail-closed evaluation for independent dual-Forge publications."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final, TypedDict, cast

_TAG: Final = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_OID: Final = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_FORGE_FIELDS: Final = frozenset(
    {
        "provider",
        "repository",
        "tag",
        "tag_object_oid",
        "commit_oid",
        "tree_oid",
        "anchor_sha256",
        "signature_verified",
        "assets",
        "ci",
        "release",
    }
)
_CI_FIELDS: Final = frozenset({"id", "revision_oid", "status", "jobs"})
_RELEASE_FIELDS: Final = frozenset({"id", "tag", "commit_oid", "name", "draft", "prerelease"})


class PublicationPolicy(TypedDict):
    """Required hosted jobs for each independent Forge plane."""

    gitlab_jobs: tuple[str, ...]
    github_jobs: tuple[str, ...]


def evaluate(
    tag: str,
    gitlab: Mapping[str, object],
    github: Mapping[str, object],
    policy: PublicationPolicy,
) -> dict[str, object]:
    """Evaluate complete evidence without minting installation authority."""

    if not policy["gitlab_jobs"] or not policy["github_jobs"]:
        return {
            "schema_version": 1,
            "tag": tag,
            "verified": False,
            "tree_equal": False,
            "reasons": ["publication_policy_empty"],
            "forges": {},
        }

    reasons: list[str] = []
    normalized: dict[str, dict[str, object]] = {}
    for provider, evidence, required_jobs in (
        ("gitlab", gitlab, policy["gitlab_jobs"]),
        ("github", github, policy["github_jobs"]),
    ):
        forge, forge_reasons = _evaluate_forge(provider, tag, evidence, required_jobs)
        reasons.extend(forge_reasons)
        if forge is not None:
            normalized[provider] = forge

    tree_equal = (
        "gitlab" in normalized
        and "github" in normalized
        and normalized["gitlab"]["tree_oid"] == normalized["github"]["tree_oid"]
    )
    if "gitlab" in normalized and "github" in normalized and not tree_equal:
        reasons.append("tree_mismatch")
    assets_equal = _common_payloads_equal(normalized, tag)
    if "gitlab" in normalized and "github" in normalized and not assets_equal:
        reasons.append("asset_mismatch")
    verified = not reasons and tree_equal and assets_equal
    return {
        "schema_version": 1,
        "tag": tag,
        "verified": verified,
        "tree_equal": tree_equal,
        "assets_equal": assets_equal,
        "reasons": reasons,
        "forges": normalized,
    }


def _common_payloads_equal(normalized: Mapping[str, Mapping[str, object]], tag: str) -> bool:
    """Compare archive and manifest digests for platforms published by both Forges."""

    if not {"gitlab", "github"} <= set(normalized):
        return False
    inventories = {
        provider: cast(Mapping[str, str], normalized[provider]["assets"])
        for provider in ("gitlab", "github")
    }
    version = tag.removeprefix("v")
    prefix = f"codex-responses-proxy-{version}-"
    platforms = [
        {
            name.removeprefix(prefix).removesuffix(".tar.gz")
            for name in inventory
            if name.startswith(prefix) and name.endswith(".tar.gz")
        }
        for inventory in inventories.values()
    ]
    common = set.intersection(*platforms)
    if not common:
        return False
    return all(
        inventories["gitlab"][name] == inventories["github"][name]
        for platform in common
        for name in (
            f"{prefix}{platform}.tar.gz",
            f"codex-responses-proxy-{platform}.manifest.json",
        )
    )


def _evaluate_forge(
    provider: str,
    tag: str,
    evidence: Mapping[str, object],
    required_jobs: Sequence[str],
) -> tuple[dict[str, object] | None, list[str]]:
    if set(evidence) != _FORGE_FIELDS:
        return None, [f"{provider}.invalid_evidence"]
    if (
        evidence.get("provider") != provider
        or evidence.get("tag") != tag
        or not _TAG.fullmatch(tag)
    ):
        return None, [f"{provider}.invalid_evidence"]
    if not isinstance(evidence.get("repository"), str) or not evidence["repository"]:
        return None, [f"{provider}.invalid_evidence"]
    if any(
        not isinstance(evidence.get(field), str) or not _OID.fullmatch(cast(str, evidence[field]))
        for field in ("tag_object_oid", "commit_oid", "tree_oid")
    ):
        return None, [f"{provider}.invalid_evidence"]
    if not isinstance(evidence.get("anchor_sha256"), str) or not _SHA256.fullmatch(
        cast(str, evidence["anchor_sha256"])
    ):
        return None, [f"{provider}.invalid_evidence"]

    reasons: list[str] = []
    if evidence.get("signature_verified") is not True:
        reasons.append(f"{provider}.signature_unverified")
    assets = evidence.get("assets")
    if not isinstance(assets, Mapping):
        return None, [f"{provider}.invalid_evidence"]
    typed_assets = cast(Mapping[str, object], assets)
    names = set(typed_assets)
    if "SHA256SUMS" not in names:
        return None, [f"{provider}.invalid_evidence"]
    archive_prefix = f"codex-responses-proxy-{tag.removeprefix('v')}-"
    platforms = {
        name.removeprefix(archive_prefix).removesuffix(".tar.gz")
        for name in names
        if name.startswith(archive_prefix) and name.endswith(".tar.gz")
    }
    expected_assets = {
        *(f"{archive_prefix}{platform}.tar.gz" for platform in platforms),
        *(f"codex-responses-proxy-{platform}.manifest.json" for platform in platforms),
        "SHA256SUMS",
        "SHA256SUMS.sig",
    }
    if not platforms or names != expected_assets:
        return None, [f"{provider}.invalid_evidence"]
    if any(
        not isinstance(typed_assets.get(name), str)
        or not _SHA256.fullmatch(cast(str, typed_assets[name]))
        for name in expected_assets
    ):
        return None, [f"{provider}.invalid_evidence"]
    ci = evidence.get("ci")
    release = evidence.get("release")
    if not isinstance(ci, Mapping) or not isinstance(release, Mapping):
        return None, [f"{provider}.invalid_evidence"]
    typed_ci = cast(Mapping[str, object], ci)
    typed_release = cast(Mapping[str, object], release)
    if set(typed_ci) != _CI_FIELDS or set(typed_release) != _RELEASE_FIELDS:
        return None, [f"{provider}.invalid_evidence"]
    commit = cast(str, evidence["commit_oid"])
    if typed_ci.get("revision_oid") != commit:
        reasons.append(f"{provider}.ci_revision_mismatch")
    if typed_ci.get("status") != "success":
        reasons.append(f"{provider}.ci_not_successful")
    jobs = typed_ci.get("jobs")
    if not isinstance(jobs, Mapping):
        return None, [f"{provider}.invalid_evidence"]
    typed_jobs = cast(Mapping[str, object], jobs)
    for job in required_jobs:
        if job not in typed_jobs:
            reasons.append(f"{provider}.ci_required_job_missing:{job}")
        elif typed_jobs[job] != "success":
            reasons.append(f"{provider}.ci_required_job_not_successful:{job}")
    if typed_release.get("tag") != tag:
        reasons.append(f"{provider}.release_tag_mismatch")
    if typed_release.get("commit_oid") != commit:
        reasons.append(f"{provider}.release_commit_mismatch")
    if typed_release.get("name") != f"Codex Responses Proxy {tag}":
        reasons.append(f"{provider}.release_name_mismatch")
    if typed_release.get("draft") is not False:
        reasons.append(f"{provider}.release_draft")
    if typed_release.get("prerelease") is not False:
        reasons.append(f"{provider}.release_prerelease")
    normalized = {
        "provider": provider,
        "repository": evidence["repository"],
        "tag": tag,
        "tag_object_oid": evidence["tag_object_oid"],
        "commit_oid": commit,
        "tree_oid": evidence["tree_oid"],
        "anchor_sha256": evidence["anchor_sha256"],
        "signature_verified": evidence["signature_verified"],
        "assets": dict(typed_assets),
        "ci": {
            "id": typed_ci.get("id"),
            "revision_oid": typed_ci.get("revision_oid"),
            "status": typed_ci.get("status"),
            "jobs": {job: typed_jobs.get(job) for job in required_jobs},
        },
        "release": {
            "id": typed_release.get("id"),
            "tag": typed_release.get("tag"),
            "commit_oid": typed_release.get("commit_oid"),
            "name": typed_release.get("name"),
            "draft": typed_release.get("draft"),
            "prerelease": typed_release.get("prerelease"),
        },
    }
    return normalized, reasons
