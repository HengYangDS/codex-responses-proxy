#!/usr/bin/env python3
"""Offline Git-object and external-anchor publication contracts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.release.publication import git


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
        subprocess.run(
            ["git", "-C", self.repo, "config", "core.hooksPath", "/dev/null"], check=True
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
                "Codex Responses Proxy v1.2.3",
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
        evidence = git.collect(
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
        with self.assertRaises(git.GitProofError):
            git.collect(
                provider="gitlab", remote=str(self.remote), tag="v1.2.4", anchor=self.anchor
            )
        wrong = self.root / "wrong"
        wrong.write_text(
            "nobody@example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
        )
        with self.assertRaises(git.GitProofError):
            git.collect(provider="gitlab", remote=str(self.remote), tag="v1.2.3", anchor=wrong)

    def test_rejects_invalid_inputs_and_unavailable_tools(self) -> None:
        for provider, tag, anchor in (
            ("other", "v1.2.3", self.anchor),
            ("gitlab", "latest", self.anchor),
            ("gitlab", "v1.2.3", self.root / "missing"),
        ):
            with (
                self.subTest(provider=provider, tag=tag),
                self.assertRaises(git.GitProofError),
            ):
                git.collect(
                    provider=provider,
                    remote=str(self.remote),
                    tag=tag,
                    anchor=anchor,
                )
        for missing in ("ssh-keygen", "git"):
            with (
                mock.patch.object(
                    git.shutil,
                    "which",
                    side_effect=lambda name, missing=missing: (
                        None if name == missing else f"/{name}"
                    ),
                ),
                self.assertRaises(git.GitProofError),
            ):
                git.collect(
                    provider="gitlab", remote=str(self.remote), tag="v1.2.3", anchor=self.anchor
                )

    def test_environment_error_translation_and_ascii_boundary(self) -> None:
        with mock.patch.dict(
            git.os.environ,
            {"GIT_DIR": "foreign", "GIT_TERMINAL_PROMPT": "9"},
            clear=True,
        ):
            environment = git._git_environment()
        self.assertNotIn("GIT_DIR", environment)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

        self.assertNotIn("GIT_CONFIG_COUNT", environment)
        self.assertNotIn("credential.helper", environment.values())

        completed = SimpleNamespace(stdout=b"\xff")
        with (
            mock.patch.object(git, "_run", return_value=completed),
            self.assertRaisesRegex(git.GitProofError, "not ASCII"),
        ):
            git._output(("git",), {})

        with (
            mock.patch.object(
                git.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, ["git"]),
            ),
            self.assertRaisesRegex(git.GitProofError, "fetch, verification"),
        ):
            git.collect(
                provider="gitlab", remote=str(self.remote), tag="v1.2.3", anchor=self.anchor
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
