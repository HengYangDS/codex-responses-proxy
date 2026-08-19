"""Contracts for exact product-object parity across optional Forge peers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.forge.audit import (
    branches_for_audit,
    exact_branch_parity,
    exact_tag_parity,
    remote_branch_oids,
)


def _run(*args: str, cwd: Path) -> str:
    environment = os.environ.copy()
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return subprocess.run(
        args,
        cwd=cwd,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _tags(oid: str) -> dict[str, dict[str, object]]:
    return {
        "v1.0.0": {
            "tag_object_oid": oid,
            "commit_oid": "commit",
            "tree_oid": "tree",
            "annotated": True,
            "signature_verified": True,
        }
    }


class TestForgeAuditContracts:
    """Require exact Git object equality rather than historical approximation."""

    def test_branch_parity_requires_one_oid_for_local_and_both_peers(self) -> None:
        common = {"main": "product", "dev": "product"}
        assert exact_branch_parity(common, common, common)
        assert not exact_branch_parity(common, common, {"main": "other", "dev": "other"})

    def test_tag_parity_requires_the_same_verified_annotated_object(self) -> None:
        assert exact_tag_parity(_tags("tag"), _tags("tag"), _tags("tag"))
        assert not exact_tag_parity(_tags("tag"), _tags("other"), _tags("tag"))
        unsigned = _tags("tag")
        unsigned["v1.0.0"]["signature_verified"] = False
        assert not exact_tag_parity(unsigned, unsigned, unsigned)

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

    def test_remote_branch_reader_requires_main_and_dev(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote.git"
        source = tmp_path / "source"
        _run("git", "init", "--bare", str(remote), cwd=tmp_path)
        _run("git", "init", "-b", "main", str(source), cwd=tmp_path)
        _run("git", "config", "user.name", "Test", cwd=source)
        _run("git", "config", "user.email", "test@example.test", cwd=source)
        (source / "README.md").write_text("test\n", encoding="utf-8")
        _run("git", "add", "README.md", cwd=source)
        _run("git", "commit", "-m", "test", cwd=source)
        _run("git", "remote", "add", "peer", str(remote), cwd=source)
        _run("git", "push", "peer", "main", cwd=source)

        with pytest.raises(RuntimeError, match="exact main and dev"):
            remote_branch_oids(source, "peer")

        _run("git", "push", "peer", "main:dev", cwd=source)
        oid = _run("git", "rev-parse", "HEAD", cwd=source)
        assert remote_branch_oids(source, "peer") == {"main": oid, "dev": oid}
