"""Contracts for live dual-Forge provenance and historical tag evidence."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

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


class DualForgeAuditContracts:
    def test_branch_provenance_requires_provider_email_and_trust(self, *, mocker) -> None:
        audit = load_audit()
        with tempfile.TemporaryDirectory() as directory:
            anchor = Path(directory) / "allowed-signers"
            anchor.write_text("anchor\n", encoding="utf-8")
            mocker.patch.object(audit, "output", return_value="commit-a\ncommit-b")
            command = mocker.patch.object(audit, "command")
            command.side_effect = [
                mocker.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                mocker.Mock(returncode=0),
                mocker.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                mocker.Mock(returncode=0),
            ]
            valid = audit.branch_provenance("main", anchor, "publisher@example.test")
            assert valid["all_commits_trusted"]
            assert valid["all_commits_use_provider_email"]
            assert valid["untrusted_commits"] == []

            command.side_effect = [
                mocker.Mock(stdout="publisher@example.test\npublisher@example.test\n"),
                mocker.Mock(returncode=0),
                mocker.Mock(stdout="other@example.test\npublisher@example.test\n"),
                mocker.Mock(returncode=1),
            ]
            invalid = audit.branch_provenance("main", anchor, "publisher@example.test")
            assert not invalid["all_commits_trusted"]
            assert invalid["untrusted_commits"] == ["commit-b"]
            assert not invalid["all_commits_use_provider_email"]
            assert invalid["identity_mismatches"] == ["commit-b"]

    def test_equal_tree_histories_with_distinct_commits_are_healthy(self, *, mocker) -> None:
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
        mocker.patch.object(
            audit,
            "live_main",
            side_effect=[
                ("gitlab-b", "tree-b", ["tree-a", "tree-b"], trusted),
                ("github-b", "tree-b", ["tree-a", "tree-b"], trusted),
            ],
        )
        mocker.patch.object(audit, "provider_release_evidence", side_effect=[tags, tags])
        mocker.patch.object(audit, "local_non_main_branches", return_value=[])
        mocker.patch.object(audit, "remote_branches", return_value=[])
        mocker.patch.object(audit, "output", return_value="worktree /repository")
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
        assert result["ok"]
        assert result["main_commit_distinct"]
        assert result["main_tree_history_equal"]

    def test_detached_historical_tags_are_retained_with_relation_metadata(self, *, mocker) -> None:
        audit = load_audit()
        commands = []

        def command(*args, **kwargs):
            commands.append(args)
            result = mocker.Mock(returncode=1 if "--is-ancestor" in args else 0, stdout="")
            if args[-2:] == ("provider", "v[0-9]*"):
                result.stdout = "a\trefs/tags/v1.0.0\n"
            return result

        mocker.patch.object(audit, "command", side_effect=command)
        mocker.patch.object(audit, "remote_url", return_value="remote")
        mocker.patch.object(audit, "output", return_value="tree")
        mocker.patch.object(audit.shutil, "rmtree")
        evidence = audit.provider_release_evidence("origin", "gitlab", Path("allowed-signers"))
        assert "v1.0.0" in evidence
        assert not evidence["v1.0.0"]["reachable_from_main"]
        assert any("--is-ancestor" in args for args in commands)
