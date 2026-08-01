#!/usr/bin/env python3
"""Contracts for live dual-Forge provenance and historical tag evidence."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load_audit():
    spec = importlib.util.spec_from_file_location(
        "dual_forge_audit", ROOT / "tools" / "forge" / "audit.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load dual-Forge audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DualForgeAuditContracts(unittest.TestCase):
    def test_branch_provenance_requires_provider_email_and_trust(self) -> None:
        audit = load_audit()
        with tempfile.TemporaryDirectory() as directory:
            anchor = Path(directory) / "allowed-signers"
            anchor.write_text("anchor\n", encoding="utf-8")
            with (
                mock.patch.object(audit, "output", return_value="commit-a\ncommit-b"),
                mock.patch.object(audit, "command") as command,
            ):
                command.side_effect = [
                    mock.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                    mock.Mock(returncode=0),
                    mock.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                    mock.Mock(returncode=0),
                ]
                valid = audit.branch_provenance("main", anchor, "publisher@example.test")
                self.assertTrue(valid["all_commits_trusted"])
                self.assertTrue(valid["all_commits_use_provider_email"])
                self.assertEqual(valid["untrusted_commits"], [])

                command.side_effect = [
                    mock.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                    mock.Mock(returncode=0),
                    mock.Mock(stdout="other@example.test\npublisher@example.test\n"),
                    mock.Mock(returncode=1),
                ]
                invalid = audit.branch_provenance("main", anchor, "publisher@example.test")
                self.assertFalse(invalid["all_commits_trusted"])
                self.assertEqual(invalid["untrusted_commits"], ["commit-b"])
                self.assertFalse(invalid["all_commits_use_provider_email"])
                self.assertEqual(invalid["identity_mismatches"], ["commit-b"])

    def test_equal_tree_histories_with_distinct_commits_are_healthy(self) -> None:
        """Treat provider-specific commit OIDs as intended provenance, not drift."""

        audit = load_audit()
        trusted = {
            "commit_count": 2,
            "all_commits_trusted": True,
            "untrusted_commits": [],
            "all_commits_use_provider_email": True,
            "identity_mismatches": [],
        }
        tags = {"v2.0.0": {"tree": "tree-b", "signature": True}}
        with (
            mock.patch.object(
                audit,
                "live_main",
                side_effect=[
                    ("gitlab-b", "tree-b", ["tree-a", "tree-b"], trusted),
                    ("github-b", "tree-b", ["tree-a", "tree-b"], trusted),
                ],
            ),
            mock.patch.object(audit, "provider_release_evidence", side_effect=[tags, tags]),
            mock.patch.object(audit, "local_non_main_branches", return_value=[]),
            mock.patch.object(audit, "remote_branches", return_value=[]),
            mock.patch.object(audit, "output", return_value="worktree /repository"),
        ):
            result = audit.audit(
                gitlab_commit_anchor=Path("gitlab-commits"),
                github_commit_anchor=Path("github-commits"),
                gitlab_author_email="gitlab@example.test",
                github_author_email="github@example.test",
                gitlab_tag_anchor=Path("gitlab-tags"),
                github_tag_anchor=Path("github-tags"),
                gitlab_remote="origin",
                github_remote="github",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["main_commit_distinct"])
        self.assertTrue(result["main_tree_history_equal"])

    def test_detached_historical_tags_are_retained_with_relation_metadata(self) -> None:
        audit = load_audit()
        commands = []

        def command(*args, **kwargs):
            commands.append(args)
            result = mock.Mock(returncode=1 if "--is-ancestor" in args else 0, stdout="")
            if args[-2:] == ("provider", "v[0-9]*"):
                result.stdout = "a\trefs/tags/v1.0.0\n"
            return result

        with (
            mock.patch.object(audit, "command", side_effect=command),
            mock.patch.object(audit, "remote_url", return_value="remote"),
            mock.patch.object(audit, "output", return_value="tree"),
            mock.patch.object(audit.shutil, "rmtree"),
        ):
            evidence = audit.provider_release_evidence("origin", "gitlab", Path("allowed-signers"))
        self.assertIn("v1.0.0", evidence)
        self.assertFalse(evidence["v1.0.0"]["reachable_from_main"])
        self.assertTrue(any("--is-ancestor" in args for args in commands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
