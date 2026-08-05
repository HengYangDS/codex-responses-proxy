"""Offline provider API projection tests for publication proof adapters."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from tools.release import product_assets as release_assets
from tools.release.publication import github, gitlab
import pytest

ROOT = Path(__file__).resolve().parents[3]


def _release_assets(
    platforms: tuple[str, ...] = release_assets.RELEASE_PLATFORMS,
) -> dict[str, bytes]:
    version = "1.2.3"
    platform_assets: dict[str, bytes] = {}
    for platform in platforms:
        executable = (
            "codex-responses-proxy.exe"
            if platform.startswith("windows-")
            else "codex-responses-proxy"
        )
        files = {executable: release_assets.ArchiveFile(f"native-{platform}".encode(), mode=0o755)}
        archive_name = release_assets.archive_name(version, platform)
        archive = release_assets.archive_bytes(files, version, platform)
        platform_assets[archive_name] = archive
        platform_assets[release_assets.manifest_name(platform)] = release_assets.asset_manifest(
            version=version,
            platform=platform,
            archive_name=archive_name,
            archive=archive,
            files=files,
        )
    unsigned = {
        **platform_assets,
        release_assets.CHECKSUM_NAME: release_assets.checksums(platform_assets),
    }
    return {**unsigned, release_assets.SIGNATURE_NAME: b"fixture-signature\n"}


class ForgeAdapterContracts:
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
        return pipeline, jobs, release, _release_assets(("linux-x86_64",))

    def test_github_requires_exact_verify_and_release_runs(self) -> None:
        commit = "a" * 40
        runs, jobs, release, assets = self._github_fixture(commit)
        result = self._normalize_github(commit, (runs, jobs, release, assets))
        ci = cast(dict[str, object], result["ci"])
        release_result = cast(dict[str, object], result["release"])
        assert ci["status"] == "success"
        assert release_result["commit_oid"] == commit
        runs[0]["head_sha"] = "b" * 40
        with pytest.raises(github.GitHubProofError):
            self._normalize_github(commit, (runs, jobs, release, assets))

    def test_gitlab_requires_exact_tag_pipeline_jobs_and_release(self) -> None:
        commit = "a" * 40
        pipeline, jobs, release, assets = self._gitlab_fixture(commit)
        result = self._normalize_gitlab(commit, (pipeline, jobs, release, assets))
        ci = cast(dict[str, object], result["ci"])
        assert ci["status"] == "success"
        jobs[-1]["allow_failure"] = True
        with pytest.raises(gitlab.GitLabProofError):
            self._normalize_gitlab(commit, (pipeline, jobs, release, assets))

    def test_required_job_duplicates_fail_closed(self) -> None:
        commit = "a" * 40
        runs, github_jobs, github_release, github_assets = self._github_fixture(commit)
        duplicated = github.DEFAULT_REQUIRED_JOBS[0]
        github_jobs[1].append({"name": duplicated, "status": "completed", "conclusion": "success"})
        with pytest.raises(github.GitHubProofError):
            self._normalize_github(commit, (runs, github_jobs, github_release, github_assets))

        pipeline, jobs, release, gitlab_assets = self._gitlab_fixture(commit)
        jobs.append(self._gitlab_job(gitlab.DEFAULT_REQUIRED_JOBS[0], commit))
        with pytest.raises(gitlab.GitLabProofError):
            self._normalize_gitlab(commit, (pipeline, jobs, release, gitlab_assets))

    def test_github_collection_binds_api_tag_object_to_fetched_identity(self, *, mocker) -> None:
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
        mocker.patch.object(github.hosted, "executable", return_value="gh")
        mocker.patch.object(github, "_api", side_effect=responses[:2])
        mocker.patch.object(
            github,
            "_api_pages",
            side_effect=[
                [{"workflow_runs": [runs[0]]}],
                [{"workflow_runs": [runs[1]]}],
                [{"jobs": responses[3]["jobs"]}],
                [{"jobs": responses[4]["jobs"]}],
                [[responses[5]]],
            ],
        )
        mocker.patch.object(github.hosted, "api_bytes", side_effect=list(asset_bytes.values()))
        github.collect(
            repository="owner/repo",
            tag="v1.2.3",
            tag_object_oid=tag_object,
            commit_oid=commit,
        )
        responses[0] = {"object": {"type": "tag", "sha": "c" * 40}}
        mocker.patch.object(github.hosted, "executable", return_value="gh")
        mocker.patch.object(github, "_api", side_effect=responses[:1])
        with pytest.raises(github.GitHubProofError):
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
        with pytest.raises(github.GitHubProofError, match="wrong workflow"):
            self._normalize_github(commit, (runs, jobs, release, assets))

    def test_provider_candidates_and_release_identity_fail_closed(self, subtests) -> None:
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
                subtests.test(pipeline=pipeline, release=release),
                pytest.raises(gitlab.GitLabProofError),
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
                subtests.test(runs=runs, release=github_release),
                pytest.raises(github.GitHubProofError),
            ):
                self._normalize_github(commit, (runs, github_jobs, github_release, github_assets))

    def test_github_malformed_boundaries_and_hosted_transport_fail_closed(
        self, subtests, *, mocker
    ) -> None:
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
            with subtests.test(name=name), pytest.raises(github.GitHubProofError):
                self._normalize_github(commit, (runs, jobs, release, assets))

        for helper, value in (
            (github._mapping, []),
            (github._mappings, {}),
        ):
            with pytest.raises(github.GitHubProofError):
                helper(value, "malformed")
        mocker.patch.object(github.hosted, "executable", return_value="gh")
        mocker.patch.object(github.hosted, "api_json", return_value={})
        with pytest.raises(github.GitHubProofError):
            github._api_pages("endpoint")
        mocker.patch.object(github.hosted, "executable", return_value="gh")
        mocker.patch.object(github.hosted, "api_json", return_value={})
        assert github._api("endpoint") == {}

        responses = [
            {"ref": "refs/tags/v1.2.3", "object": {"type": "tag", "sha": tag_object}},
            {"tag": "wrong", "sha": tag_object, "object": {"type": "commit", "sha": commit}},
        ]
        mocker.patch.object(github, "_api", side_effect=responses)
        with pytest.raises(github.GitHubProofError, match="tag identity"):
            github.collect(
                repository="owner/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

    def test_gitlab_collection_and_malformed_boundaries_fail_closed(self, *, mocker) -> None:
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
        mocker.patch.object(
            gitlab,
            "_api",
            side_effect=[tag_record, pipeline],
        )
        mocker.patch.object(gitlab.hosted, "executable", return_value="glab")
        download = mocker.patch.object(
            gitlab.hosted, "api_bytes", side_effect=list(asset_bytes.values())
        )
        mocker.patch.object(
            gitlab,
            "_api_pages",
            side_effect=[[pipeline], jobs, [release]],
        )
        result = gitlab.collect(
            api_base="https://gitlab.example/api/v4/",
            repository="group/repo",
            tag="v1.2.3",
            tag_object_oid=tag_object,
            commit_oid=commit,
        )
        assert result["repository"] == "group/repo"
        assert [call.args[0] for call in download.call_args_list] == [
            ("glab", "api", "--method", "GET", f"https://gitlab.example/assets/{index}")
            for index in range(1, len(asset_bytes) + 1)
        ]

        with pytest.raises(gitlab.GitLabProofError):
            self._normalize_gitlab(
                commit,
                (pipeline, [{"name": "not-required"}, *jobs[:-1]], release, asset_bytes),
            )

        wrong_commit = {**tag_record, "commit": {"id": "0" * 40}}
        mocker.patch.object(gitlab, "_api", return_value=wrong_commit)
        with pytest.raises(gitlab.GitLabProofError, match="commit differs"):
            gitlab.collect(
                api_base="https://gitlab.example/api/v4",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )
        mocker.patch.object(
            gitlab,
            "_api",
            side_effect=[tag_record, {**pipeline, "id": 8}],
        )
        mocker.patch.object(gitlab, "_api_pages", return_value=[pipeline])

        with pytest.raises(gitlab.GitLabProofError, match="detail identity"):
            gitlab.collect(
                api_base="https://gitlab.example/api/v4",
                repository="group/repo",
                tag="v1.2.3",
                tag_object_oid=tag_object,
                commit_oid=commit,
            )

        for value in ([], None):
            with pytest.raises(gitlab.GitLabProofError):
                gitlab._mapping(value, "malformed")
        for value in ([], {}):
            with pytest.raises(gitlab.GitLabProofError):
                gitlab._stable_id(value)
        for value, expected in (([1], [1]), ({"id": 1}, [{"id": 1}])):
            assert gitlab._page_items(value) == expected
        with pytest.raises(gitlab.GitLabProofError):
            gitlab._page_items("wrong")
        with pytest.raises(gitlab.GitLabProofError):
            gitlab._evidence({})
        with pytest.raises(gitlab.GitLabProofError, match="HTTP"):
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
            with pytest.raises(gitlab.GitLabProofError):
                self._normalize_gitlab(commit, (pipeline, jobs, release, assets))

    def test_gitlab_cli_transport_and_pagination_translate_failures(self, *, mocker) -> None:
        completed = mocker.Mock(stdout='[{"id":1}]\n{"id":2}\n')
        mocker.patch.object(gitlab.hosted, "executable", return_value="glab")
        mocker.patch.object(gitlab.subprocess, "run", return_value=completed)
        assert gitlab._api_pages("endpoint") == [{"id": 1}, {"id": 2}]
        mocker.stopall()
        mocker.patch.object(gitlab.hosted, "executable", return_value="glab")
        mocker.patch.object(gitlab.hosted, "api_json", return_value={})
        assert gitlab._api("endpoint") == {}
        mocker.stopall()
        for failure in (OSError("missing"), ValueError("bad")):
            mocker.patch.object(gitlab.hosted, "executable", return_value="glab")
            (
                mocker.patch.object(gitlab.subprocess, "run", side_effect=failure)
                if isinstance(failure, OSError)
                else mocker.patch.object(gitlab.json, "loads", side_effect=failure)
            )
            with pytest.raises(gitlab.GitLabProofError):
                gitlab._api_pages("endpoint")
            mocker.stopall()
