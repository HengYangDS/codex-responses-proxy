#!/usr/bin/env python3
"""Pure contracts for dual-Forge publication proof evaluation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import publication_proof
from platform_adapters import publication


def _policy() -> publication_proof.PublicationPolicy:
    value = publication.load_policy(ROOT / "packaging/release/publication-policy.toml")
    return {
        "gitlab_jobs": value["gitlab_jobs"],
        "github_jobs": value["github_jobs"],
    }


def _forge(provider: str, *, tree: str = "c" * 40) -> dict[str, object]:
    jobs = (
        [
            "verify-python-3.12",
            "verify-python-3.13",
            "verify-python-3.14",
            "verify-release-metadata",
            "verify-release-tag",
            "verify-python-quality",
            "publish-gitlab-release",
        ]
        if provider == "gitlab"
        else [
            "Python 3.12",
            "Python 3.13",
            "Python 3.14",
            "Python 3.12 (Windows)",
            "Python 3.13 (Windows)",
            "Python 3.14 (Windows)",
            "Governance and presentation",
            "Python quality",
            "Verify tag and publish record",
        ]
    )
    return {
        "provider": provider,
        "repository": f"example/{provider}",
        "tag": "v1.2.3",
        "tag_object_oid": ("a" if provider == "gitlab" else "b") * 40,
        "commit_oid": ("d" if provider == "gitlab" else "e") * 40,
        "tree_oid": tree,
        "anchor_sha256": "f" * 64,
        "signature_verified": True,
        "ci": {
            "id": 42,
            "revision_oid": ("d" if provider == "gitlab" else "e") * 40,
            "status": "success",
            "jobs": {name: "success" for name in jobs},
        },
        "release": {
            "id": 99,
            "tag": "v1.2.3",
            "commit_oid": ("d" if provider == "gitlab" else "e") * 40,
            "name": "Codex DMX Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
        },
    }


class PublicationProofContracts(unittest.TestCase):
    """Admit only complete independent publications of one source tree."""

    def test_valid_proof_remains_evidence_only(self) -> None:
        result = publication_proof.evaluate("v1.2.3", _forge("gitlab"), _forge("github"), _policy())
        self.assertTrue(result["verified"])
        self.assertTrue(result["tree_equal"])
        self.assertNotIn("release_source", result)
        forges = cast(dict[str, dict[str, object]], result["forges"])
        self.assertEqual(forges["gitlab"]["provider"], "gitlab")
        self.assertEqual(forges["github"]["provider"], "github")
        self.assertEqual(result["reasons"], [])

    def test_empty_caller_policy_cannot_bypass_required_jobs(self) -> None:
        result = publication_proof.evaluate(
            "v1.2.3",
            _forge("gitlab"),
            _forge("github"),
            {"gitlab_jobs": (), "github_jobs": ()},
        )
        self.assertFalse(result["verified"])
        self.assertEqual(result["reasons"], ["publication_policy_empty"])

    def test_rejects_tree_mismatch_and_unverified_signature(self) -> None:
        gitlab = _forge("gitlab")
        github = _forge("github", tree="9" * 40)
        github["signature_verified"] = False
        result = publication_proof.evaluate("v1.2.3", gitlab, github, _policy())
        self.assertFalse(result["verified"])
        self.assertFalse(result["tree_equal"])
        reasons = cast(list[str], result["reasons"])
        self.assertIn("tree_mismatch", reasons)
        self.assertIn("github.signature_unverified", reasons)

    def test_rejects_wrong_ci_revision_missing_job_and_release_identity(self) -> None:
        gitlab = _forge("gitlab")
        ci = gitlab["ci"]
        assert isinstance(ci, dict)
        typed_ci = cast(dict[str, object], ci)
        typed_ci["revision_oid"] = "0" * 40
        jobs = typed_ci["jobs"]
        assert isinstance(jobs, dict)
        cast(dict[str, object], jobs).pop("verify-python-quality")
        release = gitlab["release"]
        assert isinstance(release, dict)
        cast(dict[str, object], release)["draft"] = True
        result = publication_proof.evaluate("v1.2.3", gitlab, _forge("github"), _policy())
        self.assertFalse(result["verified"])
        reasons = cast(list[str], result["reasons"])
        self.assertIn("gitlab.ci_revision_mismatch", reasons)
        self.assertIn("gitlab.ci_required_job_missing:verify-python-quality", reasons)
        self.assertIn("gitlab.release_draft", reasons)

    def test_rejects_invalid_or_unknown_fields(self) -> None:
        gitlab = _forge("gitlab")
        gitlab["unexpected"] = "value"
        result = publication_proof.evaluate("v1.2.3", gitlab, _forge("github"), _policy())
        self.assertFalse(result["verified"])
        self.assertEqual(result["reasons"], ["gitlab.invalid_evidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
