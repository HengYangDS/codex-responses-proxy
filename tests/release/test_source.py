"""Executable contracts for released-source admission and opaque payload authority."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy.payload import source as payload_source
from codex_responses_proxy.release import admission as release_admission


def _git(repo: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        input=input_bytes,
        check=True,
        capture_output=True,
        env=release_admission._isolated_git_environment(),
    )
    return completed.stdout.strip()


def _git_blob(repo: Path, object_expression: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", object_expression],
        check=True,
        capture_output=True,
        env=release_admission._isolated_git_environment(),
    )
    return completed.stdout


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
        (root / "VERSION").write_bytes(f"{version}\n".encode())
        (root / "proxy").mkdir()
        (root / "proxy" / "runtime.py").write_bytes(b"print('released bytes')\n")
        (root / "bin").mkdir()
        executable = root / "bin" / "runner"
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
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

    def retag(self, *, version: str | None = None, lightweight: bool = False) -> None:
        tag = f"v{self.version}"
        _git(self.root, "tag", "-d", tag)
        if version is not None:
            (self.root / "VERSION").write_bytes(f"{version}\n".encode())
            _git(self.root, "add", "VERSION")
            _git(self.root, "commit", "-qm", "replacement release")
        if lightweight:
            _git(self.root, "tag", tag)
            return
        _git(
            self.root,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={self.ssh_keygen}",
            "-c",
            f"user.signingkey={self.key}",
            "tag",
            "-s",
            "-a",
            tag,
            "-m",
            "replacement release",
        )

    @property
    def paths(self) -> tuple[str, ...]:
        return ("VERSION", "proxy/runtime.py", "bin/runner")

    def admit(
        self,
        *,
        paths: tuple[str, ...] | None = None,
        anchor: Path | None = None,
        git_path: Path | str | None = None,
    ) -> payload_source.ReleasedPayload:
        payload_paths = paths or self.paths
        with mock.patch.object(release_admission.inventory, "SERVING_FILES", self.paths):
            return release_admission.admit(
                self.root,
                payload_paths=payload_paths,
                trust_anchor=anchor or self.anchor,
                git_path=git_path or Path(shutil.which("git") or "").resolve(),
                ssh_keygen_path=self.ssh_keygen,
            )


class ReleaseSourceCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repository = ReleasedRepository(self.base / "source")

    def assert_admission_error(self, message: str, **kwargs) -> None:
        self.assertRaisesRegex(
            release_admission.ReleaseSourceError,
            message,
            self.repository.admit,
            **kwargs,
        )


class TestReleaseSourceAdmission(ReleaseSourceCase):
    def test_fixture_git_blobs_do_not_depend_on_native_text_newlines(self) -> None:
        def write_crlf(path: Path, content: str, **_kwargs: object) -> int:
            return path.write_bytes(content.replace("\n", "\r\n").encode())

        with mock.patch.object(Path, "write_text", write_crlf):
            repository = ReleasedRepository(self.base / "crlf-host" / "source")

        self.assertEqual(_git_blob(repository.root, "HEAD:VERSION"), b"1.2.3\n")
        self.assertEqual(
            _git_blob(repository.root, "HEAD:proxy/runtime.py"),
            b"print('released bytes')\n",
        )

    def test_materializes_git_blobs_and_mints_exact_canonical_receipts(self) -> None:
        released = self.repository.admit()
        receipt = released.receipt
        sidecar = released.sidecar

        tag = "refs/tags/v1.2.3"
        expected = {
            "version": "1.2.3",
            "tag": tag,
            "tag_object_oid": _git(self.repository.root, "rev-parse", tag).decode(),
            "commit_oid": _git(self.repository.root, "rev-parse", f"{tag}^{{commit}}").decode(),
            "tree_oid": _git(self.repository.root, "rev-parse", f"{tag}^{{tree}}").decode(),
            "verification_scope": "signed-release-source",
            "serving_payload_sha256": sidecar["serving_payload_sha256"],
        }
        self.assertTrue(expected.items() <= receipt.items())
        self.assertNotIn("receipt_sha256", receipt)
        self.assertEqual(sidecar["receipt_sha256"], released.receipt_sha256)
        for entry, blob in zip(receipt["payload"], released.peek_blobs(), strict=True):
            expected = _git_blob(self.repository.root, f"{tag}^{{commit}}:{blob.path}")
            self.assertEqual(blob.content, expected)
            self.assertEqual(entry["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertRegex(entry["blob_oid"], r"^[0-9a-f]{40,64}$")
            self.assertIn(entry["mode"], ["100644", "100755"])

    def test_admission_refuses_dirty_checkout_before_and_after_object_reads(self) -> None:
        dirty_files = (
            (self.repository.root / "VERSION", "9.9.9\n"),
            (self.repository.root / "untracked", "not released\n"),
        )
        for path, content in dirty_files:
            with self.subTest(path=path.name):
                path.write_text(content, encoding="utf-8")
                self.assert_admission_error("clean checkout")
                if path.name == "VERSION":
                    path.write_text(f"{self.repository.version}\n", encoding="utf-8")
                else:
                    path.unlink()

        original_run = release_admission._run_git

        def dirty_after_identity(
            git: Path,
            repo: Path,
            arguments: tuple[str, ...],
        ) -> bytes:
            result = original_run(git, repo, arguments)
            if arguments == ("rev-parse", "--verify", "HEAD^{commit}"):
                (repo / "appeared-during-admission").write_text("dirty\n", encoding="utf-8")
            return result

        with (
            mock.patch.object(release_admission, "_run_git", dirty_after_identity),
            self.assertRaisesRegex(release_admission.ReleaseSourceError, "clean checkout"),
        ):
            self.repository.admit()

    def test_admission_refuses_clean_head_move_during_object_reads(self) -> None:
        original_run = release_admission._run_git
        moved = False

        def commit_after_object_format(
            git: Path,
            repo: Path,
            arguments: tuple[str, ...],
        ) -> bytes:
            nonlocal moved
            result = original_run(git, repo, arguments)
            if arguments == ("rev-parse", "--show-object-format") and not moved:
                moved = True
                (repo / "concurrent-clean-commit").write_text("new\n", encoding="utf-8")
                _git(repo, "add", "concurrent-clean-commit")
                _git(repo, "commit", "-qm", "concurrent clean commit")
            return result

        with (
            mock.patch.object(release_admission, "_run_git", commit_after_object_format),
            self.assertRaisesRegex(
                release_admission.ReleaseSourceError, "changed during admission"
            ),
        ):
            self.repository.admit()
        self.assertEqual(_git(self.repository.root, "status", "--porcelain=v1", "-z"), b"")

    def test_admission_refuses_final_clean_check_head_move(self) -> None:
        original_clean = release_admission.require_clean_checkout
        checks = 0

        def move_during_final_clean(repository, *, git_path):
            nonlocal checks
            original_clean(repository, git_path=git_path)
            checks += 1
            if checks == 2:
                repo = Path(repository)
                (repo / "move-after-final-status").write_text("new\n", encoding="utf-8")
                _git(repo, "add", "move-after-final-status")
                _git(repo, "commit", "-qm", "move after final status")

        with (
            mock.patch.object(
                release_admission,
                "require_clean_checkout",
                side_effect=move_during_final_clean,
            ),
            self.assertRaisesRegex(
                release_admission.ReleaseSourceError, "changed during admission"
            ),
        ):
            self.repository.admit()

    def test_reads_version_and_payload_from_tag_objects_not_worktree(self) -> None:
        released = self.repository.admit()
        version, runtime, _runner = released.peek_blobs()
        self.assertEqual((version.path, version.content), ("VERSION", b"1.2.3\n"))
        self.assertEqual(
            (runtime.path, runtime.content),
            ("proxy/runtime.py", b"print('released bytes')\n"),
        )

    def test_requires_strict_version_annotated_direct_head_tag_and_external_anchor(self) -> None:
        for message, mutation in (
            ("strict release SemVer", lambda repo: repo.retag(version="1.2.3-rc.1")),
            ("annotated tag", lambda repo: repo.retag(lightweight=True)),
            (
                "direct HEAD",
                lambda repo: (
                    (repo.root / "later").write_text("later\n", encoding="utf-8"),
                    _git(repo.root, "add", "later"),
                    _git(repo.root, "commit", "-qm", "later"),
                ),
            ),
        ):
            with self.subTest(message=message):
                repository = ReleasedRepository(self.base / message.replace(" ", "-") / "source")
                mutation(repository)
                self.assertRaisesRegex(
                    release_admission.ReleaseSourceError, message, repository.admit
                )
        self.assert_admission_error(
            "outside the repository", anchor=self.repository.root / "VERSION"
        )

    def test_rejects_untrusted_signature_and_requires_absolute_tools(self) -> None:
        unrelated = ReleasedRepository(self.base / "unrelated-source")
        self.assert_admission_error("No principal matched", anchor=unrelated.anchor)
        self.assert_admission_error("git path must be absolute", git_path="git")

    def test_rejects_noncanonical_payload_modes_symlinks_and_host_git_injection(self) -> None:
        for paths in [
            ("VERSION", "VERSION"),
            ("VERSION", "./proxy/runtime.py"),
            ("VERSION", "proxy/../VERSION"),
            ("VERSION", "/proxy/runtime.py"),
            ("VERSION", "C:/proxy/runtime.py"),
            ("VERSION", "C:proxy/runtime.py"),
            ("VERSION", "//server/share/runtime.py"),
        ]:
            with self.subTest(paths=paths):
                self.assert_admission_error("payload path", paths=paths)

        (self.repository.root / "link").symlink_to("VERSION")
        _git(self.repository.root, "add", "link")
        _git(self.repository.root, "commit", "-qm", "symlink payload")
        self.repository.retag()
        self.assert_admission_error("regular blob mode", paths=("VERSION", "link"))

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
            repository.admit()

    def test_source_git_never_executes_repo_local_fsmonitor(self) -> None:
        marker = self.base / "fsmonitor-ran"
        hook = self.base / "fsmonitor"
        hook.write_text(
            f"#!/bin/sh\ntouch {marker}\nprintf '0\\0'\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        _git(self.repository.root, "config", "core.fsmonitor", str(hook))

        self.repository.admit()

        self.assertFalse(marker.exists())

    def test_windows_reparse_contract_fails_closed(self) -> None:
        for metadata, message in (
            (SimpleNamespace(), "cannot safely prove"),
            (SimpleNamespace(st_file_attributes=0x400), "reparse point"),
        ):
            candidate = mock.Mock(parents=())
            candidate.lstat.return_value = metadata
            with (
                self.subTest(message=message),
                mock.patch.object(release_admission.os, "name", "nt"),
                self.assertRaisesRegex(release_admission.ReleaseSourceError, message),
            ):
                release_admission._assert_windows_no_reparse(candidate)


class TestOpaqueReleasedPayloadContract(ReleaseSourceCase):
    """Contract for the source-only, opaque released payload capability."""

    def test_admission_returns_opaque_immutable_blobs_without_stage_paths(self) -> None:
        released = self.repository.admit()

        self.assertFalse(hasattr(released, "stage_path"))
        self.assertFalse(hasattr(released, "receipt_path"))
        self.assertFalse(hasattr(released, "sidecar_path"))
        self.assertEqual(released.version, "1.2.3")
        self.assertEqual(
            released.serving_payload_sha256, released.receipt["serving_payload_sha256"]
        )
        with mock.patch.object(release_admission.inventory, "SERVING_FILES", self.repository.paths):
            blobs = payload_source.claim(released)[0]
        self.assertEqual(tuple(blob.path for blob in blobs), self.repository.paths)
        self.assertEqual(blobs[1].content, b"print('released bytes')\n")
        self.assertRaises((AttributeError, TypeError), setattr, blobs[1], "content", b"tampered")
        self.assertRaisesRegex(
            payload_source.PayloadSourceError, "immutable", setattr, released, "_claimed", False
        )
        with mock.patch.object(release_admission.inventory, "SERVING_FILES", self.repository.paths):
            self.assertRaisesRegex(
                payload_source.PayloadSourceError,
                "already claimed",
                payload_source.claim,
                released,
            )

    def test_clean_checkout_uses_exact_isolated_fail_closed_status_contract(self) -> None:
        git = Path(shutil.which("git") or "").resolve()
        with mock.patch.object(release_admission, "_git_bytes", return_value=b"") as run:
            release_admission.require_clean_checkout(self.repository.root, git_path=git)
        run.assert_called_once_with(
            git,
            self.repository.root.resolve(),
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        )

    def test_nested_receipt_and_sidecar_are_deeply_immutable(self) -> None:
        released = self.repository.admit()

        with self.assertRaises((AttributeError, TypeError)):
            released.receipt["payload"][0]["sha256"] = "0" * 64
        with self.assertRaises((AttributeError, TypeError)):
            cast("dict[str, object]", released.sidecar)["commit_oid"] = "0" * 40

    def test_claim_revalidates_receipt_sidecar_and_every_blob_binding(self) -> None:
        def replace_blob(released, **changes):
            blob = released.peek_blobs()[-1]
            replacement = payload_source.ReleasedBlob(
                path=cast(str, changes.get("path", blob.path)),
                mode=changes.get("mode", blob.mode),
                blob_oid=cast(str, changes.get("blob_oid", blob.blob_oid)),
                sha256=cast(str, changes.get("sha256", blob.sha256)),
                content=cast(bytes, changes.get("content", blob.content)),
            )
            object.__setattr__(released, "_blobs", (*released.peek_blobs()[:-1], replacement))

        mutations = {
            "receipt": lambda released: object.__setattr__(
                released, "_receipt", {**released.receipt, "version": "9.9.9"}
            ),
            "sidecar": lambda released: object.__setattr__(
                released,
                "_sidecar",
                {**released.sidecar, "receipt_sha256": "0" * 64},
            ),
            "path": lambda released: replace_blob(released, path="wrong"),
            "mode": lambda released: replace_blob(
                released,
                mode="100644" if released.peek_blobs()[-1].mode == "100755" else "100755",
            ),
            "blob_oid": lambda released: replace_blob(released, blob_oid="0" * 40),
            "sha256": lambda released: replace_blob(released, sha256="0" * 64),
            "content": lambda released: replace_blob(released, content=b"tampered"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                released = self.repository.admit()
                mutate(released)
                self.assertRaisesRegex(
                    payload_source.PayloadSourceError,
                    "integrity",
                    payload_source.claim,
                    released,
                )

    def test_source_helpers_reject_invalid_digest_paths_tools_and_encoding(self) -> None:
        self.assertRaisesRegex(
            release_admission.ReleaseSourceError,
            "serving payload files",
            release_admission.serving_payload_sha256,
            {"VERSION": "not-a-digest"},
        )
        for paths in ((), ("proxy/runtime.py",), ("VERSION", "")):
            with self.subTest(paths=paths), self.assertRaises(release_admission.ReleaseSourceError):
                release_admission._canonical_payload_paths(paths)

        non_executable = self.base / "not-executable"
        non_executable.write_text("no\n", encoding="utf-8")
        non_executable.chmod(0o600)
        native_windows_executable = self.base / "tool.EXE"
        native_windows_executable.write_bytes(b"MZ")
        metadata = native_windows_executable.lstat()
        directory = self.base / "directory.exe"
        directory.mkdir()
        with mock.patch.object(release_admission.os, "access", return_value=True):
            self.assertTrue(
                release_admission._is_executable_regular_file(
                    native_windows_executable, metadata, "nt"
                )
            )
            self.assertFalse(
                release_admission._is_executable_regular_file(
                    non_executable, non_executable.lstat(), "nt"
                )
            )
            self.assertFalse(
                release_admission._is_executable_regular_file(directory, directory.lstat(), "nt")
            )
        invalid_paths = (
            (
                "executable regular file",
                lambda: release_admission._absolute_executable(non_executable, "tool"),
            ),
            (
                "anchor path must be absolute",
                lambda: release_admission._external_regular_file(
                    "relative-anchor", self.repository.root
                ),
            ),
            (
                "regular non-symlink",
                lambda: release_admission._external_regular_file(self.base, self.repository.root),
            ),
        )
        for message, operation in invalid_paths:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(release_admission.ReleaseSourceError, message),
            ):
                operation()

        self.assertEqual(payload_source.plain_value(({1: "value"},)), [{"1": "value"}])
        with (
            mock.patch.object(release_admission, "_run_git", return_value=b"\xff"),
        ):
            self.assertRaisesRegex(
                release_admission.ReleaseSourceError,
                "not UTF-8",
                release_admission._git_text,
                Path("/git"),
                self.repository.root,
                ("rev-parse", "HEAD"),
            )
        self.assertRaisesRegex(
            release_admission.ReleaseSourceError,
            "VERSION blob is not UTF-8",
            release_admission._strict_version,
            b"\xff",
        )

    def test_tag_headers_and_reparse_walk_fail_closed(self) -> None:
        original = release_admission._git_bytes
        for replacement, message in (
            (b"object deadbeef\ntype commit\ntag v0.0.0\n", "embedded name"),
            (b"object deadbeef\ntype tree\ntag v1.2.3\n", "directly name a commit"),
        ):

            def git_bytes(git, repo, arguments, replacement=replacement):
                if arguments[:2] == ("cat-file", "tag"):
                    return replacement
                return original(git, repo, arguments)

            with (
                self.subTest(message=message),
                mock.patch.object(release_admission, "_git_bytes", side_effect=git_bytes),
                self.assertRaisesRegex(release_admission.ReleaseSourceError, message),
            ):
                self.repository.admit()

        candidate = mock.Mock()
        parent = mock.Mock()
        candidate.parents = (parent,)
        candidate.lstat.return_value = SimpleNamespace(st_file_attributes=0)
        parent.lstat.return_value = SimpleNamespace(st_file_attributes=0)
        with mock.patch.object(release_admission.os, "name", "nt"):
            release_admission._assert_windows_no_reparse(candidate)

    def test_source_git_failures_and_payload_authority_fail_closed(self) -> None:
        failures = (
            (
                subprocess.CalledProcessError(1, ["git"], stderr=b"fatal: unavailable\n"),
                "fatal: unavailable",
            ),
            (OSError("missing"), "missing"),
        )
        for failure, message in failures:
            with (
                self.subTest(message=message),
                mock.patch.object(release_admission.subprocess, "run", side_effect=failure),
                self.assertRaisesRegex(release_admission.ReleaseSourceError, message),
            ):
                release_admission._run_git(Path("/git"), self.repository.root, ("status",))

        self.assertRaisesRegex(
            payload_source.PayloadSourceError,
            "admitted ReleasedPayload",
            payload_source.claim,
            object(),
        )
        self.assertRaises(
            TypeError,
            payload_source.ReleasedPayload,
            blobs=(),
            receipt={},
            sidecar={},
        )
        self.assertFalse(hasattr(payload_source.ReleasedPayload, "_TOKEN"))
        self.assertFalse(hasattr(payload_source.ReleasedPayload, "_from_verified"))
        self.assertFalse(hasattr(payload_source, "_mint_released_payload"))

    def test_source_admission_rejects_payload_without_declared_serving_inventory(self) -> None:
        self.assertRaisesRegex(
            release_admission.ReleaseSourceError,
            "declared serving inventory",
            release_admission.admit,
            self.repository.root,
            payload_paths=self.repository.paths,
            trust_anchor=self.repository.anchor,
            git_path=Path(shutil.which("git") or "").resolve(),
            ssh_keygen_path=self.repository.ssh_keygen,
        )

    def test_claim_integrity_failure_does_not_consume_authority(self) -> None:
        released = self.repository.admit()
        original = released.sidecar
        object.__setattr__(
            released,
            "_sidecar",
            {**original, "receipt_sha256": "0" * 64},
        )
        self.assertRaises(payload_source.PayloadSourceError, payload_source.claim, released)
        object.__setattr__(released, "_sidecar", original)

        with mock.patch.object(release_admission.inventory, "SERVING_FILES", self.repository.paths):
            claimed = payload_source.claim(released)

        self.assertEqual(tuple(blob.path for blob in claimed[0]), self.repository.paths)


if __name__ == "__main__":
    unittest.main()
