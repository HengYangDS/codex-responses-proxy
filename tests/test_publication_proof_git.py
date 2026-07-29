#!/usr/bin/env python3
"""Offline Git-object and external-anchor publication contracts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publication_proof_git


class GitPublicationContracts(unittest.TestCase):
    """Require an exact annotated tag verified by an external signer anchor."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.key = self.root / "signing"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", self.key], check=True)
        public = " ".join(self.key.with_suffix(".pub").read_text().split()[:2])
        self.anchor = self.root / "allowed-signers"
        self.anchor.write_text(
            f'release@example.test namespaces="git" {public}\n', encoding="utf-8"
        )
        subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "init", "-q", "-b", "main", self.repo],
            check=True,
        )
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "Release Test"], check=True)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "release@example.test"], check=True
        )
        (self.repo / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        subprocess.run(["git", "-C", self.repo, "add", "VERSION"], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "release"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "-c",
                "gpg.format=ssh",
                "-c",
                f"user.signingkey={self.key.with_suffix('.pub')}",
                "-c",
                "gpg.ssh.program=ssh-keygen",
                "tag",
                "-s",
                "-a",
                "v1.2.3",
                "-m",
                "Codex DMX Proxy v1.2.3",
            ],
            check=True,
        )
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        subprocess.run(
            ["git", "-C", self.repo, "push", "-q", self.remote, "main", "refs/tags/v1.2.3"],
            check=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_collects_exact_signed_tag_identity(self) -> None:
        evidence = publication_proof_git.collect(
            provider="gitlab", remote=str(self.remote), tag="v1.2.3", anchor=self.anchor
        )
        self.assertEqual(evidence["provider"], "gitlab")
        self.assertTrue(evidence["signature_verified"])
        self.assertEqual(len(cast(str, evidence["tag_object_oid"])), 40)
        self.assertEqual(len(cast(str, evidence["commit_oid"])), 40)
        self.assertEqual(len(cast(str, evidence["tree_oid"])), 40)

    def test_rejects_lightweight_tag_and_wrong_anchor(self) -> None:
        subprocess.run(["git", "-C", self.repo, "tag", "v1.2.4"], check=True)
        subprocess.run(
            ["git", "-C", self.repo, "push", "-q", self.remote, "refs/tags/v1.2.4"], check=True
        )
        with self.assertRaises(publication_proof_git.GitProofError):
            publication_proof_git.collect(
                provider="gitlab", remote=str(self.remote), tag="v1.2.4", anchor=self.anchor
            )
        wrong = self.root / "wrong"
        wrong.write_text(
            "nobody@example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
        )
        with self.assertRaises(publication_proof_git.GitProofError):
            publication_proof_git.collect(
                provider="gitlab", remote=str(self.remote), tag="v1.2.3", anchor=wrong
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
