#!/usr/bin/env python3
"""Evidence-only CLI and opaque live publication-authority contracts."""

from __future__ import annotations

import copy
import pickle
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.release import publication
from codex_dmx_proxy.release.publication import evaluator
from codex_dmx_proxy.release.publication import hosted
from codex_dmx_proxy.release import admission as release_admission
from tests.support.publication import VERIFY_ARGUMENTS, forge_evidence, verified_authority


class PublicationProofCliContracts(unittest.TestCase):
    """Keep output secret-free and incapable of minting source authority."""

    def test_publication_owner_imports_semantic_collaborators(self) -> None:
        self.assertIs(publication.evaluator, evaluator)

    def test_evidence_projection_cannot_construct_publication_authority(self) -> None:
        self.assertFalse(hasattr(release_admission, "ForgePublication"))
        self.assertFalse(hasattr(release_admission, "PublicationProof"))
        with self.assertRaises(TypeError):
            publication.PublishedRelease(evidence={})
        self.assertFalse(hasattr(publication.PublishedRelease, "_from_verified"))
        self.assertFalse(hasattr(publication, "_mint_verified"))

        forged = object.__new__(publication.PublishedRelease)
        object.__setattr__(forged, "_evidence", {})
        object.__setattr__(forged, "_consumed", False)
        with self.assertRaises(publication.PublicationError):
            publication.consume(forged)

    def test_publication_authority_cannot_be_copied_or_pickled(self) -> None:
        authority = verified_authority(forge_evidence())
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.subTest(operation=operation), self.assertRaises(Exception):
                operation(authority)

    def test_publication_policy_and_verifier_fail_closed_on_invalid_inputs(self) -> None:
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
                with self.subTest(name=name), self.assertRaises(publication.PublicationError):
                    publication.load_policy(path)
            with self.assertRaises(publication.PublicationError):
                publication.load_policy(root / "missing.toml")

        arguments = VERIFY_ARGUMENTS
        with (
            mock.patch.object(
                publication.git,
                "collect",
                side_effect=publication.git.GitProofError("offline"),
            ),
            mock.patch.object(
                publication,
                "load_policy",
                return_value={"gitlab_jobs": ("job",), "github_jobs": ("job",)},
            ),
            self.assertRaisesRegex(publication.PublicationError, "unavailable or invalid"),
        ):
            publication.verify(**arguments)

        with self.assertRaisesRegex(publication.PublicationError, "exact vMAJOR"):
            publication.verify(**{**arguments, "tag": "latest"})

    def test_publication_verifier_rejects_unverified_and_malformed_results(self) -> None:
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
            with (
                mock.patch.object(publication.git, "collect", return_value=identity),
                mock.patch.object(publication.gitlab, "collect", return_value={}),
                mock.patch.object(publication.github, "collect", return_value={}),
                mock.patch.object(
                    publication.evaluator,
                    "evaluate",
                    side_effect=lambda *_args, result=result: result,
                ),
                mock.patch.object(
                    publication,
                    "load_policy",
                    return_value={"gitlab_jobs": ("job",), "github_jobs": ("job",)},
                ),
                self.subTest(result=result),
                self.assertRaisesRegex(publication.PublicationError, message),
            ):
                publication.verify(**arguments)

    def test_publication_capability_is_immutable_and_evidence_is_deeply_frozen(self) -> None:
        authority = verified_authority(forge_evidence(items=[{"value": 1}]))
        with self.assertRaisesRegex(publication.PublicationError, "immutable"):
            authority.extra = "no"
        with self.assertRaises(TypeError):
            authority.evidence()["forges"]["gitlab"]["items"][0]["value"] = 2

    def test_cli_invalid_tag_fails_without_echoing_secret_environment(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify-publication-proof.py"), "--tag", "latest"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "SECRET_TOKEN": "do-not-print"},
        )
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("do-not-print", completed.stdout + completed.stderr)

    def test_hosted_transport_resolves_tools_and_translates_failures(self) -> None:
        with mock.patch.object(hosted.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                hosted.executable("gh", RuntimeError)
        candidate = str(Path("native-tools", "gh").resolve())
        with mock.patch.object(hosted.shutil, "which", return_value=candidate):
            self.assertEqual(hosted.executable("gh", RuntimeError), candidate)

        completed = mock.Mock(stdout='{"ok":true}')
        with mock.patch.object(hosted.subprocess, "run", return_value=completed):
            self.assertEqual(
                hosted.api_json(("gh", "api"), unavailable="offline", error_type=RuntimeError),
                {"ok": True},
            )
        for failure in (OSError("missing"), subprocess.CalledProcessError(1, ["gh"])):
            with (
                mock.patch.object(hosted.subprocess, "run", side_effect=failure),
                self.assertRaisesRegex(RuntimeError, "offline"),
            ):
                hosted.api_json(("gh", "api"), unavailable="offline", error_type=RuntimeError)


if __name__ == "__main__":
    unittest.main(verbosity=2)
