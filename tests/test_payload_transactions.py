#!/usr/bin/env python3
"""Contracts for runtime payload construction and transactional replacement."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_dmx_proxy import installation  # noqa: E402
from codex_dmx_proxy import errors  # noqa: E402
from codex_dmx_proxy.release import admission as release_admission  # noqa: E402
from codex_dmx_proxy.release import inventory  # noqa: E402
from codex_dmx_proxy.release import projection as payload_projection  # noqa: E402
from codex_dmx_proxy.release import transaction as payload_transaction  # noqa: E402
from codex_dmx_proxy.listener import identity as listener_identity  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402
from tests.support.repository_fixtures import write_retired_projection  # noqa: E402


def released_fixture(version: str = "1.2.3") -> release_admission.ReleasedPayload:
    """Build a transaction candidate while tests remain below source admission."""

    def blob(relative: str) -> release_admission.ReleasedBlob:
        content = (
            f"{version}\n".encode() if relative == "VERSION" else (ROOT / relative).read_bytes()
        )
        return release_admission.ReleasedBlob(
            path=relative,
            mode="100644",
            blob_oid=hashlib.sha1(content).hexdigest(),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    blobs = tuple(map(blob, payload_projection.RUNTIME_PAYLOAD_FILES))
    serving = {
        item.path: item.sha256
        for item in blobs
        if item.path in payload_projection.SERVING_PAYLOAD_FILES
    }
    receipt = {
        "schema_version": 1,
        "version": version,
        "serving_payload_sha256": payload_projection.serving_payload_sha256(serving),
        "serving_files": list(payload_projection.SERVING_PAYLOAD_FILES),
        "payload": [
            dict(path=item.path, mode=item.mode, blob_oid=item.blob_oid, sha256=item.sha256)
            for item in blobs
        ],
    }
    candidate = mock.create_autospec(release_admission.ReleasedPayload, instance=True)
    candidate.peek_blobs.return_value = blobs
    candidate.receipt = receipt
    candidate.version = version
    candidate.receipt_sha256 = hashlib.sha256(
        release_admission.digest.canonical_json(receipt)
    ).hexdigest()
    return cast("release_admission.ReleasedPayload", candidate)


def begin_transaction(
    ctx: installation.InstallContext, candidate: release_admission.ReleasedPayload
) -> payload_transaction.PayloadTransaction:
    """Exercise transaction behavior with source claim patched at its authority boundary."""

    if not isinstance(candidate, release_admission.ReleasedPayload):
        return payload_transaction.begin_transaction(ctx, candidate)
    blobs = candidate.peek_blobs()
    receipt = candidate.receipt
    claimed = (blobs, candidate.version, candidate.receipt_sha256, receipt, {})
    with mock.patch.object(release_admission, "claim", return_value=claimed):
        return payload_transaction.begin_transaction(ctx, candidate)


class TestPayloadIdentity(unittest.TestCase):
    """Manifest and startup-frozen aggregate contracts over opaque payload bytes."""

    @staticmethod
    def _install(ctx: installation.InstallContext, version: str = "1.2.3") -> None:
        transaction = begin_transaction(ctx, released_fixture(version))
        transaction.commit_projection()
        transaction.finalize({"pid": 1})

    def test_transaction_installs_complete_runtime_and_manifest(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        manifest = json.loads(
            Path(payload_projection.payload_manifest_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(
            sorted(manifest["files"]), sorted(payload_projection.RUNTIME_PAYLOAD_FILES)
        )
        self.assertEqual(
            sorted(manifest["serving_files"]), sorted(payload_projection.SERVING_PAYLOAD_FILES)
        )
        self.assertEqual(
            manifest["serving_payload_sha256"],
            payload_projection.serving_payload_sha256(manifest["serving_files"]),
        )
        self.assertTrue(Path(ctx.install_dir, "control.py").is_file())
        self.assertTrue(Path(ctx.install_dir, "governance.py").is_file())

    def test_fixture_manifest_can_omit_receipt_identity(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        for blob in released_fixture().peek_blobs():
            target = Path(ctx.install_dir, blob.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.content)
        path = payload_projection._write_payload_manifest_for_fixture(ctx)
        self.assertNotIn("release_receipt_sha256", json.loads(Path(path).read_text()))
        self.assertTrue(payload_projection.verify_payload_manifest(ctx)[0])

    def test_manifest_detects_payload_and_aggregate_tampering(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        proxy = Path(ctx.proxy_script)
        proxy.write_bytes(proxy.read_bytes() + b"# tampered\n")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("hash mismatch", detail)

        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["serving_payload_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertEqual(detail, "serving payload aggregate mismatch")

    def test_committed_successor_identity_is_independent_of_the_old_loaded_release(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx, "1.2.3")

        committed = listener_identity.committed_payload(Path(ctx.proxy_script))

        self.assertIsNotNone(committed)
        assert committed is not None
        self.assertEqual(committed.release, "1.2.3")
        self.assertEqual(
            committed.handoff()["manifest_sha256"],
            hashlib.sha256(Path(ctx.install_dir, "payload-manifest.json").read_bytes()).hexdigest(),
        )

        Path(ctx.install_dir, "VERSION").write_text("1.2.4\n", encoding="utf-8")
        self.assertIsNone(listener_identity.committed_payload(Path(ctx.proxy_script)))

        Path(ctx.install_dir, "VERSION").write_text("1.2.3\n", encoding="utf-8")
        manifest_path = Path(ctx.install_dir, "payload-manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = (
            lambda value: value.__setitem__("schema_version", 1),
            lambda value: value.__setitem__("files", []),
            lambda value: value["files"].pop("control.py"),
            lambda value: value["serving_files"].pop("VERSION"),
            lambda value: value["files"].__setitem__("control.py", "0" * 64),
            lambda value: value["serving_files"].__setitem__("VERSION", "0" * 64),
            lambda value: value.__setitem__("release_receipt_sha256", "invalid"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                broken = json.loads(json.dumps(manifest))
                mutate(broken)
                manifest_path.write_text(json.dumps(broken), encoding="utf-8")
                self.assertIsNone(listener_identity.committed_payload(Path(ctx.proxy_script)))
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIsNone(listener_identity.committed_payload(Path(ctx.install_dir, "control.py")))

    def test_purge_unlinks_only_manifest_owned_payload_and_preserves_unknown_content(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        install = Path(ctx.install_dir)
        unknown = install / "operator-note.txt"
        unknown.write_text("keep\n", encoding="utf-8")

        remaining = payload_projection.purge_installed_projection(ctx)

        self.assertEqual(remaining, ("operator-note.txt",))
        self.assertEqual(unknown.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse(Path(payload_projection.payload_manifest_path(ctx)).exists())
        for relative in payload_projection.RUNTIME_PAYLOAD_FILES:
            self.assertFalse((install / relative).exists())

    def test_purge_rejects_manifest_claims_outside_historical_inventory(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        claimed = {
            "VERSION": b"1.0.8\n",
            "operator-note.txt": b"keep\n",
        }
        for relative, content in claimed.items():
            target = install / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest = {
            "schema_version": 1,
            "release": "1.0.8",
            "files": {
                relative: hashlib.sha256(content).hexdigest()
                for relative, content in claimed.items()
            },
        }
        (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_bytes(
            payload_transaction.digest.canonical_json(manifest)
        )

        with self.assertRaisesRegex(errors.InstallError, "file set is unsupported"):
            payload_projection.purge_installed_projection(ctx)
        self.assertEqual((install / "operator-note.txt").read_bytes(), b"keep\n")

    def test_purge_fails_closed_without_one_valid_manifest(self) -> None:
        for mutate, message in (
            (lambda _ctx: None, "manifest is required"),
            (
                lambda ctx: Path(payload_projection.payload_manifest_path(ctx)).symlink_to(
                    Path(ctx.install_dir, "VERSION")
                ),
                "manifest is a symlink",
            ),
        ):
            with self.subTest(message=message):
                ctx = install_context(Path(tempfile.mkdtemp()))
                marker = Path(ctx.install_dir, "VERSION")
                marker.parent.mkdir(parents=True)
                marker.write_text("1.2.3\n", encoding="utf-8")
                mutate(ctx)
                with self.assertRaisesRegex(errors.InstallError, message):
                    payload_projection.purge_installed_projection(ctx)
                self.assertTrue(marker.exists())

    def test_serving_payload_identity_is_order_independent_and_length_delimited(self) -> None:
        digests = {
            relative: hashlib.sha256(relative.encode("utf-8")).hexdigest()
            for relative in payload_projection.SERVING_PAYLOAD_FILES
        }
        reverse_order = dict(reversed(tuple(digests.items())))
        self.assertEqual(
            payload_projection.serving_payload_sha256(digests),
            payload_projection.serving_payload_sha256(reverse_order),
        )
        changed = dict(digests)
        changed[payload_projection.SERVING_PAYLOAD_FILES[-1]] = "0" * 64
        self.assertNotEqual(
            payload_projection.serving_payload_sha256(digests),
            payload_projection.serving_payload_sha256(changed),
        )

    def test_loaded_identity_freezes_release_aggregate_and_receipt_before_disk_changes(
        self,
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        script = """
import json
from pathlib import Path
from codex_dmx_proxy.listener import entrypoint
root = Path.cwd()
(root / "VERSION").write_text("9.9.9\\n", encoding="utf-8")
(root / "codex_dmx_proxy" / "listener" / "state.py").write_text("tampered = True\\n", encoding="utf-8")
print(json.dumps(entrypoint.runtime_status()))
"""
        completed = subprocess.run(
            [ctx.python, "-c", script],
            cwd=ctx.install_dir,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": ctx.install_dir},
        )
        runtime = json.loads(completed.stdout)
        manifest = json.loads(
            Path(payload_projection.payload_manifest_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(runtime["release"], "1.2.3")
        self.assertEqual(runtime["serving_payload_sha256"], manifest["serving_payload_sha256"])
        self.assertEqual(runtime["release_receipt_sha256"], manifest["release_receipt_sha256"])


class TestReceiptBoundPayloadTransaction(unittest.TestCase):
    """Contract for the only payload/receipt/state mutation boundary."""

    @staticmethod
    def _finalize(
        ctx: installation.InstallContext,
        version: str = "1.2.3",
    ) -> payload_transaction.PayloadTransaction:
        transaction = begin_transaction(ctx, released_fixture(version))
        transaction.commit_projection()
        transaction.finalize({"pid": 1})
        return transaction

    def test_begin_accepts_only_opaque_released_payload_not_a_raw_path(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        with self.assertRaises((TypeError, errors.InstallError)):
            begin_transaction(ctx, cast("release_admission.ReleasedPayload", str(ROOT)))

    def test_transaction_status_is_absent_without_a_journal(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self.assertIsNone(payload_transaction.transaction_status(ctx))

    def test_retired_security_boundaries(self) -> None:
        cases = (
            self._assert_current_manifest_is_verified,
            self._assert_pretty_legacy_manifest_is_accepted,
            self._assert_candidate_symlinks_are_rejected,
            self._assert_failed_snapshot_releases_transaction,
            self._assert_snapshot_paths_are_bounded,
        )
        for case in cases:
            with self.subTest(case=case.__name__):
                case()

    def _assert_current_manifest_is_verified(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local\n")
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["VERSION"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "hash mismatch"):
            transaction.commit_projection()
        self.assertEqual(unknown.read_bytes(), b"local\n")
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def _assert_pretty_legacy_manifest_is_accepted(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()
        self.assertFalse((install / "proxy/dmx_responses_proxy.py").exists())

    def _assert_candidate_symlinks_are_rejected(self) -> None:
        for boundary in ("install", "ancestor"):
            root = Path(tempfile.mkdtemp())
            ctx = install_context(root)
            external = root / "external"
            external.mkdir()
            install = Path(ctx.install_dir)
            if boundary == "install":
                install.parent.mkdir(parents=True)
                install.symlink_to(external, target_is_directory=True)
            else:
                install.mkdir(parents=True)
                (install / "codex_dmx_proxy").symlink_to(external, target_is_directory=True)
            transaction = begin_transaction(ctx, released_fixture())
            with self.assertRaisesRegex(errors.InstallError, "symlink"):
                transaction.commit_projection()
            self.assertEqual(tuple(external.iterdir()), ())

    def _assert_failed_snapshot_releases_transaction(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        marker = Path(ctx.install_dir, "proxy", "owned.py")
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"unowned\n")
        first = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "manifest is required"):
            first.commit_projection()
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())
        marker.unlink()
        marker.parent.rmdir()
        begin_transaction(ctx, released_fixture()).rollback()

    def _assert_snapshot_paths_are_bounded(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        rollback.mkdir(parents=True)
        for relative in ("unknown.py", "C:/escape.py", "//server/share.py"):
            snapshot = {
                "schema_version": 2,
                "present": {relative: {"sha256": "0" * 64, "mode": 0o644}},
                "retired": [],
                "retired_owned_sha256": payload_transaction._path_set_sha256(set()),
                "previous_owned": [],
            }
            (rollback / "snapshot.json").write_bytes(
                payload_transaction.digest.canonical_json(snapshot)
            )
            with self.assertRaisesRegex(errors.InstallError, "path|inventory"):
                payload_transaction._restore_rollback_snapshot(ctx, rollback)

    def test_retired_transaction_resists_races_and_unowned_collisions(self) -> None:
        cases = (
            self._assert_rollback_preflights_all_sources,
            self._assert_rollback_conflicting_retired_target_fails,
            self._assert_retired_unlink_revalidates_snapshot_digest,
            self._assert_retired_snapshot_binds_owned_manifest,
            self._assert_retired_directory_scan_errors_are_typed,
            self._assert_legacy_downgrade_is_refused,
            self._assert_candidate_collision_is_refused,
            self._assert_manifest_only_legacy_collision_is_refused,
        )
        for case in cases:
            with self.subTest(case=case.__name__):
                case()

    def _legacy_transaction(
        self, files: dict[str, bytes], *, version: str = "1.0.27"
    ) -> tuple[installation.InstallContext, payload_transaction.PayloadTransaction]:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        retired = write_retired_projection(ctx, version=version, schema=2)
        for relative, content in files.items():
            target = install / relative
            if relative not in retired:
                raise AssertionError(f"not a historical schema-2 path: {relative}")
            target.write_bytes(content)
        manifest = json.loads((install / payload_projection.PAYLOAD_MANIFEST_FILENAME).read_text())
        manifest["files"].update(
            {relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()}
        )
        (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return ctx, begin_transaction(ctx, released_fixture())

    def _assert_rollback_preflights_all_sources(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()
        live = Path(ctx.install_dir, "control.py")
        before = live.read_bytes()
        Path(payload_transaction.payload_transaction_dir(ctx), "rollback", "VERSION").unlink()
        with self.assertRaisesRegex(errors.InstallError, "rollback.*unavailable"):
            transaction.rollback()
        self.assertEqual(live.read_bytes(), before)

    def _assert_rollback_conflicting_retired_target_fails(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        transaction.commit_projection()
        conflict = Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py")
        conflict.parent.mkdir(parents=True, exist_ok=True)
        conflict.write_bytes(b"new unknown\n")
        with self.assertRaisesRegex(errors.InstallError, "conflicts"):
            transaction.rollback()
        self.assertEqual(conflict.read_bytes(), b"new unknown\n")

    def _assert_retired_unlink_revalidates_snapshot_digest(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        original = payload_transaction._write_rollback_snapshot

        def mutate_after_snapshot(context, rollback) -> None:
            original(context, rollback)
            Path(context.install_dir, "proxy", "dmx_responses_proxy.py").write_bytes(b"changed\n")

        with (
            mock.patch.object(
                payload_transaction, "_write_rollback_snapshot", side_effect=mutate_after_snapshot
            ),
            self.assertRaisesRegex(errors.InstallError, "changed after snapshot"),
        ):
            transaction.commit_projection()
        self.assertEqual(
            Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py").read_bytes(), b"changed\n"
        )

    def _assert_retired_snapshot_binds_owned_manifest(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        transaction.commit_projection()
        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        injected = rollback / "proxy" / "user.py"
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.write_bytes(b"injected\n")
        snapshot_path = rollback / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["present"]["proxy/user.py"] = {
            "sha256": hashlib.sha256(b"injected\n").hexdigest(),
            "mode": 0o644,
        }
        snapshot["retired"].append("proxy/user.py")
        snapshot_path.write_bytes(payload_transaction.digest.canonical_json(snapshot))
        with self.assertRaisesRegex(errors.InstallError, "owned proof"):
            transaction.rollback()
        self.assertFalse(Path(ctx.install_dir, "proxy", "user.py").exists())

    def _assert_retired_directory_scan_errors_are_typed(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        original = Path.rglob

        def fail_scan(path: Path, pattern: str):
            if path == Path(ctx.install_dir, "proxy"):
                raise OSError("blocked")
            return original(path, pattern)

        with (
            mock.patch.object(Path, "rglob", autospec=True, side_effect=fail_scan),
            self.assertRaisesRegex(errors.InstallError, "cleanup failed"),
        ):
            transaction.commit_projection()

    def _assert_legacy_downgrade_is_refused(self) -> None:
        _ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, version="9.9.9"
        )
        with self.assertRaisesRegex(errors.InstallError, "downgrade"):
            transaction.commit_projection()

    def _assert_candidate_collision_is_refused(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        collision = Path(ctx.install_dir, "codex_dmx_proxy", "errors.py")
        collision.parent.mkdir()
        collision.write_bytes(b"unknown\n")
        with self.assertRaisesRegex(errors.InstallError, "unowned collision"):
            transaction.commit_projection()
        self.assertEqual(collision.read_bytes(), b"unknown\n")

    def _assert_manifest_only_legacy_collision_is_refused(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        collision = install / "codex_dmx_proxy" / "errors.py"
        collision.parent.mkdir()
        collision.write_bytes(b"unknown\n")
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "unowned collision"):
            transaction.commit_projection()
        self.assertEqual(collision.read_bytes(), b"unknown\n")

    def test_retired_manifest_files_are_removed_without_touching_unknown_content(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        owned = write_retired_projection(ctx, schema=2)
        unknown = {
            "proxy/local.py": b"user proxy\n",
            "tests/fixtures/data.txt": b"user fixture\n",
        }
        for relative, content in unknown.items():
            target = install / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        retired_roots = {"platform_adapters", "proxy", "tests"}
        for relative in owned:
            if PurePosixPath(relative).parts[0] in retired_roots:
                self.assertFalse((install / relative).exists())
        for relative, content in unknown.items():
            self.assertEqual((install / relative).read_bytes(), content)

        transaction.rollback()

        for relative, content in owned.items():
            self.assertEqual((install / relative).read_bytes(), content)
        for relative, content in unknown.items():
            self.assertEqual((install / relative).read_bytes(), content)

    def test_retired_empty_directories_are_pruned_but_unknown_directories_remain(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        files = write_retired_projection(ctx, schema=2)
        owned = install / "proxy" / "dmx_responses_proxy.py"

        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        self.assertFalse((install / "proxy").exists())

        transaction.rollback()
        self.assertEqual(owned.read_bytes(), files["proxy/dmx_responses_proxy.py"])

    def test_retired_projection_requires_a_valid_manifest_before_mutation(self) -> None:
        cases = (
            (None, "manifest is required"),
            ({"schema_version": 99, "release": "1.0.27", "files": {}}, "unsupported"),
            (
                {
                    "schema_version": 1,
                    "release": "1.0.27",
                    "files": {"VERSION": "0" * 64},
                },
                "file set is unsupported",
            ),
        )
        for manifest, message in cases:
            with self.subTest(message=message):
                ctx = install_context(Path(tempfile.mkdtemp()))
                install = Path(ctx.install_dir)
                marker = install / "proxy" / "owned.py"
                marker.parent.mkdir(parents=True)
                marker.write_bytes(b"untouched\n")
                (install / "VERSION").write_bytes(b"1.0.27\n")
                if manifest is not None:
                    (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_bytes(
                        payload_transaction.digest.canonical_json(manifest)
                    )
                transaction = begin_transaction(ctx, released_fixture())
                with self.assertRaisesRegex(errors.InstallError, message):
                    transaction.commit_projection()
                self.assertEqual(marker.read_bytes(), b"untouched\n")

    def test_retired_manifest_rejects_noncanonical_paths_and_symlink_boundaries(self) -> None:
        invalid_paths = (
            "/proxy/owned.py",
            "../proxy/owned.py",
            "proxy/../owned.py",
            "proxy//owned.py",
            "proxy\\owned.py",
        )
        for relative in invalid_paths:
            with self.subTest(relative=relative):
                ctx = install_context(Path(tempfile.mkdtemp()))
                install = Path(ctx.install_dir)
                install.mkdir(parents=True)
                version = b"1.0.27\n"
                (install / "VERSION").write_bytes(version)
                manifest = {
                    "schema_version": 1,
                    "release": "1.0.27",
                    "files": {
                        "VERSION": hashlib.sha256(version).hexdigest(),
                        relative: hashlib.sha256(b"owned\n").hexdigest(),
                    },
                }
                (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_bytes(
                    payload_transaction.digest.canonical_json(manifest)
                )
                transaction = begin_transaction(ctx, released_fixture())
                with self.assertRaisesRegex(errors.InstallError, "path is not canonical"):
                    transaction.commit_projection()

        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        external = install.parent / "external"
        external.mkdir(parents=True)
        external_file = external / "dmx_responses_proxy.py"
        external_file.write_bytes(b"external\n")
        write_retired_projection(ctx, schema=2)
        for path in (install / "proxy").iterdir():
            path.unlink()
        (install / "proxy").rmdir()
        (install / "proxy").symlink_to(external, target_is_directory=True)
        manifest_path = install / payload_projection.PAYLOAD_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["proxy/dmx_responses_proxy.py"] = hashlib.sha256(
            b"external\n"
        ).hexdigest()
        manifest_path.write_bytes(payload_transaction.digest.canonical_json(manifest))
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "symlink"):
            transaction.commit_projection()
        self.assertEqual(external_file.read_bytes(), b"external\n")

    def test_privacy_cleanup_failure_refuses_before_transaction_or_live_payload_write(self) -> None:
        root = Path(tempfile.mkdtemp())
        ctx = install_context(root)
        log_root = Path(ctx.log_dir)
        log_root.mkdir(parents=True)
        capture = log_root / "reject-private.json"
        capture.write_bytes(b'{"input":"private request"}\n')
        install_root = Path(ctx.install_dir)
        install_root.mkdir(parents=True)
        marker = install_root / "VERSION"
        marker.write_bytes(b"existing live payload\n")
        original_unlink = Path.unlink

        def fail_capture_unlink(path: Path, *args, **kwargs) -> None:
            if path == capture:
                raise OSError("cleanup blocked")
            original_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_capture_unlink),
            self.assertRaisesRegex(errors.InstallError, "capture cleanup failed"),
        ):
            begin_transaction(ctx, released_fixture())

        self.assertEqual(marker.read_bytes(), b"existing live payload\n")
        self.assertTrue(capture.is_file())
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

        with (
            mock.patch.object(Path, "iterdir", autospec=True, side_effect=OSError("blocked")),
            self.assertRaisesRegex(errors.InstallError, "residue inventory failed"),
        ):
            begin_transaction(ctx, released_fixture())

    def test_fresh_commit_writes_manifest_receipt_and_pending_journal_then_finalize_state(
        self,
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_fixture())

        transaction.commit_projection()

        self.assertTrue(Path(ctx.install_dir, "payload-manifest.json").is_file())
        self.assertTrue(
            Path(ctx.install_dir, payload_projection.RELEASE_RECEIPT_FILENAME).is_file()
        )
        journal = json.loads(
            Path(payload_transaction.transaction_journal_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["state"], "committed")
        self.assertFalse(Path(payload_transaction.installed_release_state_path(ctx)).exists())

        transaction.finalize({"pid": 123, "accepting": True})

        state = json.loads(
            Path(payload_transaction.installed_release_state_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(state["version"], "1.2.3")
        self.assertEqual(state["receipt_sha256"], transaction.receipt_sha256)
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def test_failed_commit_rolls_back_before_propagating(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        before = Path(ctx.install_dir, "VERSION").read_bytes()
        transaction = begin_transaction(ctx, released_fixture())
        with (
            mock.patch.object(
                payload_projection,
                "verify_payload_manifest",
                return_value=(False, "tampered"),
            ),
            self.assertRaisesRegex(errors.InstallError, "integrity check failed"),
        ):
            transaction.commit_projection()
        self.assertEqual(Path(ctx.install_dir, "VERSION").read_bytes(), before)
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def test_upgrade_rollback_restores_payload_receipt_and_installed_state_exactly(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        before = {
            relative: Path(ctx.install_dir, relative).read_bytes()
            for relative in (
                *payload_projection.RUNTIME_PAYLOAD_FILES,
                payload_projection.PAYLOAD_MANIFEST_FILENAME,
                payload_projection.RELEASE_RECEIPT_FILENAME,
            )
        }
        before_state = Path(payload_transaction.installed_release_state_path(ctx)).read_bytes()

        second = begin_transaction(ctx, released_fixture("1.2.3"))
        second.commit_projection()
        second.rollback()

        for relative, content in before.items():
            self.assertEqual(Path(ctx.install_dir, relative).read_bytes(), content)
        self.assertEqual(
            Path(payload_transaction.installed_release_state_path(ctx)).read_bytes(), before_state
        )
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def test_upgrade_rollback_preserves_unknown_retired_content(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local content\n")

        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()
        self.assertEqual(unknown.read_bytes(), b"local content\n")
        transaction.rollback()

        self.assertEqual(unknown.read_bytes(), b"local content\n")

    def test_replay_and_downgrade_are_rejected_before_any_live_write(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx)
        marker = Path(ctx.install_dir, "VERSION").read_bytes()

        for version, message in (("1.2.3", "replay"), ("1.2.2", "downgrade")):
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(errors.InstallError, message),
            ):
                begin_transaction(ctx, released_fixture(version))
            self.assertEqual(Path(ctx.install_dir, "VERSION").read_bytes(), marker)
            self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def test_preserve_for_recovery_keeps_journal_and_rollback_visible(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        transaction = begin_transaction(ctx, released_fixture("1.2.3"))
        transaction.commit_projection()

        transaction.preserve_for_recovery("handoff outcome unknown")

        journal = json.loads(
            Path(payload_transaction.transaction_journal_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["state"], "recovery_required")
        self.assertEqual(journal["reason"], "handoff outcome unknown")
        self.assertTrue(Path(payload_transaction.payload_transaction_dir(ctx), "rollback").is_dir())

    def test_recovery_rollback_restores_previous_projection_and_removes_hold(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        previous = Path(ctx.install_dir, "VERSION").read_bytes()
        candidate = begin_transaction(ctx, released_fixture("1.2.3"))
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        previous_identity = listener_identity.committed_payload(rollback / inventory.ENTRYPOINT)
        candidate_identity = listener_identity.committed_payload(Path(ctx.proxy_script))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = {
            **previous_identity.handoff(),
            "payload_manifest_sha256": candidate_identity.manifest_sha256,
            "accepting": True,
            "handoff_state": "idle",
        }
        runtime.pop("manifest_sha256")

        result = payload_transaction.rollback_recovery(ctx, runtime=runtime)

        self.assertEqual(result["state"], "rolled_back")
        self.assertEqual(Path(ctx.install_dir, "VERSION").read_bytes(), previous)
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

        invalid = (
            {},
            {
                "schema_version": 0,
                "state": "recovery_required",
                "transaction_id": "x",
                "version": "1.2.3",
            },
            {
                "schema_version": 1,
                "state": "committed",
                "transaction_id": "x",
                "version": "1.2.3",
            },
            {
                "schema_version": 1,
                "state": "recovery_required",
                "transaction_id": 1,
                "version": "1.2.3",
            },
            {
                "schema_version": 1,
                "state": "recovery_required",
                "transaction_id": "x",
                "version": 1,
            },
        )
        for journal in invalid:
            with self.subTest(journal=journal):
                root = Path(payload_transaction.payload_transaction_dir(ctx))
                root.mkdir()
                Path(payload_transaction.transaction_journal_path(ctx)).write_bytes(
                    payload_transaction.digest.canonical_json(journal)
                )
                with self.assertRaisesRegex(errors.InstallError, "unavailable or invalid"):
                    payload_transaction.rollback_recovery(ctx, runtime=runtime)
                for path in sorted(root.rglob("*"), reverse=True):
                    path.unlink() if path.is_file() else path.rmdir()
                root.rmdir()

        candidate = begin_transaction(ctx, released_fixture("1.2.3"))
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        root = Path(payload_transaction.payload_transaction_dir(ctx))
        rollback = root / "rollback"
        previous_identity = listener_identity.committed_payload(rollback / inventory.ENTRYPOINT)
        candidate_identity = listener_identity.committed_payload(Path(ctx.proxy_script))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = {
            **previous_identity.handoff(),
            "payload_manifest_sha256": candidate_identity.manifest_sha256,
            "accepting": True,
            "handoff_state": "idle",
        }
        runtime.pop("manifest_sha256")
        with self.assertRaisesRegex(errors.InstallError, "does not match"):
            payload_transaction.rollback_recovery(
                ctx,
                runtime={**runtime, "release": "wrong"},
            )
        candidate_version = Path(ctx.install_dir, "VERSION")
        candidate_bytes = candidate_version.read_bytes()
        candidate_version.write_bytes(b"tampered\n")
        with self.assertRaisesRegex(errors.InstallError, "candidate projection identity"):
            payload_transaction.rollback_recovery(ctx, runtime=runtime)
        candidate_version.write_bytes(candidate_bytes)
        (root / "rollback" / "VERSION").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(errors.InstallError, "runtime identity is invalid"):
            payload_transaction.rollback_recovery(ctx, runtime=runtime)
        self.assertTrue(root.exists())

    def test_transaction_status_projects_only_the_read_only_recovery_contract(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._finalize(ctx, "1.2.2")
        transaction = begin_transaction(ctx, released_fixture("1.2.3"))
        transaction.commit_projection()
        transaction.preserve_for_recovery("handoff outcome unknown")
        journal_path = Path(payload_transaction.transaction_journal_path(ctx))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal.update(
            {
                "authorization": "Bearer secret-token",
                "request_body": {"input": "private request"},
                "stage_path": "/private/release-stage",
                "reason": (
                    "handoff unknown; Authorization=Bearer secret-token; "
                    "body=private request; stage=/private/release-stage"
                ),
            }
        )
        journal_path.write_bytes(payload_transaction.digest.canonical_json(journal))
        before = journal_path.read_bytes()

        evidence = payload_transaction.transaction_status(ctx)

        self.assertEqual(
            evidence,
            {
                "transaction_id": journal["transaction_id"],
                "version": "1.2.3",
                "receipt_sha256": transaction.receipt_sha256,
                "state": "recovery_required",
                "fresh": False,
            },
        )
        serialized = json.dumps(evidence, sort_keys=True)
        for forbidden in ("secret-token", "private request", "/private/release-stage"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(journal_path.read_bytes(), before)

    def test_finalize_reports_cleanup_failure_without_erasing_success_state(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        with (
            mock.patch.object(
                payload_transaction.shutil, "rmtree", side_effect=OSError("cleanup blocked")
            ),
            self.assertRaisesRegex(errors.InstallError, "cleanup failed"),
        ):
            transaction.finalize({"pid": 123})

        self.assertTrue(Path(payload_transaction.installed_release_state_path(ctx)).is_file())
        self.assertTrue(Path(payload_transaction.transaction_journal_path(ctx)).is_file())

    def test_transaction_state_machine_rejects_invalid_order_and_duplicate_commit(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_fixture())
        self.assertEqual(transaction.release, "1.2.3")
        self.assertEqual(transaction.expected["release"], "1.2.3")
        with self.assertRaisesRegex(errors.InstallError, "not committed"):
            transaction.finalize()
        with self.assertRaisesRegex(errors.InstallError, "only a committed"):
            transaction.preserve_for_recovery("not committed")
        transaction.commit_projection()
        with self.assertRaisesRegex(errors.InstallError, "not prepared"):
            transaction.commit_projection()
        transaction.rollback()
        transaction.rollback()
        with self.assertRaises(TypeError):
            payload_transaction.PayloadTransaction(
                ctx=ctx,
                blobs=(),
                version="1.2.3",
                receipt_sha256="0" * 64,
                receipt={},
                transaction_id="test",
                fresh=True,
            )

        fresh = begin_transaction(install_context(Path(tempfile.mkdtemp())), released_fixture())
        fresh.rollback()
        payload_transaction._remove_transaction_root(fresh._ctx)

    def test_begin_rejects_existing_transaction_and_invalid_candidate_boundaries(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction_root = Path(payload_transaction.payload_transaction_dir(ctx))
        transaction_root.mkdir(parents=True)
        with self.assertRaisesRegex(errors.InstallError, "already exists"):
            begin_transaction(ctx, released_fixture())

        valid = released_fixture()
        blobs, receipt = valid.peek_blobs(), dict(valid.receipt)
        cases = [
            (blobs, "1.2.3-rc1", "0" * 64, receipt, "version is invalid"),
            (blobs, "1.2.3", "short", receipt, "receipt digest is invalid"),
            (blobs, "1.2.3", "0" * 64, {**receipt, "version": "0.0.0"}, "version mismatch"),
            (blobs[:-1], "1.2.3", "0" * 64, receipt, "file set mismatch"),
            (
                blobs,
                "1.2.3",
                "0" * 64,
                {**receipt, "serving_files": []},
                "serving file set mismatch",
            ),
            (
                blobs,
                "1.2.3",
                "0" * 64,
                {**receipt, "serving_payload_sha256": "0" * 64},
                "serving identity mismatch",
            ),
        ]
        blob = blobs[0]

        def altered_blob(
            *,
            mode: Literal["100644", "100755"] = blob.mode,
            sha256: str = blob.sha256,
            content: bytes = blob.content,
        ) -> release_admission.ReleasedBlob:
            return release_admission.ReleasedBlob(
                path=blob.path,
                mode=mode,
                blob_oid=blob.blob_oid,
                sha256=sha256,
                content=content,
            )

        cases += (
            (
                (altered_blob(mode=cast("Literal['100644', '100755']", "100600")), *blobs[1:]),
                "1.2.3",
                "0" * 64,
                receipt,
                "mode is invalid",
            ),
            (
                (altered_blob(sha256="0" * 64), *blobs[1:]),
                "1.2.3",
                "0" * 64,
                receipt,
                "digest mismatch",
            ),
            (
                (
                    altered_blob(
                        content=b"0.0.0\n",
                        sha256=hashlib.sha256(b"0.0.0\n").hexdigest(),
                    ),
                    *blobs[1:],
                ),
                "1.2.3",
                "0" * 64,
                receipt,
                "VERSION blob",
            ),
        )
        for candidate_blobs, version, digest, candidate_receipt, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(errors.InstallError, message),
            ):
                payload_transaction._validate_candidate(
                    candidate_blobs, version, digest, candidate_receipt
                )

    def test_digest_boundary_and_retired_residue_types_fail_closed(self) -> None:
        valid = {
            relative: hashlib.sha256(relative.encode()).hexdigest()
            for relative in payload_projection.SERVING_PAYLOAD_FILES
        }
        with self.assertRaisesRegex(errors.InstallError, "file set mismatch"):
            payload_projection.serving_payload_sha256({})
        invalid = dict(valid)
        invalid["VERSION"] = "invalid"
        with self.assertRaisesRegex(errors.InstallError, "invalid serving payload"):
            payload_projection.serving_payload_sha256(invalid)

        ctx = install_context(Path(tempfile.mkdtemp()))
        retired_directory = Path(ctx.install_dir, "tests")
        retired_directory.parent.mkdir(parents=True, exist_ok=True)
        retired_directory.write_text("not a directory", encoding="utf-8")
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "manifest is required"):
            transaction.commit_projection()

    def test_transaction_filesystem_failures_remain_fail_closed(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))

        transaction = begin_transaction(ctx, released_fixture())
        with (
            mock.patch.object(payload_projection, "_sha256_file", return_value="0" * 64),
            self.assertRaisesRegex(errors.InstallError, "installed payload digest mismatch"),
        ):
            transaction.commit_projection()

        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        rollback.mkdir(parents=True)
        snapshot = {
            "schema_version": 2,
            "present": {"proxy/owned.py": {"sha256": "0" * 64, "mode": 0o644}},
            "retired": ["proxy/owned.py"],
            "retired_owned_sha256": payload_transaction._path_set_sha256({"proxy/owned.py"}),
            "previous_owned": ["proxy/owned.py"],
        }
        (rollback / "snapshot.json").write_bytes(
            payload_transaction.digest.canonical_json(snapshot)
        )
        with self.assertRaisesRegex(errors.InstallError, "rollback.*unavailable"):
            payload_transaction._restore_rollback_snapshot(ctx, rollback)

    def test_manifest_verifier_reports_each_metadata_boundary(self) -> None:
        def installed() -> tuple[installation.InstallContext, Path, dict[str, object]]:
            ctx = install_context(Path(tempfile.mkdtemp()))
            TestPayloadIdentity._install(ctx)
            path = Path(payload_projection.payload_manifest_path(ctx))
            return ctx, path, json.loads(path.read_text())

        ctx = install_context(Path(tempfile.mkdtemp()))
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("manifest unavailable", detail)

        ctx, path, _ = installed()
        path.write_text("not-json")
        self.assertIn("manifest unavailable", payload_projection.verify_payload_manifest(ctx)[1])

        mutations = [
            (lambda value: value.update(schema_version=99), "manifest schema is unsupported"),
            (lambda value: value.pop("release"), "manifest is incomplete"),
            (lambda value: value.update(release="9.9.9"), "release mismatch"),
            (lambda value: value["files"].pop("control.py"), "manifest file set mismatch"),
            (
                lambda value: value["serving_files"].pop(
                    payload_projection.SERVING_PAYLOAD_FILES[-1]
                ),
                "manifest serving file set mismatch",
            ),
            (lambda value: value["files"].update({"VERSION": "short"}), "invalid digest"),
            (
                lambda value: value["serving_files"].update({"VERSION": "0" * 64}),
                "serving digest mismatch",
            ),
            (
                lambda value: value.update(release_receipt_sha256="short"),
                "receipt digest is invalid",
            ),
            (
                lambda value: value.update(release_receipt_sha256="0" * 64),
                "receipt digest mismatch",
            ),
        ]
        for mutate, message in mutations:
            ctx, path, manifest = installed()
            mutate(manifest)
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(message=message):
                ok, detail = payload_projection.verify_payload_manifest(ctx)
                self.assertFalse(ok)
                self.assertIn(message, detail)

        ctx, _, _ = installed()
        Path(ctx.install_dir, "VERSION").unlink()
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("installed VERSION unavailable", detail)

        ctx, _, _ = installed()
        Path(ctx.install_dir, "control.py").unlink()
        with self.assertRaisesRegex(errors.InstallError, "installed payload is incomplete"):
            payload_projection.verify_payload_manifest(ctx)

        ctx, _, _ = installed()
        with mock.patch.object(
            payload_projection,
            "serving_payload_sha256",
            side_effect=errors.InstallError("invalid serving payload digest"),
        ):
            ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("invalid serving payload", detail)

        ctx, _, _ = installed()
        with mock.patch.object(
            payload_projection,
            "_sha256_file",
            side_effect=OSError("blocked"),
        ):
            ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("payload unavailable", detail)

        ctx, _, _ = installed()
        receipt = Path(ctx.install_dir, payload_projection.RELEASE_RECEIPT_FILENAME)
        receipt.unlink()
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("release receipt unavailable", detail)

    def test_canonical_state_and_rollback_validation_fail_closed(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        path = Path(ctx.install_dir, "state.json")
        path.parent.mkdir(parents=True)
        path.write_text('{"value": 1}', encoding="utf-8")
        with self.assertRaisesRegex(errors.InstallError, "not canonical JSON"):
            payload_projection._read_canonical_json(path, "state")
        path.write_bytes(b"\xff")
        with self.assertRaisesRegex(errors.InstallError, "unavailable or invalid"):
            payload_projection._read_canonical_json(path, "state")

        installed_state = Path(payload_transaction.installed_release_state_path(ctx))
        installed_state.write_bytes(
            payload_transaction.digest.canonical_json({"schema_version": 99})
        )
        with self.assertRaisesRegex(errors.InstallError, "schema is unsupported"):
            payload_transaction._read_installed_release_state(ctx)
        with self.assertRaisesRegex(errors.InstallError, "state version is invalid"):
            payload_transaction._require_state_version({"version": "latest"})

        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        rollback.mkdir(parents=True)
        cases = (
            ({"schema_version": 1, "present": {}}, "schema is unsupported"),
            (
                {
                    "schema_version": 2,
                    "present": [],
                    "retired": [],
                    "retired_owned_sha256": "0" * 64,
                    "previous_owned": [],
                },
                "snapshot is invalid",
            ),
            (
                {
                    "schema_version": 2,
                    "present": {"VERSION": {"sha256": "short", "mode": 0o644}},
                    "retired": [],
                    "retired_owned_sha256": payload_transaction._path_set_sha256(set()),
                    "previous_owned": ["VERSION"],
                },
                "metadata is invalid",
            ),
            (
                {
                    "schema_version": 2,
                    "present": {},
                    "retired": ["proxy/owned.py"],
                    "retired_owned_sha256": payload_transaction._path_set_sha256(
                        {"proxy/owned.py"}
                    ),
                    "previous_owned": ["proxy/owned.py"],
                },
                "retired inventory is incomplete",
            ),
        )
        for snapshot, message in cases:
            with self.subTest(message=message):
                (rollback / "snapshot.json").write_bytes(
                    payload_transaction.digest.canonical_json(snapshot)
                )
                with self.assertRaisesRegex(errors.InstallError, message):
                    payload_transaction._restore_rollback_snapshot(ctx, rollback)


if __name__ == "__main__":
    unittest.main(verbosity=2)
