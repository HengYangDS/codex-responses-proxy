"""Executable contracts for provider-specific, fully signed commit history."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REWRITER = ROOT / "scripts" / "rewrite-provider-history.py"


def command(*args: str, cwd: Path, input_text: str | None = None) -> str:
    """Run a fixture command and return stripped standard output."""

    return subprocess.check_output(args, cwd=cwd, input=input_text, text=True).strip()


class ProviderHistoryTests(unittest.TestCase):
    """Prove semantic preservation, identity convergence, and commit verification."""

    def test_rewriter_preserves_dag_semantics_and_signs_every_commit(self) -> None:
        """Rebuild a merge history without changing its trees, topology, messages, or dates."""

        with tempfile.TemporaryDirectory(prefix="codex-dmx-provider-history-") as temp:
            root = Path(temp)
            repository = root / "repository"
            key = root / "signing"
            allowed = root / "allowed-signers"
            command("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=root)
            public = " ".join(key.with_suffix(".pub").read_text().split()[:2])
            allowed.write_text(f'provider@example.test namespaces="git" {public}\n')
            command("git", "init", "-q", "-b", "main", str(repository), cwd=root)
            command("git", "config", "user.name", "Original One", cwd=repository)
            command("git", "config", "user.email", "one@example.test", cwd=repository)
            (repository / "base.txt").write_text("base\n")
            command("git", "add", ".", cwd=repository)
            command("git", "commit", "-qm", "base", cwd=repository)
            command("git", "checkout", "-qb", "topic", cwd=repository)
            (repository / "topic.txt").write_text("topic\n")
            command("git", "add", ".", cwd=repository)
            command("git", "commit", "-qm", "topic", cwd=repository)
            command("git", "checkout", "-q", "main", cwd=repository)
            command("git", "config", "user.name", "Original Two", cwd=repository)
            command("git", "config", "user.email", "two@example.test", cwd=repository)
            (repository / "main.txt").write_text("main\n")
            command("git", "add", ".", cwd=repository)
            command("git", "commit", "-qm", "main", cwd=repository)
            command("git", "merge", "--no-ff", "topic", "-m", "merge topic", cwd=repository)
            source_shape = command(
                "git",
                "log",
                "--reverse",
                "--topo-order",
                "--format=%T%x09%P%x09%aI%x09%cI%x09%s",
                "main",
                cwd=repository,
            )
            source_count = command("git", "rev-list", "--count", "main", cwd=repository)

            command(
                sys.executable,
                str(REWRITER),
                "--repository",
                str(repository),
                "--source-ref",
                "main",
                "--target-ref",
                "refs/heads/provider",
                "--name",
                "Provider",
                "--email",
                "provider@example.test",
                "--signing-key",
                str(key.with_suffix(".pub")),
                "--signing-program",
                "/usr/bin/ssh-keygen",
                "--allowed-signers",
                str(allowed),
                cwd=repository,
            )
            self.assertEqual(
                source_count, command("git", "rev-list", "--count", "provider", cwd=repository)
            )
            target_shape = command(
                "git",
                "log",
                "--reverse",
                "--topo-order",
                "--format=%T%x09%P%x09%aI%x09%cI%x09%s",
                "provider",
                cwd=repository,
            )
            source_lines = [line.split("\t") for line in source_shape.splitlines()]
            target_lines = [line.split("\t") for line in target_shape.splitlines()]
            self.assertEqual(
                [
                    (tree, len(parents.split()), author_date, commit_date, subject)
                    for tree, parents, author_date, commit_date, subject in source_lines
                ],
                [
                    (tree, len(parents.split()), author_date, commit_date, subject)
                    for tree, parents, author_date, commit_date, subject in target_lines
                ],
            )
            identities = command(
                "git", "log", "provider", "--format=%an%x09%ae%x09%cn%x09%ce", cwd=repository
            )
            self.assertEqual(
                {"Provider\tprovider@example.test\tProvider\tprovider@example.test"},
                set(identities.splitlines()),
            )
            for commit in command("git", "rev-list", "provider", cwd=repository).splitlines():
                subprocess.run(
                    (
                        "git",
                        "-c",
                        "gpg.format=ssh",
                        "-c",
                        f"gpg.ssh.allowedSignersFile={allowed}",
                        "verify-commit",
                        commit,
                    ),
                    cwd=repository,
                    check=True,
                    capture_output=True,
                )


if __name__ == "__main__":
    unittest.main()
