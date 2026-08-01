#!/usr/bin/env python3
"""Pure contracts for dual-Forge publication proof evaluation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.release.publication import verification as publication
from codex_responses_proxy.release.publication import evaluator


def _policy() -> evaluator.PublicationPolicy:
    return publication.load_policy(ROOT / "tests" / "fixtures" / "publication-policy.toml")


def _forge(
    provider: str,
    *,
    repository: str,
    tag_object_oid: str,
    commit_oid: str,
    jobs: tuple[str, ...],
    tree: str = "c" * 40,
) -> dict[str, object]:
    return {
        "provider": provider,
        "repository": repository,
        "tag": "v1.2.3",
        "tag_object_oid": tag_object_oid,
        "commit_oid": commit_oid,
        "tree_oid": tree,
        "anchor_sha256": "f" * 64,
        "signature_verified": True,
        "assets": {
            "codex-responses-proxy-1.2.3.tar.gz": "1" * 64,
            "SHA256SUMS": "2" * 64,
        },
        "ci": {
            "id": 42,
            "revision_oid": commit_oid,
            "status": "success",
            "jobs": {name: "success" for name in jobs},
        },
        "release": {
            "id": 99,
            "tag": "v1.2.3",
            "commit_oid": commit_oid,
            "name": "Codex Responses Proxy v1.2.3",
            "draft": False,
            "prerelease": False,
        },
    }


def _gitlab_forge(*, tree: str = "c" * 40) -> dict[str, object]:
    return _forge(
        "gitlab",
        repository="example/gitlab",
        tag_object_oid="a" * 40,
        commit_oid="d" * 40,
        jobs=tuple(
            "verify-python-3.12 verify-python-3.13 verify-python-3.14 verify-release-metadata "
            "verify-release-tag verify-python-quality publish-gitlab-release".split()
        ),
        tree=tree,
    )


def _github_forge(*, tree: str = "c" * 40) -> dict[str, object]:
    return _forge(
        "github",
        repository="example/github",
        tag_object_oid="b" * 40,
        commit_oid="e" * 40,
        jobs=tuple(
            (
                "Python 3.12|Python 3.13|Python 3.14|Python 3.12 (Windows)|"
                "Python 3.13 (Windows)|Python 3.14 (Windows)|Governance and presentation|"
                "Python quality|Verify tag and publish record"
            ).split("|")
        ),
        tree=tree,
    )


class PublicationProofContracts(unittest.TestCase):
    """Admit only complete independent publications of one source tree."""

    def test_valid_proof_remains_evidence_only(self) -> None:
        result = evaluator.evaluate("v1.2.3", _gitlab_forge(), _github_forge(), _policy())
        self.assertTrue(result["verified"])
        self.assertTrue(result["tree_equal"])
        self.assertTrue(result["assets_equal"])
        self.assertNotIn("release_source", result)
        forges = cast(dict[str, dict[str, object]], result["forges"])
        self.assertEqual(forges["gitlab"]["provider"], "gitlab")
        self.assertEqual(forges["github"]["provider"], "github")
        self.assertEqual(result["reasons"], [])

    def test_empty_policy_and_unknown_fields_fail_closed(self) -> None:
        cases: tuple[tuple[evaluator.PublicationPolicy, bool, list[str]], ...] = (
            (
                evaluator.PublicationPolicy(gitlab_jobs=(), github_jobs=()),
                False,
                ["publication_policy_empty"],
            ),
            (_policy(), True, ["gitlab.invalid_evidence"]),
        )
        for policy, unexpected, reasons in cases:
            gitlab = _gitlab_forge()
            if unexpected:
                gitlab["unexpected"] = "value"
            result = evaluator.evaluate("v1.2.3", gitlab, _github_forge(), policy)
            with self.subTest(reasons=reasons):
                self.assertFalse(result["verified"])
                self.assertEqual(result["reasons"], reasons)

    def test_rejects_tree_mismatch_and_unverified_signature(self) -> None:
        gitlab = _gitlab_forge()
        github = _github_forge(tree="9" * 40)
        github["signature_verified"] = False
        result = evaluator.evaluate("v1.2.3", gitlab, github, _policy())
        self.assertFalse(result["verified"])
        self.assertFalse(result["tree_equal"])
        reasons = cast(list[str], result["reasons"])
        self.assertIn("tree_mismatch", reasons)
        self.assertIn("github.signature_unverified", reasons)

    def test_rejects_cross_forge_asset_mismatch(self) -> None:
        github = _github_forge()
        cast(dict[str, str], github["assets"])["SHA256SUMS"] = "9" * 64
        result = evaluator.evaluate("v1.2.3", _gitlab_forge(), github, _policy())
        self.assertFalse(result["verified"])
        self.assertFalse(result["assets_equal"])
        self.assertIn("asset_mismatch", cast(list[str], result["reasons"]))

    def test_rejects_wrong_ci_revision_missing_job_and_release_identity(self) -> None:
        gitlab = _gitlab_forge()
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
        result = evaluator.evaluate("v1.2.3", gitlab, _github_forge(), _policy())
        self.assertFalse(result["verified"])
        reasons = cast(list[str], result["reasons"])
        self.assertIn("gitlab.ci_revision_mismatch", reasons)
        self.assertIn("gitlab.ci_required_job_missing:verify-python-quality", reasons)
        self.assertIn("gitlab.release_draft", reasons)

    def test_invalid_shapes_and_all_semantic_mismatches_fail_closed(self) -> None:
        invalid = {
            "tag": "latest",
            "repository": "",
            "tag_object_oid": "not-an-oid",
            "anchor_sha256": "not-a-digest",
            "assets": {},
            "ci": [],
        }
        for field, value in invalid.items():
            evidence = _gitlab_forge()
            evidence[field] = value
            with self.subTest(field=field):
                self.assertIsNone(
                    evaluator._evaluate_forge(
                        "gitlab", "v1.2.3", evidence, _policy()["gitlab_jobs"]
                    )[0]
                )

        evidence = _gitlab_forge()
        cast(dict[str, object], evidence["assets"])["SHA256SUMS"] = "not-a-digest"
        self.assertIsNone(
            evaluator._evaluate_forge("gitlab", "v1.2.3", evidence, _policy()["gitlab_jobs"])[0]
        )

        evidence = _gitlab_forge()
        cast(dict[str, object], evidence["release"]).pop("name")
        self.assertIsNone(
            evaluator._evaluate_forge("gitlab", "v1.2.3", evidence, _policy()["gitlab_jobs"])[0]
        )

        evidence = _gitlab_forge()
        ci = cast(dict[str, object], evidence["ci"])
        release = cast(dict[str, object], evidence["release"])
        ci.update(status="failed", jobs={"verify-python-quality": "failed"})
        release.update(
            tag="v0.0.0",
            commit_oid="0" * 40,
            name="wrong",
            draft=True,
            prerelease=True,
        )
        result = evaluator.evaluate("v1.2.3", evidence, _github_forge(), _policy())
        reasons = cast(list[str], result["reasons"])
        for expected in (
            "gitlab.ci_not_successful",
            "gitlab.ci_required_job_not_successful:verify-python-quality",
            "gitlab.release_tag_mismatch",
            "gitlab.release_commit_mismatch",
            "gitlab.release_name_mismatch",
            "gitlab.release_prerelease",
        ):
            self.assertIn(expected, reasons)

        evidence = _gitlab_forge()
        cast(dict[str, object], evidence["ci"])["jobs"] = []
        self.assertIsNone(
            evaluator._evaluate_forge("gitlab", "v1.2.3", evidence, _policy()["gitlab_jobs"])[0]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
