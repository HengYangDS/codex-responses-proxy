#!/usr/bin/env python3
"""End-to-end contract from signed release source to finalized runtime projection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.payload import inventory  # noqa: E402
from codex_responses_proxy.payload import state as payload_state  # noqa: E402
from codex_responses_proxy.payload import source as payload_source  # noqa: E402
from codex_responses_proxy.release import admission as release_admission  # noqa: E402
from codex_responses_proxy.payload import projection as payload_projection
from codex_responses_proxy.payload import transaction as payload_transaction  # noqa: E402
from tests.deployment.fixtures import install_context  # noqa: E402


def _git_environment() -> dict[str, str]:
    """Return a deterministic Git environment isolated from host configuration."""

    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
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

        # A released checkout carries the runtime payload plus this exact
        # source-only pre-projection closure.
        self.source_only = set(inventory.SOURCE_INSTALL_FILES)
        self.assertTrue(
            self.source_only.isdisjoint(payload_projection.RUNTIME_PAYLOAD_FILES),
            "source-side installer files must not leak into the installed runtime",
        )
        for relative in (*payload_projection.RUNTIME_PAYLOAD_FILES, *self.source_only):
            source = ROOT / relative
            target = self.repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (self.repository / "VERSION").write_bytes(f"{self.version}\n".encode("ascii"))

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

    def test_source_only_plus_runtime_inventory_is_import_complete(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.repository / "codex_responses_proxy/commands/install.py"),
                "--help",
            ],
            cwd=self.base,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Install Codex Responses Proxy", completed.stdout)

    def test_policy_inventory_is_derived_from_the_provider_manifest(self) -> None:
        self.assertIn(
            "codex_responses_proxy/providers/policies/dmxapi.py",
            inventory.RUNTIME_FILES,
        )
        source = (ROOT / "codex_responses_proxy/payload/inventory.py").read_text(encoding="utf-8")
        self.assertNotIn('"codex_responses_proxy/providers/policies/dmxapi.py"', source)
        self.assertNotIn("import tomllib", source)
        self.assertIn("provider_registry.policy_module_names", source)

    def test_runtime_manifest_override_does_not_create_a_second_authority(self) -> None:
        override = self.base / "runtime-providers.toml"
        override.write_text(
            "version = 1\n[providers.adopter-gateway]\nbase_url = 'https://gateway.example/v1'\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["CODEX_RESPONSES_PROXY_PROVIDERS"] = str(override)

        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from codex_responses_proxy.payload import inventory; "
                "print('\\n'.join(inventory.POLICY_FILES))",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.strip(),
            "codex_responses_proxy/providers/policies/dmxapi.py",
        )
        source = (ROOT / "codex_responses_proxy/providers/registry.py").read_text(encoding="utf-8")
        self.assertNotIn("CODEX_RESPONSES_PROXY_PROVIDERS", source)

    def test_signed_release_projects_only_runtime_and_finalizes_provenance(self) -> None:
        admitted = release_admission.admit(
            self.repository,
            payload_paths=payload_projection.RUNTIME_PAYLOAD_FILES,
            trust_anchor=self.trust_anchor,
            git_path=self.git,
            ssh_keygen_path=self.ssh_keygen,
        )
        install = install_context(self.base / "host")
        transaction = payload_transaction.begin_transaction(install, admitted)

        transaction.commit_projection()

        install_root = Path(install.install_dir)
        expected_projection = set(payload_projection.RUNTIME_PAYLOAD_FILES) | {
            payload_projection.PAYLOAD_MANIFEST_FILENAME,
            payload_projection.RELEASE_RECEIPT_FILENAME,
        }
        actual_projection = {
            path.relative_to(install_root).as_posix()
            for path in install_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual_projection, expected_projection)
        for relative in self.source_only:
            self.assertFalse((install_root / relative).exists())

        receipt_path = install_root / payload_projection.RELEASE_RECEIPT_FILENAME
        manifest_path = Path(payload_projection.payload_manifest_path(install))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt, payload_source.plain_value(admitted.receipt))
        self.assertEqual(manifest["release"], self.version)
        self.assertEqual(set(manifest["files"]), set(payload_projection.RUNTIME_PAYLOAD_FILES))
        self.assertEqual(
            set(manifest["serving_files"]), set(payload_projection.SERVING_PAYLOAD_FILES)
        )
        self.assertEqual(manifest["release_receipt_sha256"], admitted.receipt_sha256)
        self.assertEqual(manifest["serving_payload_sha256"], admitted.serving_payload_sha256)
        ok, detail = payload_projection.verify_payload_manifest(install)
        self.assertTrue(ok, detail)

        journal = json.loads(Path(payload_state.journal_path(install)).read_text(encoding="utf-8"))

        runtime = {"pid": 1234, "accepting": True}
        transaction.finalize(runtime)

        state = json.loads(Path(payload_state.installed_path(install)).read_text(encoding="utf-8"))
        self.assertEqual(state["version"], self.version)
        self.assertEqual(state["receipt_sha256"], admitted.receipt_sha256)
        self.assertEqual(state["transaction_id"], journal["transaction_id"])
        self.assertEqual(state["runtime"], runtime)
        self.assertFalse(Path(payload_state.transaction_root(install)).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
