"""Contracts for independent Forge lineage comparison."""

from __future__ import annotations

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
