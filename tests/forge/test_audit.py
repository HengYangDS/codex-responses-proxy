"""Contracts for independent Forge lineage comparison."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tools.forge import audit
from tools.forge.audit import branches_for_audit
from tools.forge.audit import commits_from_continuity_base
from tools.forge.audit import continuity_base
from tools.forge.audit import shared_history_suffix


class ForgeAuditContracts:
    """Compare the current semantic lineage, not unrelated old prefixes."""

    def test_shared_suffix_accepts_different_provider_cutover_prefixes(self) -> None:
        assert shared_history_suffix(
            ["gitlab-only", "shared-one", "shared-two"],
            ["github-old", "github-only", "shared-one", "shared-two"],
        ) == ["shared-one", "shared-two"]

    def test_shared_suffix_rejects_different_current_tips(self) -> None:
        assert (
            shared_history_suffix(
                ["shared", "gitlab-tip"],
                ["shared", "github-tip"],
            )
            == []
        )

    def test_branch_inventory_follows_declared_repository_roles(self, tmp_path: Path) -> None:
        policy = tmp_path / "workspace.toml"
        policy.write_text(
            """\
[branch_roles]
release_branch = "stable"
accepted_branch = "integration"
candidate_branch = "candidate/integration"
work_branch_prefix = "work/"
proposal_branch_prefix = "proposal/"
""",
            encoding="utf-8",
        )

        assert branches_for_audit(policy) == (
            frozenset({"stable", "integration", "candidate/integration"}),
            frozenset({"stable", "integration"}),
        )

    def test_provenance_starts_at_the_exact_continuity_base(self) -> None:
        assert commits_from_continuity_base(
            ["tip", "successor", "continuity", "retired"], "continuity"
        ) == ["tip", "successor", "continuity"]

    def test_provenance_rejects_a_missing_continuity_base(self) -> None:
        with pytest.raises(RuntimeError, match="continuity base is not an ancestor"):
            commits_from_continuity_base(["tip", "parent"], "drifted")

    def test_audit_consumes_the_exact_provider_projection_receipt(self, tmp_path: Path) -> None:
        receipt = tmp_path / "gitlab.json"
        receipt.write_text(
            '{"provider":"gitlab","source_commit":"source",'
            '"projected_commit":"tip","continuity_source_base":"source",'
            '"continuity_projected_anchor":"anchor"}\n',
            encoding="utf-8",
        )

        assert continuity_base(receipt, "gitlab", "tip") == "anchor"

    def test_audit_rejects_a_projection_receipt_for_another_tip(self, tmp_path: Path) -> None:
        receipt = tmp_path / "gitlab.json"
        receipt.write_text(
            '{"provider":"gitlab","source_commit":"source",'
            '"projected_commit":"old-tip","continuity_source_base":"source",'
            '"continuity_projected_anchor":"anchor"}\n',
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError, match="projection receipt does not bind"):
            continuity_base(receipt, "gitlab", "current-tip")

    def test_release_evidence_fetches_all_provider_tags_once(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        clone = tmp_path / "repository"
        clone.mkdir()
        mocker.patch.object(audit.tempfile, "mkdtemp", return_value=str(tmp_path))

        def completed(*args: str, **_: object) -> audit.subprocess.CompletedProcess[str]:
            stdout = "a\trefs/tags/v2.0.39\nb\trefs/tags/v2.0.40\n" if "ls-remote" in args else ""
            return audit.subprocess.CompletedProcess(args, 0, stdout, "")

        run = mocker.patch.object(audit, "command", side_effect=completed)
        mocker.patch.object(audit, "remote_url", return_value="provider-url")
        mocker.patch.object(audit, "output", return_value="tree")
        mocker.patch.object(audit.shutil, "rmtree")

        evidence = audit.provider_release_evidence("origin", "gitlab", tmp_path / "anchor")

        assert set(evidence) == {"v2.0.39", "v2.0.40"}
        assert any(
            invocation.args == ("git", "-C", str(clone), "fetch", "--quiet", "--tags", "provider")
            for invocation in run.call_args_list
        )
        assert not any(
            "refs/tags/" in " ".join(invocation.args)
            for invocation in run.call_args_list
            if "fetch" in invocation.args
        )
