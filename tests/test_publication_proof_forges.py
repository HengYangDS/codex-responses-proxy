#!/usr/bin/env python3
"""Offline provider API projection tests for publication proof adapters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publication_proof_github
import publication_proof_gitlab


class ForgeAdapterContracts(unittest.TestCase):
    """Normalize only exact hosted CI and release identities."""

    @staticmethod
    def _gitlab_job(name: str, commit: str, pipeline_id: int = 7) -> dict[str, object]:
        return {
            "name": name,
            "status": "success",
            "allow_failure": False,
            "ref": "v1.2.3",
            "tag": True,
            "pipeline": {
                "id": pipeline_id,
                "sha": commit,
                "ref": "v1.2.3",
                "source": "push",
            },
            "commit": {"id": commit},
        }

    def test_github_requires_exact_verify_and_release_runs(self) -> None:
        commit = "a" * 40
        runs = [
            {
                "id": 1,
                "name": "Verify",
                "path": ".github/workflows/verify.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 2,
                "name": "Release",
                "path": ".github/workflows/release.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
        ]
        jobs = {
            1: [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in publication_proof_github.DEFAULT_REQUIRED_JOBS[:-1]
            ],
            2: [
                {
                    "name": publication_proof_github.DEFAULT_REQUIRED_JOBS[-1],
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        }
        release = {
            "id": 3,
            "tag_name": "v1.2.3",
            "name": "Codex DMX Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
        }
        result = publication_proof_github.normalize(
            repository="owner/repo",
            tag="v1.2.3",
            commit_oid=commit,
            runs=runs,
            jobs=jobs,
            release=release,
        )
        ci = cast(dict[str, object], result["ci"])
        release_result = cast(dict[str, object], result["release"])
        self.assertEqual(ci["status"], "success")
        self.assertEqual(release_result["commit_oid"], commit)
        runs[0]["head_sha"] = "b" * 40
        with self.assertRaises(publication_proof_github.GitHubProofError):
            publication_proof_github.normalize(
                repository="owner/repo",
                tag="v1.2.3",
                commit_oid=commit,
                runs=runs,
                jobs=jobs,
                release=release,
            )

    def test_gitlab_requires_exact_tag_pipeline_jobs_and_release(self) -> None:
        commit = "a" * 40
        pipeline = {
            "id": 7,
            "sha": commit,
            "ref": "v1.2.3",
            "tag": True,
            "source": "push",
            "status": "success",
        }
        jobs = [
            self._gitlab_job(name, commit)
            for name in publication_proof_gitlab.DEFAULT_REQUIRED_JOBS
        ]
        release = {
            "tag_name": "v1.2.3",
            "name": "Codex DMX Proxy v1.2.3",
            "commit": {"id": commit},
            "upcoming_release": False,
            "evidences": [{"sha": "f" * 40}],
        }
        result = publication_proof_gitlab.normalize(
            repository="group/repo",
            tag="v1.2.3",
            commit_oid=commit,
            pipeline=pipeline,
            jobs=jobs,
            release=release,
        )
        ci = cast(dict[str, object], result["ci"])
        self.assertEqual(ci["status"], "success")
        jobs[-1]["allow_failure"] = True
        with self.assertRaises(publication_proof_gitlab.GitLabProofError):
            publication_proof_gitlab.normalize(
                repository="group/repo",
                tag="v1.2.3",
                commit_oid=commit,
                pipeline=pipeline,
                jobs=jobs,
                release=release,
            )

    def test_required_job_duplicates_fail_closed(self) -> None:
        commit = "a" * 40
        github_runs = [
            {
                "id": 1,
                "name": "Verify",
                "path": ".github/workflows/verify.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 2,
                "name": "Release",
                "path": ".github/workflows/release.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
        ]
        duplicated = publication_proof_github.DEFAULT_REQUIRED_JOBS[0]
        github_jobs = {
            1: [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in publication_proof_github.DEFAULT_REQUIRED_JOBS[:-1]
            ]
            + [{"name": duplicated, "status": "completed", "conclusion": "success"}],
            2: [
                {
                    "name": publication_proof_github.DEFAULT_REQUIRED_JOBS[-1],
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        }
        github_release = {
            "id": 3,
            "tag_name": "v1.2.3",
            "name": "Codex DMX Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
        }
        with self.assertRaises(publication_proof_github.GitHubProofError):
            publication_proof_github.normalize(
                repository="owner/repo",
                tag="v1.2.3",
                commit_oid=commit,
                runs=github_runs,
                jobs=github_jobs,
                release=github_release,
            )

        gitlab_pipeline = {
            "id": 7,
            "sha": commit,
            "ref": "v1.2.3",
            "tag": True,
            "source": "push",
            "status": "success",
        }
        gitlab_jobs = [
            self._gitlab_job(name, commit)
            for name in publication_proof_gitlab.DEFAULT_REQUIRED_JOBS
        ] + [self._gitlab_job(publication_proof_gitlab.DEFAULT_REQUIRED_JOBS[0], commit)]
        gitlab_release = {
            "tag_name": "v1.2.3",
            "name": "Codex DMX Proxy v1.2.3",
            "commit": {"id": commit},
            "upcoming_release": False,
            "evidences": [{"sha": "f" * 40}],
        }
        with self.assertRaises(publication_proof_gitlab.GitLabProofError):
            publication_proof_gitlab.normalize(
                repository="group/repo",
                tag="v1.2.3",
                commit_oid=commit,
                pipeline=gitlab_pipeline,
                jobs=gitlab_jobs,
                release=gitlab_release,
            )

    def test_github_collection_binds_api_tag_object_to_fetched_identity(self) -> None:
        commit = "a" * 40
        tag_object = "b" * 40
        runs = [
            {
                "id": 1,
                "name": "Verify",
                "path": ".github/workflows/verify.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 2,
                "name": "Release",
                "path": ".github/workflows/release.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
        ]
        responses = [
            {"object": {"type": "tag", "sha": tag_object}},
            {"tag": "v1.2.3", "sha": tag_object, "object": {"type": "commit", "sha": commit}},
            {"workflow_runs": runs},
            {
                "jobs": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in publication_proof_github.DEFAULT_REQUIRED_JOBS[:-1]
                ]
            },
            {
                "jobs": [
                    {
                        "name": publication_proof_github.DEFAULT_REQUIRED_JOBS[-1],
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            },
            {
                "id": 3,
                "tag_name": "v1.2.3",
                "name": "Codex DMX Proxy v1.2.3",
                "draft": False,
                "prerelease": False,
            },
        ]
        with (
            mock.patch.object(publication_proof_github, "_api", side_effect=responses[:2]),
            mock.patch.object(
                publication_proof_github,
                "_api_pages",
                side_effect=[
                    [{"workflow_runs": [runs[0]]}],
                    [{"workflow_runs": [runs[1]]}],
                    [{"jobs": responses[3]["jobs"]}],
                    [{"jobs": responses[4]["jobs"]}],
                    [[responses[5]]],
                ],
            ),
        ):
            publication_proof_github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )
        responses[0] = {"object": {"type": "tag", "sha": "c" * 40}}
        with (
            mock.patch.object(publication_proof_github, "_api", side_effect=responses[:1]),
            self.assertRaises(publication_proof_github.GitHubProofError),
        ):
            publication_proof_github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

    def test_required_job_cannot_move_to_the_wrong_github_workflow(self) -> None:
        commit = "a" * 40
        runs = [
            {
                "id": 1,
                "name": "Verify",
                "path": ".github/workflows/verify.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 2,
                "name": "Release",
                "path": ".github/workflows/release.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            },
        ]
        jobs = {
            1: [],
            2: [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in publication_proof_github.DEFAULT_REQUIRED_JOBS
            ],
        }
        release = {
            "id": 3,
            "tag_name": "v1.2.3",
            "name": "Codex DMX Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
        }
        with self.assertRaisesRegex(publication_proof_github.GitHubProofError, "wrong workflow"):
            publication_proof_github.normalize(
                repository="owner/repo",
                tag="v1.2.3",
                commit_oid=commit,
                runs=runs,
                jobs=jobs,
                release=release,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
