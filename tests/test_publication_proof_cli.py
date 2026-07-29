#!/usr/bin/env python3
"""Command-line and released-source mapping contracts for publication proof."""

from __future__ import annotations

import subprocess
import sys
import unittest
import copy
import pickle
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import publication_proof
from platform_adapters import publication, release_source
from tests.support.publication import verified_authority


class PublicationProofCliContracts(unittest.TestCase):
    """Keep output secret-free and directly consumable by source admission."""

    def test_evidence_projection_cannot_construct_publication_authority(self) -> None:
        policy = cast(
            publication_proof.PublicationPolicy,
            publication.load_policy(ROOT / "packaging/release/publication-policy.toml"),
        )

        def forge(provider: str) -> dict[str, object]:
            commit = ("a" if provider == "gitlab" else "b") * 40
            jobs = policy["gitlab_jobs"] if provider == "gitlab" else policy["github_jobs"]
            return {
                "provider": provider,
                "repository": f"owner/{provider}",
                "tag": "v1.2.3",
                "tag_object_oid": ("c" if provider == "gitlab" else "d") * 40,
                "commit_oid": commit,
                "tree_oid": "e" * 40,
                "anchor_sha256": "f" * 64,
                "signature_verified": True,
                "ci": {
                    "id": 1,
                    "revision_oid": commit,
                    "status": "success",
                    "jobs": {job: "success" for job in jobs},
                },
                "release": {
                    "id": 2,
                    "tag": "v1.2.3",
                    "commit_oid": commit,
                    "name": "Codex DMX Proxy v1.2.3",
                    "draft": False,
                    "prerelease": False,
                },
            }

        result = publication_proof.evaluate("v1.2.3", forge("gitlab"), forge("github"), policy)
        self.assertTrue(result["verified"])
        self.assertNotIn("release_source", result)
        self.assertFalse(hasattr(release_source, "ForgePublication"))
        self.assertFalse(hasattr(release_source, "PublicationProof"))
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
        identity = {
            "tag_object_oid": "a" * 40,
            "commit_oid": "b" * 40,
            "tree_oid": "c" * 40,
        }
        authority = verified_authority(
            {
                "verified": True,
                "tag": "v1.2.3",
                "forges": {
                    "gitlab": {"provider": "gitlab", **identity},
                    "github": {"provider": "github", **identity},
                },
            }
        )
        with self.assertRaises(Exception):
            copy.copy(authority)
        with self.assertRaises(Exception):
            copy.deepcopy(authority)
        with self.assertRaises(Exception):
            pickle.dumps(authority)

    def test_release_source_admission_requires_process_local_capability(self) -> None:
        fixture = ROOT / "tests" / "test_release_source.py"
        self.assertTrue(fixture.is_file())
        self.assertIn("PublishedRelease", release_source.admit.__annotations__["publication"])

    def test_cli_invalid_tag_fails_without_echoing_secret_environment(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify-publication-proof.py"), "--tag", "latest"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "SECRET_TOKEN": "do-not-print"},
        )
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("do-not-print", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
