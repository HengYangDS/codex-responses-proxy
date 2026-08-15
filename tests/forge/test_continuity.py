"""Exact, append-only recovery contracts for Forge continuity checkpoints."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

from tests.forge.test_forward_only import (
    ForgeFixture,
    ProviderProjectionTests,
    run,
    ssh_agent,
)
from tools.forge.history import HistoryError, join_indexes_from_base


class ForgeContinuityContracts:
    """Resume one provider projection without reinterpreting its old trust epoch."""

    def setup_method(self) -> None:
        ProviderProjectionTests().setup_method()

    @staticmethod
    def fixture(root: Path) -> ForgeFixture:
        return ProviderProjectionTests().fixture(root)

    environment = staticmethod(ProviderProjectionTests.environment)

    def test_explicit_base_resumes_after_a_provider_checkpoint(self) -> None:
        """Append canonical successors to the exact observed provider tip."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            remote = fixture["github_remote"]
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                run(
                    sys.executable,
                    "-m",
                    "tools.forge.project",
                    "--provider",
                    "github",
                    "--publication-context",
                    str(fixture["context"]),
                    "--anchor",
                    str(fixture["github_anchor"]),
                    "--repository",
                    "owner/project",
                    cwd=source,
                    env=environment,
                )
                continuity_base = run("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
                projected_anchor = run(
                    "git", "rev-parse", "refs/heads/main", cwd=remote
                ).stdout.strip()
                (source / "accepted-one.txt").write_text("one\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", "accepted one", cwd=source)
                accepted_one = run("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
                checkpoint = self._provider_checkpoint(
                    root, fixture, accepted_one, projected_anchor, environment
                )
                (source / "accepted-two.txt").write_text("two\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", "accepted two", cwd=source)
                mapping = root / "continuity-map.json"
                run(
                    sys.executable,
                    "-m",
                    "tools.forge.project",
                    "--provider",
                    "github",
                    "--map-output",
                    str(mapping),
                    "--continuity-base",
                    continuity_base,
                    "--projected-anchor",
                    projected_anchor,
                    "--expect-remote-tip",
                    checkpoint,
                    "--publication-context",
                    str(fixture["context"]),
                    "--anchor",
                    str(fixture["github_anchor"]),
                    "--repository",
                    "owner/project",
                    cwd=source,
                    env=environment,
                )

            new_tip = run("git", "rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
            run("git", "merge-base", "--is-ancestor", checkpoint, new_tip, cwd=remote)
            assert (
                run("git", "rev-parse", "HEAD^{tree}", cwd=source).stdout.strip()
                == run("git", "rev-parse", "main^{tree}", cwd=remote).stdout.strip()
            )
            projection = json.loads(mapping.read_text(encoding="utf-8"))
            assert projection["continuity_source_base"] == continuity_base
            assert projection["continuity_projected_anchor"] == projected_anchor
            assert projection["base_projected_commit"] == checkpoint
            assert len(projection["created"]) == 2

    def test_explicit_base_rejects_changed_provider_tip(self) -> None:
        """Bind recovery to the exact provider tip observed before mutation."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture(root)
            source = fixture["source"]
            remote = fixture["github_remote"]
            with ssh_agent(root, fixture["gitlab_key"], fixture["github_key"]) as agent:
                environment = self.environment(fixture, agent)
                run(
                    sys.executable,
                    "-m",
                    "tools.forge.project",
                    "--provider",
                    "github",
                    "--publication-context",
                    str(fixture["context"]),
                    "--anchor",
                    str(fixture["github_anchor"]),
                    "--repository",
                    "owner/project",
                    cwd=source,
                    env=environment,
                )
                continuity_base = run("git", "rev-parse", "HEAD", cwd=source).stdout.strip()
                observed_tip = run("git", "rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
                (source / "successor.txt").write_text("successor\n", encoding="utf-8")
                run("git", "add", ".", cwd=source)
                run("git", "commit", "-qS", "-m", "successor", cwd=source)
                changed_tip = self._provider_checkpoint(
                    root, fixture, "HEAD", observed_tip, environment
                )
                result = run(
                    sys.executable,
                    "-m",
                    "tools.forge.project",
                    "--provider",
                    "github",
                    "--continuity-base",
                    continuity_base,
                    "--projected-anchor",
                    observed_tip,
                    "--expect-remote-tip",
                    observed_tip,
                    "--publication-context",
                    str(fixture["context"]),
                    "--anchor",
                    str(fixture["github_anchor"]),
                    "--repository",
                    "owner/project",
                    cwd=source,
                    check=False,
                    env=environment,
                )

            assert result.returncode != 0
            assert "provider tip changed after continuity observation" in result.stderr
            assert (
                changed_tip == run("git", "rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
            )

    @staticmethod
    def _provider_checkpoint(
        root: Path,
        fixture: ForgeFixture,
        accepted_commit: str,
        parent: str,
        environment: dict[str, str],
    ) -> str:
        """Create one signed provider-native checkpoint and advance its fixture remote."""

        checkout = root / f"provider-checkpoint-{len(tuple(root.glob('provider-checkpoint-*')))}"
        run("git", "clone", "-q", str(fixture["github_remote"]), str(checkout), cwd=root)
        run("git", "checkout", "-qB", "main", "origin/main", cwd=checkout)
        run("git", "config", "user.name", "GitHub Publisher", cwd=checkout)
        run("git", "config", "user.email", fixture["github_email"], cwd=checkout)
        run("git", "config", "gpg.format", "ssh", cwd=checkout)
        run("git", "config", "user.signingkey", str(fixture["github_key"]), cwd=checkout)
        source = fixture["source"]
        resolved = run("git", "rev-parse", accepted_commit, cwd=source).stdout.strip()
        run("git", "fetch", "-q", str(source), resolved, cwd=checkout)
        tree = run("git", "rev-parse", f"{resolved}^{{tree}}", cwd=checkout).stdout.strip()
        checkpoint = run(
            "git",
            "commit-tree",
            "-S",
            tree,
            "-p",
            parent,
            "-m",
            "provider checkpoint",
            cwd=checkout,
            env=environment,
        ).stdout.strip()
        run("git", "push", "-q", "origin", f"{checkpoint}:main", cwd=checkout)
        return checkpoint


class ForgeContinuityIndexContracts:
    """Constrain explicit recovery to the ordered suffix after its exact base."""

    def test_duplicate_fingerprints_before_base_do_not_block_successors(self) -> None:
        canonical = [
            ("duplicate", "canonical-old-one"),
            ("duplicate", "canonical-old-two"),
            ("base", "canonical-base"),
            ("next", "canonical-next"),
        ]
        projected = [
            ("duplicate", "provider-old-one"),
            ("duplicate", "provider-old-two"),
            ("base", "provider-base"),
            ("next", "provider-next"),
        ]

        anchor, mapping = join_indexes_from_base(canonical, projected, "canonical-base")

        assert anchor == "provider-base"
        assert mapping == [("canonical-next", "provider-next")]

    def test_duplicate_fingerprint_after_base_remains_ambiguous(self) -> None:
        canonical = [("base", "canonical-base"), ("next", "canonical-next")]
        projected = [
            ("base", "provider-base"),
            ("next", "provider-next-one"),
            ("next", "provider-next-two"),
        ]

        with pytest.raises(HistoryError, match="ambiguous provider history matches"):
            join_indexes_from_base(canonical, projected, "canonical-base")
