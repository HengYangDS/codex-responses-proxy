"""Evidence-only CLI and opaque live publication-authority contracts."""

from __future__ import annotations

import operator
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

from codex_responses_proxy.lifecycle import artifact
from tests.release.publication.fixtures import VERIFY_ARGUMENTS
from tests.release.publication.fixtures import VerifyArguments
from tests.release.publication.fixtures import forge_evidence
from tests.release.publication.fixtures import verified_evidence
from tools.release import product_assets
from tools.release import verify as publication_cli
from tools.release.publication import evaluator
from tools.release.publication import hosted
from tools.release.publication import verification as publication

ROOT = Path(__file__).resolve().parents[3]


class PublicationProofCliContracts:
    """Keep output secret-free and incapable of minting source authority."""

    def test_publication_owner_imports_semantic_collaborators(self) -> None:
        assert publication.evaluator is evaluator

    def test_evidence_projection_has_no_installation_capability(self, *, mocker) -> None:
        assert not hasattr(artifact, "ForgePublication")
        assert not hasattr(artifact, "PublicationProof")
        assert not hasattr(publication, "PublishedRelease")
        assert not hasattr(publication, "consume")
        assert verified_evidence(forge_evidence(), mocker=mocker)["verified"]

    def test_publication_verifier_fails_closed_on_invalid_inputs(self, *, mocker) -> None:
        arguments = VERIFY_ARGUMENTS
        mocker.patch.object(
            publication.git,
            "collect",
            side_effect=publication.git.GitProofError("offline"),
        )
        with pytest.raises(publication.PublicationError, match="unavailable or invalid") as failure:
            publication.verify(**arguments)
        assert failure.value.reasons == ("gitlab.remote_git_evidence_invalid",)

        invalid_tag: VerifyArguments = {**arguments, "tag": "latest"}
        with pytest.raises(publication.PublicationError, match="exact vMAJOR") as failure:
            publication.verify(**invalid_tag)
        assert failure.value.reasons == ("release_tag_invalid",)

    def test_publication_verifier_composes_validated_adapter_evidence(self, *, mocker) -> None:
        commit = "b" * 40
        git_evidence = {
            "tag_object_oid": "a" * 40,
            "commit_oid": commit,
            "tree_oid": "c" * 40,
            "anchor_sha256": "f" * 64,
            "signature_verified": True,
        }
        assets = dict.fromkeys(
            product_assets.release_asset_names("1.2.3", product_assets.RELEASE_PLATFORMS),
            "1" * 64,
        )

        def collect_git(*, provider: str, **_: object) -> dict[str, object]:
            return {"provider": provider, "tag": "v1.2.3", **git_evidence}

        def collect_hosted(*, repository: str, **_: object) -> dict[str, object]:
            return {
                "repository": repository,
                "ci": {
                    "id": 42,
                    "revision_oid": commit,
                    "status": "success",
                    "jobs": {"required": "success"},
                },
                "release": {
                    "id": 99,
                    "tag": "v1.2.3",
                    "commit_oid": commit,
                    "name": "Codex Responses Proxy v1.2.3",
                    "draft": False,
                    "prerelease": False,
                },
                "assets": assets,
            }

        mocker.patch.object(publication.git, "collect", side_effect=collect_git)
        mocker.patch.object(publication.gitlab, "collect", side_effect=collect_hosted)
        mocker.patch.object(publication.github, "collect", side_effect=collect_hosted)

        result = publication.verify(**VERIFY_ARGUMENTS)

        assert result["verified"] is True
        forges = result["forges"]
        assert isinstance(forges, Mapping)
        for forge in forges.values():
            assert isinstance(forge, Mapping)
            ci = forge["ci"]
            assert isinstance(ci, Mapping)
            assert set(ci) == {"id", "revision_oid", "status"}

    def test_publication_verifier_rejects_unverified_and_malformed_results(
        self, subtests, *, mocker
    ) -> None:
        identity = {
            "tag_object_oid": "a" * 40,
            "commit_oid": "b" * 40,
            "tree_oid": "c" * 40,
        }
        arguments = VERIFY_ARGUMENTS
        hosted = {
            "repository": "example/repository",
            "ci": {"id": 1, "revision_oid": "b" * 40, "status": "success"},
            "release": {},
            "assets": {},
        }
        for result, message in (
            ({"verified": False}, "did not verify"),
            ({"verified": True, "forges": []}, "malformed"),
        ):
            mocker.patch.object(publication.git, "collect", return_value=identity)
            mocker.patch.object(publication.gitlab, "collect", return_value=hosted)
            mocker.patch.object(publication.github, "collect", return_value=hosted)
            mocker.patch.object(
                publication.evaluator,
                "evaluate",
                side_effect=lambda *_args, result=result: result,
            )
            with (
                subtests.test(result=result),
                pytest.raises(publication.PublicationError, match=message),
            ):
                publication.verify(**arguments)

    def test_publication_evidence_is_deeply_frozen(self, *, mocker) -> None:
        evidence = verified_evidence(forge_evidence(items=[{"value": 1}]), mocker=mocker)
        forges = evidence["forges"]
        assert isinstance(forges, Mapping)
        gitlab = forges["gitlab"]
        assert isinstance(gitlab, Mapping)
        items = gitlab["items"]
        assert isinstance(items, tuple)
        item = items[0]
        assert isinstance(item, Mapping)
        with pytest.raises(TypeError):
            operator.setitem(item, "value", 2)

    def test_cli_serializes_frozen_publication_evidence(self) -> None:
        frozen = MappingProxyType(
            {
                "verified": True,
                "forges": MappingProxyType(
                    {"github": MappingProxyType({"ci": MappingProxyType({"id": 1})})}
                ),
            }
        )

        plain = publication_cli._plain(frozen)

        assert isinstance(plain, dict)
        assert type(plain) is dict
        assert plain == {
            "verified": True,
            "forges": {"github": {"ci": {"id": 1}}},
        }
        forges = plain["forges"]
        assert isinstance(forges, dict)
        assert type(forges) is dict
        github = forges["github"]
        assert type(github) is dict

    def test_cli_reports_stable_semantic_failure_reason(self, capsys, *, mocker) -> None:
        mocker.patch.object(
            publication_cli,
            "verify",
            side_effect=publication.PublicationError(
                "live publication evidence is unavailable or invalid",
                reasons=("gitlab.hosted_evidence_invalid",),
            ),
        )

        with pytest.raises(SystemExit) as failure:
            publication_cli._command(
                tag="v1.2.3",
                gitlab_git_url="https://gitlab.example/team/repository.git",
                gitlab_api_base="https://gitlab.example/api/v4",
                gitlab_repo="team/repository",
                github_git_url="https://github.example/team/repository.git",
                github_repo="team/repository",
                gitlab_anchor=Path("gitlab-anchor"),
                github_anchor=Path("github-anchor"),
                as_json=True,
            )

        assert failure.value.code == 1
        assert '"reasons":["gitlab.hosted_evidence_invalid"]' in capsys.readouterr().out

    def test_cli_invalid_tag_fails_without_echoing_secret_environment(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "tools.release.verify", "--tag", "latest"],
            capture_output=True,
            check=False,
            text=True,
            env={"PATH": "/usr/bin:/bin", "SECRET_TOKEN": "do-not-print"},
        )
        assert completed.returncode == 2
        assert "do-not-print" not in completed.stdout + completed.stderr

    def test_hosted_transport_resolves_tools_and_translates_failures(self, *, mocker) -> None:
        mocker.patch.object(hosted.shutil, "which", return_value=None)
        with pytest.raises(RuntimeError):
            hosted.executable("gh", RuntimeError)
        candidate = str(Path("native-tools", "gh").resolve())
        mocker.patch.object(hosted.shutil, "which", return_value=candidate)
        assert hosted.executable("gh", RuntimeError) == candidate

        completed = mocker.Mock(stdout='{"ok":true}')
        mocker.patch.object(hosted.subprocess, "run", return_value=completed)
        assert hosted.api_json(("gh", "api"), unavailable="offline", error_type=RuntimeError) == {
            "ok": True
        }
        bytes_completed = mocker.Mock(stdout=b"asset")
        mocker.patch.object(hosted.subprocess, "run", return_value=bytes_completed)
        assert (
            hosted.api_bytes(("gh", "api"), unavailable="offline", error_type=RuntimeError)
            == b"asset"
        )
        for failure in (OSError("missing"), subprocess.CalledProcessError(1, ["gh"])):
            mocker.patch.object(hosted.subprocess, "run", side_effect=failure)
            with pytest.raises(RuntimeError, match="offline"):
                hosted.api_json(("gh", "api"), unavailable="offline", error_type=RuntimeError)
            mocker.patch.object(hosted.subprocess, "run", side_effect=failure)
            with pytest.raises(RuntimeError, match="offline"):
                hosted.api_bytes(("gh", "api"), unavailable="offline", error_type=RuntimeError)
