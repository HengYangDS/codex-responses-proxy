#!/usr/bin/env python3
"""End-to-end contract from signed release source to finalized runtime projection."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import payload, publication, release_source  # noqa: E402
from tests.support.publication import verified_authority  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402


def _git_environment() -> dict[str, str]:
    """Return a deterministic Git environment isolated from host configuration."""

    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("GIT_"):
            environment.pop(name)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _git(repository: Path, *arguments: str) -> str:
    """Run one isolated Git command and return stripped UTF-8 output."""

    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=_git_environment(),
    )
    return completed.stdout.strip()


class TestReleasedSourceProjectionPipeline(unittest.TestCase):
    """Exercise the real source-admission and payload-transaction implementations."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = self.base / "released-source"
        self.repository.mkdir()
        self.version = "9.8.7"
        self.git = Path(shutil.which("git") or "").resolve()
        ssh_keygen = shutil.which("ssh-keygen")
        if not self.git.is_file() or not ssh_keygen:
            self.skipTest("git and ssh-keygen are required")
        self.ssh_keygen = Path(ssh_keygen).resolve()
        self.key = self.base / "release-key"
        subprocess.run(
            [str(self.ssh_keygen), "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            capture_output=True,
        )
        principal = "release-pipeline@example.test"
        public_key = self.key.with_suffix(".pub").read_text(encoding="utf-8").strip()
        self.trust_anchor = self.base / "allowed-signers"
        self.trust_anchor.write_text(
            f'{principal} namespaces="git" {public_key}\n',
            encoding="utf-8",
        )

        source_only = {
            "install.py",
            "platform_adapters/deployment.py",
            "platform_adapters/release_source.py",
        }
        self.source_only = tuple(sorted(source_only.difference(payload.RUNTIME_PAYLOAD_FILES)))
        for relative in (*payload.RUNTIME_PAYLOAD_FILES, *self.source_only):
            source = ROOT / relative
            target = self.repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (self.repository / "VERSION").write_text(f"{self.version}\n", encoding="utf-8")

        _git(self.repository, "init", "-q", "-b", "main")
        _git(self.repository, "config", "user.name", "Release Pipeline Test")
        _git(self.repository, "config", "user.email", principal)
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-qm", "release fixture")
        _git(
            self.repository,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={self.ssh_keygen}",
            "-c",
            f"user.signingkey={self.key}",
            "tag",
            "-s",
            "-a",
            f"v{self.version}",
            "-m",
            f"Release v{self.version}",
        )

    def _publication(self) -> publication.PublishedRelease:
        tag = f"refs/tags/v{self.version}"
        tag_object = _git(self.repository, "rev-parse", tag)
        commit = _git(self.repository, "rev-parse", f"{tag}^{{commit}}")
        tree = _git(self.repository, "rev-parse", f"{tag}^{{tree}}")
        return verified_authority(
            {
                "schema_version": 1,
                "tag": f"v{self.version}",
                "verified": True,
                "tree_equal": True,
                "forges": {
                    "gitlab": {
                        "tag": f"v{self.version}",
                        "tag_object_oid": tag_object,
                        "commit_oid": commit,
                        "tree_oid": tree,
                        "anchor_sha256": hashlib.sha256(self.trust_anchor.read_bytes()).hexdigest(),
                        "signature_verified": True,
                    },
                    "github": {
                        "tag": f"v{self.version}",
                        "tag_object_oid": "f" * len(tag_object),
                        "commit_oid": "e" * len(commit),
                        "tree_oid": tree,
                        "anchor_sha256": "e" * 64,
                        "signature_verified": True,
                    },
                },
            }
        )

    def test_signed_release_projects_only_runtime_and_finalizes_provenance(self) -> None:
        admitted = release_source.admit(
            self.repository,
            payload_paths=payload.RUNTIME_PAYLOAD_FILES,
            serving_payload_paths=payload.SERVING_PAYLOAD_FILES,
            trust_anchor=self.trust_anchor,
            publication=self._publication(),
            git_path=self.git,
            ssh_keygen_path=self.ssh_keygen,
        )
        context = install_context(self.base / "host")
        transaction = payload.begin_transaction(context, admitted)

        transaction.commit_projection()

        install_root = Path(context.install_dir)
        expected_projection = {
            *payload.RUNTIME_PAYLOAD_FILES,
            payload.PAYLOAD_MANIFEST_FILENAME,
            payload.RELEASE_RECEIPT_FILENAME,
        }
        actual_projection = {
            path.relative_to(install_root).as_posix()
            for path in install_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual_projection, expected_projection)
        for relative in self.source_only:
            self.assertFalse((install_root / relative).exists())
        for relative in payload.RUNTIME_PAYLOAD_FILES:
            self.assertEqual(
                (install_root / relative).read_bytes(),
                (self.repository / relative).read_bytes(),
            )

        receipt_path = install_root / payload.RELEASE_RECEIPT_FILENAME
        manifest_path = Path(payload.payload_manifest_path(context))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt, admitted.receipt)
        self.assertEqual(
            hashlib.sha256(receipt_path.read_bytes()).hexdigest(), admitted.receipt_sha256
        )
        self.assertEqual(manifest["release"], self.version)
        self.assertEqual(set(manifest["files"]), set(payload.RUNTIME_PAYLOAD_FILES))
        self.assertEqual(set(manifest["serving_files"]), set(payload.SERVING_PAYLOAD_FILES))
        self.assertEqual(manifest["release_receipt_sha256"], admitted.receipt_sha256)
        self.assertEqual(manifest["serving_payload_sha256"], admitted.serving_payload_sha256)
        self.assertEqual(
            transaction.expected["manifest_sha256"],
            hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        )
        ok, detail = payload.verify_payload_manifest(context)
        self.assertTrue(ok, detail)

        journal = json.loads(
            Path(payload.transaction_journal_path(context)).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["state"], "committed")
        self.assertEqual(journal["version"], self.version)
        self.assertEqual(journal["receipt_sha256"], admitted.receipt_sha256)

        runtime = {"pid": 1234, "accepting": True}
        transaction.finalize(runtime)

        state = json.loads(
            Path(payload.installed_release_state_path(context)).read_text(encoding="utf-8")
        )
        self.assertEqual(state["version"], self.version)
        self.assertEqual(state["receipt_sha256"], admitted.receipt_sha256)
        self.assertEqual(state["transaction_id"], journal["transaction_id"])
        self.assertEqual(state["runtime"], runtime)
        self.assertFalse(Path(payload.payload_transaction_dir(context)).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
