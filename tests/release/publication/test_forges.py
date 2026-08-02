#!/usr/bin/env python3
"""Offline provider API projection tests for publication proof adapters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.release.publication import github
from codex_responses_proxy.release.publication import gitlab
from codex_responses_proxy.release import assets as release_assets


def _release_assets() -> dict[str, bytes]:
    archive_name = "codex-responses-proxy-1.2.3.tar.gz"
    archive = b"archive"
    return {
        archive_name: archive,
        release_assets.CHECKSUM_NAME: release_assets.checksums({archive_name: archive}),
    }


class ForgeAdapterContracts(unittest.TestCase):
    """Normalize only exact hosted CI and release identities."""

    @staticmethod
    def _github_fixture(
        commit: str,
    ) -> tuple[
        list[dict[str, object]],
        dict[int, list[dict[str, object]]],
        dict[str, object],
        dict[str, bytes],
    ]:
        runs: list[dict[str, object]] = [
            {
                "id": index,
                "name": name,
                "path": f".github/workflows/{name.lower()}.yml",
                "event": "push",
                "head_branch": "v1.2.3",
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
            }
            for index, name in ((1, "Verify"), (2, "Release"))
        ]
        jobs: dict[int, list[dict[str, object]]] = {
            1: [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in github.DEFAULT_REQUIRED_JOBS[:-1]
            ],
            2: [
                {
                    "name": github.DEFAULT_REQUIRED_JOBS[-1],
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        }
        release: dict[str, object] = {
            "id": 3,
            "tag_name": "v1.2.3",
            "name": "Codex Responses Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-07-29T00:00:00Z",
        }
        assets = _release_assets()
        return runs, jobs, release, assets

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

    @staticmethod
    def _normalize_github(
        commit: str,
        fixture: tuple[
            list[dict[str, object]],
            dict[int, list[dict[str, object]]],
            dict[str, object],
            dict[str, bytes],
        ],
    ):
        runs, jobs, release, assets = fixture
        return github.normalize(
            repository="owner/repo",
            tag="v1.2.3",
            commit_oid=commit,
            runs=runs,
            jobs=jobs,
            release=release,
            assets=assets,
        )

    @staticmethod
    def _normalize_gitlab(
        commit: str,
        fixture: tuple[
            dict[str, object], list[dict[str, object]], dict[str, object], dict[str, bytes]
        ],
    ):
        pipeline, jobs, release, assets = fixture
        return gitlab.normalize(
            repository="group/repo",
            tag="v1.2.3",
            commit_oid=commit,
            pipeline=pipeline,
            jobs=jobs,
            release=release,
            assets=assets,
        )

    @staticmethod
    def _gitlab_fixture(
        commit: str,
    ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object], dict[str, bytes]]:
        pipeline: dict[str, object] = {
            "id": 7,
            "sha": commit,
            "ref": "v1.2.3",
            "tag": True,
            "source": "push",
            "status": "success",
        }
        jobs = [
            ForgeAdapterContracts._gitlab_job(name, commit) for name in gitlab.DEFAULT_REQUIRED_JOBS
        ]
        release: dict[str, object] = {
            "tag_name": "v1.2.3",
            "name": "Codex Responses Proxy v1.2.3",
            "commit": {"id": commit},
            "upcoming_release": False,
            "description": "Provider-native source release. See CHANGELOG.md for user-relevant changes.",
            "evidences": [{"sha": "f" * 40}],
        }
        return pipeline, jobs, release, _release_assets()

    def test_github_requires_exact_verify_and_release_runs(self) -> None:
        commit = "a" * 40
        runs, jobs, release, assets = self._github_fixture(commit)
        result = self._normalize_github(commit, (runs, jobs, release, assets))
        ci = cast(dict[str, object], result["ci"])
        release_result = cast(dict[str, object], result["release"])
        self.assertEqual(ci["status"], "success")
        self.assertEqual(release_result["commit_oid"], commit)
        runs[0]["head_sha"] = "b" * 40
        with self.assertRaises(github.GitHubProofError):
            self._normalize_github(commit, (runs, jobs, release, assets))

    def test_gitlab_requires_exact_tag_pipeline_jobs_and_release(self) -> None:
        commit = "a" * 40
        pipeline, jobs, release, assets = self._gitlab_fixture(commit)
        result = self._normalize_gitlab(commit, (pipeline, jobs, release, assets))
        ci = cast(dict[str, object], result["ci"])
        self.assertEqual(ci["status"], "success")
        jobs[-1]["allow_failure"] = True
        with self.assertRaises(gitlab.GitLabProofError):
            self._normalize_gitlab(commit, (pipeline, jobs, release, assets))

    def test_required_job_duplicates_fail_closed(self) -> None:
        commit = "a" * 40
        runs, github_jobs, github_release, github_assets = self._github_fixture(commit)
        duplicated = github.DEFAULT_REQUIRED_JOBS[0]
        github_jobs[1].append({"name": duplicated, "status": "completed", "conclusion": "success"})
        with self.assertRaises(github.GitHubProofError):
            self._normalize_github(commit, (runs, github_jobs, github_release, github_assets))

        pipeline, jobs, release, gitlab_assets = self._gitlab_fixture(commit)
        jobs.append(self._gitlab_job(gitlab.DEFAULT_REQUIRED_JOBS[0], commit))
        with self.assertRaises(gitlab.GitLabProofError):
            self._normalize_gitlab(commit, (pipeline, jobs, release, gitlab_assets))

    def test_github_collection_binds_api_tag_object_to_fetched_identity(self) -> None:
        commit = "a" * 40
        tag_object = "b" * 40
        runs, _, _, asset_bytes = self._github_fixture(commit)
        responses = [
            {"ref": "refs/tags/v1.2.3", "object": {"type": "tag", "sha": tag_object}},
            {"tag": "v1.2.3", "sha": tag_object, "object": {"type": "commit", "sha": commit}},
            {"workflow_runs": runs},
            {
                "jobs": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in github.DEFAULT_REQUIRED_JOBS[:-1]
                ]
            },
            {
                "jobs": [
                    {
                        "name": github.DEFAULT_REQUIRED_JOBS[-1],
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            },
            {
                "id": 3,
                "tag_name": "v1.2.3",
                "name": "Codex Responses Proxy v1.2.3",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-07-29T00:00:00Z",
                "assets": [
                    {"name": name, "url": f"https://api.example/assets/{index}"}
                    for index, name in enumerate(asset_bytes, 1)
                ],
            },
        ]
        with (
            mock.patch.object(github.hosted, "executable", return_value="gh"),
            mock.patch.object(github, "_api", side_effect=responses[:2]),
            mock.patch.object(
                github,
                "_api_pages",
                side_effect=[
                    [{"workflow_runs": [runs[0]]}],
                    [{"workflow_runs": [runs[1]]}],
                    [{"jobs": responses[3]["jobs"]}],
                    [{"jobs": responses[4]["jobs"]}],
                    [[responses[5]]],
                ],
            ),
            mock.patch.object(github.hosted, "api_bytes", side_effect=list(asset_bytes.values())),
        ):
            github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )
        responses[0] = {"object": {"type": "tag", "sha": "c" * 40}}
        with (
            mock.patch.object(github.hosted, "executable", return_value="gh"),
            mock.patch.object(github, "_api", side_effect=responses[:1]),
            self.assertRaises(github.GitHubProofError),
        ):
            github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

    def test_required_job_cannot_move_to_the_wrong_github_workflow(self) -> None:
        commit = "a" * 40
        runs, jobs, release, assets = self._github_fixture(commit)
        jobs: dict[int, list[dict[str, object]]] = {
            1: [],
            2: [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in github.DEFAULT_REQUIRED_JOBS
            ],
        }
        with self.assertRaisesRegex(github.GitHubProofError, "wrong workflow"):
            self._normalize_github(commit, (runs, jobs, release, assets))

    def test_provider_candidates_and_release_identity_fail_closed(self) -> None:
        commit = "a" * 40
        pipeline, jobs, release, assets = self._gitlab_fixture(commit)
        for mutation in (
            lambda: pipeline.update(source="web"),
            lambda: release.update(description="wrong"),
            lambda: release.update(evidences=[{"sha": "f" * 40}, {"sha": "e" * 40}]),
        ):
            pipeline.update(source="push")
            release.update(
                description="Provider-native source release. See CHANGELOG.md for user-relevant changes.",
                evidences=[{"sha": "f" * 40}],
            )
            mutation()
            with (
                self.subTest(pipeline=pipeline, release=release),
                self.assertRaises(gitlab.GitLabProofError),
            ):
                self._normalize_gitlab(commit, (pipeline, jobs, release, assets))

        runs, github_jobs, github_release, github_assets = self._github_fixture(commit)
        for mutation in (
            lambda: runs.append(dict(runs[0], id=4)),
            lambda: github_release.update(published_at=None),
        ):
            runs[:] = runs[:2]
            github_release.update(published_at="2026-07-29T00:00:00Z")
            mutation()
            with (
                self.subTest(runs=runs, release=github_release),
                self.assertRaises(github.GitHubProofError),
            ):
                self._normalize_github(commit, (runs, github_jobs, github_release, github_assets))

    def test_github_malformed_boundaries_and_hosted_transport_fail_closed(self) -> None:
        commit, tag_object = "a" * 40, "b" * 40
        runs, jobs, release, assets = self._github_fixture(commit)
        cases = (
            ("run-id", lambda: runs[0].update(id=True)),
            ("incomplete-job", lambda: jobs[1][0].update(status="queued")),
            ("release-id", lambda: release.update(id=True)),
        )
        for name, mutate in cases:
            runs, jobs, release, assets = self._github_fixture(commit)
            mutate()
            with self.subTest(name=name), self.assertRaises(github.GitHubProofError):
                self._normalize_github(commit, (runs, jobs, release, assets))

        for helper, value in (
            (github._mapping, []),
            (github._mappings, {}),
        ):
            with self.assertRaises(github.GitHubProofError):
                helper(value, "malformed")
        with (
            mock.patch.object(github.hosted, "executable", return_value="gh"),
            mock.patch.object(github.hosted, "api_json", return_value={}),
            self.assertRaises(github.GitHubProofError),
        ):
            github._api_pages("endpoint")
        with (
            mock.patch.object(github.hosted, "executable", return_value="gh"),
            mock.patch.object(github.hosted, "api_json", return_value={}),
        ):
            self.assertEqual(github._api("endpoint"), {})

        responses = [
            {"ref": "refs/tags/v1.2.3", "object": {"type": "tag", "sha": tag_object}},
            {"tag": "wrong", "sha": tag_object, "object": {"type": "commit", "sha": commit}},
        ]
        with (
            mock.patch.object(github, "_api", side_effect=responses),
            self.assertRaisesRegex(github.GitHubProofError, "tag identity"),
        ):
            github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

    def test_gitlab_collection_and_malformed_boundaries_fail_closed(self) -> None:
        commit, tag_object = "a" * 40, "b" * 40
        pipeline, jobs, release, asset_bytes = self._gitlab_fixture(commit)
        release["assets"] = {
            "links": [
                {"name": name, "url": f"https://gitlab.example/assets/{index}"}
                for index, name in enumerate(asset_bytes, 1)
            ]
        }
        tag_record = {
            "name": "v1.2.3",
            "target": tag_object,
            "commit": {"id": commit},
        }
        with (
            mock.patch.object(
                gitlab,
                "_api",
                side_effect=[tag_record, pipeline],
            ),
            mock.patch.object(gitlab.hosted, "executable", return_value="glab"),
            mock.patch.object(
                gitlab.hosted, "api_bytes", side_effect=list(asset_bytes.values())
            ) as download,
            mock.patch.object(
                gitlab,
                "_api_pages",
                side_effect=[[pipeline], jobs, [release]],
            ),
        ):
            result = gitlab.collect(
                api_base="https://gitlab.example/api/v4/",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )
        self.assertEqual(result["repository"], "group/repo")
        self.assertEqual(
            [call.args[0] for call in download.call_args_list],
            [
                ("glab", "api", "--method", "GET", f"https://gitlab.example/assets/{index}")
                for index in range(1, 3)
            ],
        )

        with self.assertRaises(gitlab.GitLabProofError):
            self._normalize_gitlab(
                commit,
                (pipeline, [{"name": "not-required"}, *jobs[:-1]], release, asset_bytes),
            )

        wrong_commit = {**tag_record, "commit": {"id": "0" * 40}}
        with (
            mock.patch.object(gitlab, "_api", return_value=wrong_commit),
            self.assertRaisesRegex(gitlab.GitLabProofError, "commit differs"),
        ):
            gitlab.collect(
                api_base="https://gitlab.example/api/v4",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

        with (
            mock.patch.object(
                gitlab,
                "_api",
                side_effect=[tag_record, {**pipeline, "id": 8}],
            ),
            mock.patch.object(gitlab, "_api_pages", return_value=[pipeline]),
            self.assertRaisesRegex(gitlab.GitLabProofError, "detail identity"),
        ):
            gitlab.collect(
                api_base="https://gitlab.example/api/v4",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

        for value in ([], None):
            with self.assertRaises(gitlab.GitLabProofError):
                gitlab._mapping(value, "malformed")
        for value in ([], {}):
            with self.assertRaises(gitlab.GitLabProofError):
                gitlab._stable_id(value)
        for value, expected in (([1], [1]), ({"id": 1}, [{"id": 1}])):
            self.assertEqual(gitlab._page_items(value), expected)
        with self.assertRaises(gitlab.GitLabProofError):
            gitlab._page_items("wrong")
        with self.assertRaises(gitlab.GitLabProofError):
            gitlab._evidence({})
        with self.assertRaisesRegex(gitlab.GitLabProofError, "HTTP"):
            gitlab.collect(
                api_base="file:///tmp",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

        pipeline, jobs, release, assets = self._gitlab_fixture(commit)
        for mutation in (
            lambda: pipeline.update(yaml_errors="bad"),
            lambda: jobs[0].update(ref="wrong"),
            lambda: jobs[0].update(commit={"id": "0" * 40}),
            lambda: release.update(commit={"id": "0" * 40}),
            lambda: release.update(evidences=[{"sha": ""}]),
        ):
            pipeline, jobs, release, assets = self._gitlab_fixture(commit)
            mutation()
            with self.assertRaises(gitlab.GitLabProofError):
                self._normalize_gitlab(commit, (pipeline, jobs, release, assets))

    def test_gitlab_cli_transport_and_pagination_translate_failures(self) -> None:
        completed = mock.Mock(stdout='[{"id":1}]\n{"id":2}\n')
        with (
            mock.patch.object(gitlab.hosted, "executable", return_value="glab"),
            mock.patch.object(gitlab.subprocess, "run", return_value=completed),
        ):
            self.assertEqual(gitlab._api_pages("endpoint"), [{"id": 1}, {"id": 2}])
        with (
            mock.patch.object(gitlab.hosted, "executable", return_value="glab"),
            mock.patch.object(gitlab.hosted, "api_json", return_value={}),
        ):
            self.assertEqual(gitlab._api("endpoint"), {})
        for failure in (OSError("missing"), ValueError("bad")):
            patch = (
                mock.patch.object(gitlab.subprocess, "run", side_effect=failure)
                if isinstance(failure, OSError)
                else mock.patch.object(gitlab.json, "loads", side_effect=failure)
            )
            with (
                mock.patch.object(gitlab.hosted, "executable", return_value="glab"),
                patch,
                self.assertRaises(gitlab.GitLabProofError),
            ):
                gitlab._api_pages("endpoint")


if __name__ == "__main__":
    unittest.main(verbosity=2)
