"""Executable contract for released-source admission and sealed staging."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platform_adapters import publication as publication_authority
from platform_adapters import release_source
from tests.support.publication import verified_authority


def _isolated_git_env() -> dict[str, str]:
    """Return the same hostile-host isolation expected from production Git."""
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
    )
    for name in tuple(environment):
        if name.startswith("GIT_") and name not in {
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
            "GIT_OPTIONAL_LOCKS",
            "GIT_NO_REPLACE_OBJECTS",
        }:
            environment.pop(name)
    return environment


def _git(repo: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        input=input_bytes,
        check=True,
        capture_output=True,
        env=_isolated_git_env(),
    )
    return completed.stdout.strip()


def _git_blob(repo: Path, object_expression: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", object_expression],
        check=True,
        capture_output=True,
        env=_isolated_git_env(),
    )
    return completed.stdout


def _write_text(path: Path, content: str) -> None:
    """Write one fixture mutation while intentionally discarding its byte count."""
    path.write_text(content, encoding="utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    """Write one fixture mutation while intentionally discarding its byte count."""
    path.write_bytes(content)


def _authority(
    tag: str,
    gitlab_tag_object: str,
    gitlab_commit: str,
    tree: str,
    anchor: Path,
) -> publication_authority.PublishedRelease:
    """Mint test-only authority from already-verified fixture identity."""

    return verified_authority(
        {
            "schema_version": 1,
            "tag": tag,
            "verified": True,
            "tree_equal": True,
            "forges": {
                "gitlab": {
                    "tag": tag,
                    "tag_object_oid": gitlab_tag_object,
                    "commit_oid": gitlab_commit,
                    "tree_oid": tree,
                    "anchor_sha256": hashlib.sha256(anchor.read_bytes()).hexdigest(),
                    "signature_verified": True,
                },
                "github": {
                    "tag": tag,
                    "tag_object_oid": "d" * len(gitlab_tag_object),
                    "commit_oid": "e" * len(gitlab_commit),
                    "tree_oid": tree,
                    "anchor_sha256": "e" * 64,
                    "signature_verified": True,
                },
            },
        }
    )


class ReleasedRepository:
    """Small signed Git repository with an external trust anchor."""

    def __init__(self, root: Path, version: str = "1.2.3") -> None:
        self.root = root
        self.version = version
        root.parent.mkdir(parents=True, exist_ok=True)
        self.key = root.parent / f"{root.name}-release-signing-key"
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            raise unittest.SkipTest("ssh-keygen is unavailable")
        self.ssh_keygen = Path(ssh_keygen).resolve()
        subprocess.run(
            [str(self.ssh_keygen), "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            capture_output=True,
        )
        principal = "release@example.test"
        public_key = self.key.with_suffix(".pub").read_text(encoding="utf-8").strip()
        self.anchor = root.parent / f"{root.name}-trusted-allowed-signers"
        self.anchor.write_text(
            f'{principal} namespaces="git" {public_key}\n',
            encoding="utf-8",
        )
        root.mkdir()
        (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        (root / "proxy").mkdir()
        (root / "proxy" / "runtime.py").write_text(
            "print('released bytes')\n",
            encoding="utf-8",
        )
        (root / "bin").mkdir()
        executable = root / "bin" / "runner"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.name", "Release Test")
        _git(root, "config", "user.email", principal)
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "release")
        _git(
            root,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={self.ssh_keygen}",
            "-c",
            f"user.signingkey={self.key}",
            "tag",
            "-s",
            "-a",
            f"v{version}",
            "-m",
            f"Release v{version}",
        )

    @property
    def paths(self) -> tuple[str, ...]:
        return ("VERSION", "proxy/runtime.py", "bin/runner")

    def publication(self) -> publication_authority.PublishedRelease:
        tag = f"refs/tags/v{self.version}"
        tag_object = _git(self.root, "rev-parse", tag).decode()
        commit = _git(self.root, "rev-parse", f"{tag}^{{commit}}").decode()
        tree = _git(self.root, "rev-parse", f"{tag}^{{tree}}").decode()
        return _authority(f"v{self.version}", tag_object, commit, tree, self.anchor)

    def admit(self, workspace: Path | None = None) -> release_source.ReleasedPayload:
        del workspace
        return release_source.admit(
            self.root,
            payload_paths=self.paths,
            trust_anchor=self.anchor,
            publication=self.publication(),
            git_path=Path(shutil.which("git") or "").resolve(),
            ssh_keygen_path=self.ssh_keygen,
        )


class TestReleaseSourceAdmission(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = ReleasedRepository(self.base / "source")
        self.workspace = self.base / "private-transaction"

    def test_materializes_git_blobs_and_mints_exact_canonical_receipts(self) -> None:
        released = self.repository.admit(self.workspace)
        receipt = released.receipt
        sidecar = released.sidecar

        tag = "refs/tags/v1.2.3"
        self.assertEqual(receipt["version"], "1.2.3")
        self.assertEqual(receipt["tag"], tag)
        self.assertEqual(
            receipt["tag_object_oid"], _git(self.repository.root, "rev-parse", tag).decode()
        )
        self.assertEqual(
            receipt["commit_oid"],
            _git(self.repository.root, "rev-parse", f"{tag}^{{commit}}").decode(),
        )
        self.assertEqual(
            receipt["tree_oid"], _git(self.repository.root, "rev-parse", f"{tag}^{{tree}}").decode()
        )
        self.assertEqual(receipt["verification_scope"], "published-signed-release-source")
        self.assertEqual(receipt["serving_payload_sha256"], sidecar["serving_payload_sha256"])
        self.assertNotIn("receipt_sha256", receipt)
        self.assertEqual(sidecar["receipt_sha256"], released.receipt_sha256)
        for entry, blob in zip(receipt["payload"], released.peek_blobs(), strict=True):
            expected = _git_blob(self.repository.root, f"{tag}^{{commit}}:{blob.path}")
            self.assertEqual(blob.content, expected)
            self.assertEqual(entry["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertRegex(entry["blob_oid"], r"^[0-9a-f]{40,64}$")
            self.assertIn(entry["mode"], ["100644", "100755"])

    def test_reads_version_and_payload_from_tag_objects_not_worktree(self) -> None:
        original_run = release_source._run_git

        def mutate_after_identity(
            git: Path,
            repo: Path,
            arguments: tuple[str, ...],
        ) -> bytes:
            result = original_run(git, repo, arguments)
            if arguments == ("rev-parse", "--verify", "HEAD^{commit}"):
                (self.repository.root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
                (self.repository.root / "proxy" / "runtime.py").write_text(
                    "print('worktree tamper')\n",
                    encoding="utf-8",
                )
            return result

        with mock.patch.object(release_source, "_run_git", mutate_after_identity):
            released = self.repository.admit(self.workspace)
        blobs = {blob.path: blob.content for blob in released.peek_blobs()}
        self.assertEqual(blobs["VERSION"], b"1.2.3\n")
        self.assertEqual(blobs["proxy/runtime.py"], b"print('released bytes')\n")

    def test_requires_strict_version_annotated_direct_head_tag_and_external_anchor(self) -> None:
        cases: list[tuple[str, Callable[[], None]]] = [
            (
                "strict release SemVer",
                lambda: self._retag_version("1.2.3-rc.1"),
            ),
            (
                "annotated tag",
                self._replace_with_lightweight_tag,
            ),
            (
                "direct HEAD",
                self._commit_after_tag,
            ),
        ]
        for message, mutation in cases:
            with self.subTest(message=message):
                nested = self.base / message.replace(" ", "-")
                repository = ReleasedRepository(nested / "source")
                workspace = nested / "transaction"
                self.repository = repository
                mutation()
                with self.assertRaisesRegex(release_source.ReleaseSourceError, message):
                    repository.admit(workspace)

        with self.assertRaisesRegex(release_source.ReleaseSourceError, "outside the repository"):
            release_source.admit(
                self.repository.root,
                payload_paths=self.repository.paths,
                trust_anchor=self.repository.root / "VERSION",
                publication=self.repository.publication(),
                git_path=Path(shutil.which("git") or "").resolve(),
                ssh_keygen_path=self.repository.ssh_keygen,
            )

    def test_rejects_untrusted_signature_and_requires_absolute_tools(self) -> None:
        unrelated = ReleasedRepository(self.base / "unrelated-source")
        authority = self.repository.publication()
        with self.assertRaisesRegex(release_source.ReleaseSourceError, "trust anchor"):
            release_source.admit(
                self.repository.root,
                payload_paths=self.repository.paths,
                trust_anchor=unrelated.anchor,
                publication=authority,
                git_path=Path(shutil.which("git") or "").resolve(),
                ssh_keygen_path=self.repository.ssh_keygen,
            )
        with self.assertRaisesRegex(release_source.ReleaseSourceError, "git path must be absolute"):
            release_source.admit(
                self.repository.root,
                payload_paths=self.repository.paths,
                trust_anchor=self.repository.anchor,
                publication=self.repository.publication(),
                git_path="git",
                ssh_keygen_path=self.repository.ssh_keygen,
            )

    def test_rejects_noncanonical_payload_modes_symlinks_and_host_git_injection(self) -> None:
        for paths in [
            ("VERSION", "VERSION"),
            ("VERSION", "./proxy/runtime.py"),
            ("VERSION", "proxy/../VERSION"),
            ("VERSION", "/proxy/runtime.py"),
        ]:
            with (
                self.subTest(paths=paths),
                self.assertRaisesRegex(release_source.ReleaseSourceError, "payload path"),
            ):
                release_source.admit(
                    self.repository.root,
                    payload_paths=paths,
                    trust_anchor=self.repository.anchor,
                    publication=self.repository.publication(),
                    git_path=Path(shutil.which("git") or "").resolve(),
                    ssh_keygen_path=self.repository.ssh_keygen,
                )

        (self.repository.root / "link").symlink_to("VERSION")
        _git(self.repository.root, "add", "link")
        _git(self.repository.root, "commit", "-qm", "symlink payload")
        self._sign_current_tag()
        with self.assertRaisesRegex(release_source.ReleaseSourceError, "regular blob mode"):
            release_source.admit(
                self.repository.root,
                payload_paths=("VERSION", "link"),
                trust_anchor=self.repository.anchor,
                publication=self.repository.publication(),
                git_path=Path(shutil.which("git") or "").resolve(),
                ssh_keygen_path=self.repository.ssh_keygen,
            )

        environment = os.environ.copy()
        environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.sshCommand",
                "GIT_CONFIG_VALUE_0": "false",
                "GIT_OBJECT_DIRECTORY": str(self.base / "host-objects"),
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(self.base / "alternates"),
                "GIT_REPLACE_REF_BASE": "refs/evil",
            }
        )
        with mock.patch.dict(os.environ, environment, clear=True):
            isolated = self.base / "isolated"
            repository = ReleasedRepository(isolated / "source")
            repository.admit(isolated / "transaction")

    def test_windows_reparse_contract_fails_closed_when_attributes_are_unprovable(self) -> None:
        candidate = mock.Mock()
        candidate.parents = ()
        candidate.lstat.return_value = SimpleNamespace()
        with (
            mock.patch.object(release_source.os, "name", "nt"),
            self.assertRaisesRegex(release_source.ReleaseSourceError, "cannot safely prove"),
        ):
            release_source._assert_windows_no_reparse(candidate)

    def test_windows_reparse_contract_rejects_any_reparse_attribute(self) -> None:
        candidate = mock.Mock()
        candidate.parents = ()
        candidate.lstat.return_value = SimpleNamespace(st_file_attributes=0x400)
        with (
            mock.patch.object(release_source.os, "name", "nt"),
            self.assertRaisesRegex(release_source.ReleaseSourceError, "reparse point"),
        ):
            release_source._assert_windows_no_reparse(candidate)

    def _retag_version(self, version: str) -> None:
        (self.repository.root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        _git(self.repository.root, "add", "VERSION")
        _git(self.repository.root, "commit", "-qm", "non-release version")

    def _replace_with_lightweight_tag(self) -> None:
        _git(self.repository.root, "tag", "-d", f"v{self.repository.version}")
        _git(self.repository.root, "tag", f"v{self.repository.version}")

    def _commit_after_tag(self) -> None:
        (self.repository.root / "later").write_text("later\n", encoding="utf-8")
        _git(self.repository.root, "add", "later")
        _git(self.repository.root, "commit", "-qm", "later")

    def _sign_current_tag(self) -> None:
        _git(self.repository.root, "tag", "-d", f"v{self.repository.version}")
        _git(
            self.repository.root,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={self.repository.ssh_keygen}",
            "-c",
            f"user.signingkey={self.repository.key}",
            "tag",
            "-s",
            "-a",
            f"v{self.repository.version}",
            "-m",
            "replacement release",
        )


class TestOpaqueReleasedPayloadContract(unittest.TestCase):
    """Contract for the source-only, opaque released payload capability."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = ReleasedRepository(self.base / "source")

    def test_published_release_capability_is_opaque_and_single_use(self) -> None:
        with self.assertRaises(TypeError):
            publication_authority.PublishedRelease(evidence={})
        authority = self.repository.publication()
        release_source.admit(
            self.repository.root,
            payload_paths=self.repository.paths,
            trust_anchor=self.repository.anchor,
            publication=authority,
            git_path=Path(shutil.which("git") or "").resolve(),
            ssh_keygen_path=self.repository.ssh_keygen,
        )
        with self.assertRaisesRegex(publication_authority.PublicationError, "already consumed"):
            publication_authority.consume(authority)

    def test_admission_returns_opaque_immutable_blobs_without_stage_paths(self) -> None:
        local_tag = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3").decode()
        local_commit = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3^{commit}").decode()
        local_tree = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3^{tree}").decode()
        proof = _authority("v1.2.3", local_tag, local_commit, local_tree, self.repository.anchor)
        released = release_source.admit(
            self.repository.root,
            payload_paths=self.repository.paths,
            trust_anchor=self.repository.anchor,
            publication=proof,
            serving_payload_paths=self.repository.paths,
            git_path=Path(shutil.which("git") or "").resolve(),
            ssh_keygen_path=self.repository.ssh_keygen,
        )

        self.assertFalse(hasattr(released, "stage_path"))
        self.assertFalse(hasattr(released, "receipt_path"))
        self.assertFalse(hasattr(released, "sidecar_path"))
        self.assertEqual(released.version, "1.2.3")
        self.assertEqual(
            released.serving_payload_sha256, released.receipt["serving_payload_sha256"]
        )
        blobs = released.claim_blobs()
        self.assertEqual(tuple(blob.path for blob in blobs), self.repository.paths)
        self.assertEqual(blobs[1].content, b"print('released bytes')\n")
        with self.assertRaises((AttributeError, TypeError)):
            setattr(blobs[1], "content", b"tampered")
        with self.assertRaisesRegex(release_source.ReleaseSourceError, "already claimed"):
            released.claim_blobs()

    def test_admission_rejects_publication_identity_before_materializing_blobs(self) -> None:
        tag_object = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3").decode()
        commit = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3^{commit}").decode()
        tree = _git(self.repository.root, "rev-parse", "refs/tags/v1.2.3^{tree}").decode()
        proof = _authority("v1.2.3", "0" * len(tag_object), commit, tree, self.repository.anchor)
        with self.assertRaisesRegex(release_source.ReleaseSourceError, "GitLab.*tag object"):
            release_source.admit(
                self.repository.root,
                payload_paths=self.repository.paths,
                trust_anchor=self.repository.anchor,
                publication=proof,
                git_path=Path(shutil.which("git") or "").resolve(),
                ssh_keygen_path=self.repository.ssh_keygen,
            )


if __name__ == "__main__":
    unittest.main()
