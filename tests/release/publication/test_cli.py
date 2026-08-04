"""Evidence-only CLI and opaque live publication-authority contracts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from tests.release.publication.fixtures import (
    VERIFY_ARGUMENTS,
    VerifyArguments,
    forge_evidence,
    verified_evidence,
)
from codex_responses_proxy.lifecycle import artifact
from tools.release.publication import evaluator, hosted
from tools.release.publication import verification as publication
import pytest

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

    def test_publication_policy_and_verifier_fail_closed_on_invalid_inputs(
        self, subtests, *, mocker
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {
                "unsupported-schema.toml": """
                    schema-version = 2
                    [gitlab]
                    required-jobs = ["job"]
                    [github]
                    required-jobs = ["job"]
                """,
                "duplicate-job.toml": """
                    schema-version = 1
                    [gitlab]
                    required-jobs = ["job", "job"]
                    [github]
                    required-jobs = ["job"]
                """,
            }
            for name, content in cases.items():
                path = root / name
                path.write_text(content, encoding="utf-8")
                with subtests.test(name=name), pytest.raises(publication.PublicationError):
                    publication.load_policy(path)
            with pytest.raises(publication.PublicationError):
                publication.load_policy(root / "missing.toml")

        arguments = VERIFY_ARGUMENTS
        mocker.patch.object(
            publication.git,
            "collect",
            side_effect=publication.git.GitProofError("offline"),
        )
        mocker.patch.object(
            publication,
            "load_policy",
            return_value={"gitlab_jobs": ("job",), "github_jobs": ("job",)},
        )
        with pytest.raises(publication.PublicationError, match="unavailable or invalid"):
            publication.verify(**arguments)

        invalid_tag: VerifyArguments = {**arguments, "tag": "latest"}
        with pytest.raises(publication.PublicationError, match="exact vMAJOR"):
            publication.verify(**invalid_tag)

    def test_publication_verifier_rejects_unverified_and_malformed_results(
        self, subtests, *, mocker
    ) -> None:
        identity = {
            "tag_object_oid": "a" * 40,
            "commit_oid": "b" * 40,
            "tree_oid": "c" * 40,
        }
        arguments = VERIFY_ARGUMENTS
        for result, message in (
            ({"verified": False}, "did not verify"),
            ({"verified": True, "forges": []}, "malformed"),
        ):
            mocker.patch.object(publication.git, "collect", return_value=identity)
            mocker.patch.object(publication.gitlab, "collect", return_value={})
            mocker.patch.object(publication.github, "collect", return_value={})
            mocker.patch.object(
                publication.evaluator,
                "evaluate",
                side_effect=lambda *_args, result=result: result,
            )
            mocker.patch.object(
                publication,
                "load_policy",
                return_value={"gitlab_jobs": ("job",), "github_jobs": ("job",)},
            )
            with (
                subtests.test(result=result),
                pytest.raises(publication.PublicationError, match=message),
            ):
                publication.verify(**arguments)

    def test_publication_evidence_is_deeply_frozen(self, *, mocker) -> None:
        evidence = verified_evidence(forge_evidence(items=[{"value": 1}]), mocker=mocker)
        with pytest.raises(TypeError):
            evidence["forges"]["gitlab"]["items"][0]["value"] = 2

    def test_cli_invalid_tag_fails_without_echoing_secret_environment(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "tools.release.verify", "--tag", "latest"],
            capture_output=True,
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
