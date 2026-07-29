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
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import common, payload, release_source  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402


def released_fixture(version: str = "1.2.3") -> release_source.ReleasedPayload:
    """Build one genuine opaque runtime payload without a Git fixture."""

    files = {relative: (ROOT / relative).read_bytes() for relative in payload.RUNTIME_PAYLOAD_FILES}
    files["VERSION"] = f"{version}\n".encode()
    blobs = tuple(
        release_source.ReleasedBlob(
            path=relative,
            mode="100644",
            blob_oid=hashlib.sha1(content).hexdigest(),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        for relative, content in files.items()
    )
    serving = {
        blob.path: blob.sha256 for blob in blobs if blob.path in payload.SERVING_PAYLOAD_FILES
    }
    aggregate = payload.serving_payload_sha256(serving)
    receipt = {
        "schema_version": 1,
        "version": version,
        "tag_object_oid": "b" * 40,
        "commit_oid": "c" * 40,
        "tree_oid": "d" * 40,
        "serving_payload_sha256": aggregate,
        "payload": [
            {
                "path": blob.path,
                "mode": blob.mode,
                "blob_oid": blob.blob_oid,
                "sha256": blob.sha256,
            }
            for blob in blobs
        ],
    }
    sidecar = {
        "schema_version": 1,
        "receipt_sha256": hashlib.sha256(release_source.canonical_json(receipt)).hexdigest(),
    }
    # Construction stays test-local; production callers can only obtain this class through admit().
    return release_source.ReleasedPayload._from_verified(
        blobs=blobs,
        receipt=receipt,
        sidecar=sidecar,
    )


class TestPayloadIdentity(unittest.TestCase):
    """Manifest and startup-frozen aggregate contracts over opaque payload bytes."""

    @staticmethod
    def _install(ctx: common.InstallContext, version: str = "1.2.3") -> None:
        transaction = payload.begin_transaction(ctx, released_fixture(version))
        transaction.commit_projection()
        transaction.finalize({"pid": 1})

    def test_transaction_installs_complete_runtime_and_manifest(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        manifest = json.loads(Path(payload.payload_manifest_path(ctx)).read_text(encoding="utf-8"))
        self.assertEqual(sorted(manifest["files"]), sorted(payload.RUNTIME_PAYLOAD_FILES))
        self.assertEqual(sorted(manifest["serving_files"]), sorted(payload.SERVING_PAYLOAD_FILES))
        self.assertEqual(
            manifest["serving_payload_sha256"],
            payload.serving_payload_sha256(manifest["serving_files"]),
        )
        self.assertTrue(Path(ctx.install_dir, "control.py").is_file())
        self.assertTrue(Path(ctx.install_dir, "governance.py").is_file())

    def test_manifest_detects_payload_and_aggregate_tampering(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        proxy = Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py")
        proxy.write_bytes(proxy.read_bytes() + b"# tampered\n")
        ok, detail = payload.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("hash mismatch", detail)

        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        manifest_path = Path(payload.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["serving_payload_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        ok, detail = payload.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertEqual(detail, "serving payload aggregate mismatch")

    def test_serving_payload_identity_is_order_independent_and_length_delimited(self) -> None:
        digests = {
            relative: hashlib.sha256(relative.encode("utf-8")).hexdigest()
            for relative in payload.SERVING_PAYLOAD_FILES
        }
        reverse_order = dict(reversed(tuple(digests.items())))
        self.assertEqual(
            payload.serving_payload_sha256(digests),
            payload.serving_payload_sha256(reverse_order),
        )
        changed = dict(digests)
        changed["proxy/runtime_state.py"] = "0" * 64
        self.assertNotEqual(
            payload.serving_payload_sha256(digests),
            payload.serving_payload_sha256(changed),
        )

    def test_loaded_identity_freezes_release_aggregate_and_receipt_before_disk_changes(
        self,
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self._install(ctx)
        proxy_root = Path(ctx.install_dir) / "proxy"
        script = """
import json
from pathlib import Path
import dmx_responses_proxy as proxy
root = Path.cwd()
(root / "VERSION").write_text("9.9.9\\n", encoding="utf-8")
(root / "proxy" / "runtime_state.py").write_text("tampered = True\\n", encoding="utf-8")
print(json.dumps(proxy.runtime_status()))
"""
        completed = subprocess.run(
            [ctx.python, "-c", script],
            cwd=ctx.install_dir,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(proxy_root)},
        )
        runtime = json.loads(completed.stdout)
        manifest = json.loads(Path(payload.payload_manifest_path(ctx)).read_text(encoding="utf-8"))
        self.assertEqual(runtime["release"], "1.2.3")
        self.assertEqual(runtime["serving_payload_sha256"], manifest["serving_payload_sha256"])
        self.assertEqual(runtime["release_receipt_sha256"], manifest["release_receipt_sha256"])


class TestReceiptBoundPayloadTransaction(unittest.TestCase):
    """Contract for the only payload/receipt/state mutation boundary."""

    def test_begin_accepts_only_opaque_released_payload_not_a_raw_path(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        with self.assertRaises((TypeError, common.InstallError)):
            payload.begin_transaction(ctx, cast("release_source.ReleasedPayload", str(ROOT)))

    def test_begin_removes_only_exact_runtime_owned_legacy_privacy_residue(self) -> None:
        root = Path(tempfile.mkdtemp())
        ctx = install_context(root)
        log_root = Path(ctx.log_dir)
        log_root.mkdir(parents=True)
        captures = (
            log_root / "reject-400-1700000000.json",
            log_root / "reject-empty-response.json",
        )
        for capture in captures:
            capture.write_bytes(b'{"input":"private request"}\n')
        retained_log = log_root / "dmx-responses-proxy.log"
        retained_log.write_bytes(b"bounded structured event\n")
        retained_json = log_root / "response.json"
        retained_json.write_bytes(b'{"not":"a legacy capture"}\n')
        nested = log_root / "nested"
        nested.mkdir()
        nested_capture = nested / "reject-nested.json"
        nested_capture.write_bytes(b'{"input":"outside direct-child scope"}\n')
        external = root / "reject-external.json"
        external.write_bytes(b'{"input":"outside runtime root"}\n')
        obsolete_tests = Path(ctx.install_dir) / "tests"
        obsolete_tests.mkdir(parents=True)
        (obsolete_tests / "test_legacy.py").write_bytes(b"legacy test residue\n")

        released = released_fixture()
        original_read_bytes = Path.read_bytes

        def refuse_capture_read(path: Path) -> bytes:
            if path in captures:
                raise AssertionError("capture read")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=refuse_capture_read):
            transaction = payload.begin_transaction(ctx, released)

        for capture in captures:
            self.assertFalse(capture.exists())
        self.assertEqual(retained_log.read_bytes(), b"bounded structured event\n")
        self.assertEqual(retained_json.read_bytes(), b'{"not":"a legacy capture"}\n')
        self.assertTrue(nested_capture.is_file())
        self.assertTrue(external.is_file())
        self.assertFalse(obsolete_tests.exists())
        self.assertTrue(Path(payload.transaction_journal_path(ctx)).is_file())
        transaction.rollback()

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
            self.assertRaisesRegex(common.InstallError, "capture cleanup failed"),
        ):
            payload.begin_transaction(ctx, released_fixture())

        self.assertEqual(marker.read_bytes(), b"existing live payload\n")
        self.assertTrue(capture.is_file())
        self.assertFalse(Path(payload.payload_transaction_dir(ctx)).exists())

    def test_fresh_commit_writes_manifest_receipt_and_pending_journal_then_finalize_state(
        self,
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = payload.begin_transaction(ctx, released_fixture())

        transaction.commit_projection()

        self.assertTrue(Path(ctx.install_dir, "payload-manifest.json").is_file())
        self.assertTrue(Path(ctx.install_dir, payload.RELEASE_RECEIPT_FILENAME).is_file())
        journal = json.loads(
            Path(payload.transaction_journal_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["state"], "committed")
        self.assertFalse(Path(payload.installed_release_state_path(ctx)).exists())

        transaction.finalize({"pid": 123, "accepting": True})

        state = json.loads(
            Path(payload.installed_release_state_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(state["version"], "1.2.3")
        self.assertEqual(state["receipt_sha256"], transaction.receipt_sha256)
        self.assertFalse(Path(payload.payload_transaction_dir(ctx)).exists())

    def test_upgrade_rollback_restores_payload_receipt_and_installed_state_exactly(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        first = payload.begin_transaction(ctx, released_fixture("1.2.2"))
        first.commit_projection()
        first.finalize({"pid": 111})
        before = {
            relative: Path(ctx.install_dir, relative).read_bytes()
            for relative in (
                *payload.RUNTIME_PAYLOAD_FILES,
                payload.PAYLOAD_MANIFEST_FILENAME,
                payload.RELEASE_RECEIPT_FILENAME,
            )
        }
        before_state = Path(payload.installed_release_state_path(ctx)).read_bytes()

        second = payload.begin_transaction(ctx, released_fixture("1.2.3"))
        second.commit_projection()
        second.rollback()

        for relative, content in before.items():
            self.assertEqual(Path(ctx.install_dir, relative).read_bytes(), content)
        self.assertEqual(Path(payload.installed_release_state_path(ctx)).read_bytes(), before_state)
        self.assertFalse(Path(payload.payload_transaction_dir(ctx)).exists())

    def test_replay_and_downgrade_are_rejected_before_any_live_write(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        initial = payload.begin_transaction(ctx, released_fixture("1.2.3"))
        initial.commit_projection()
        initial.finalize({"pid": 111})
        marker = Path(ctx.install_dir, "VERSION").read_bytes()

        for version, message in (("1.2.3", "replay"), ("1.2.2", "downgrade")):
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(common.InstallError, message),
            ):
                payload.begin_transaction(ctx, released_fixture(version))
            self.assertEqual(Path(ctx.install_dir, "VERSION").read_bytes(), marker)
            self.assertFalse(Path(payload.payload_transaction_dir(ctx)).exists())

    def test_preserve_for_recovery_keeps_journal_and_rollback_visible(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        initial = payload.begin_transaction(ctx, released_fixture("1.2.2"))
        initial.commit_projection()
        initial.finalize({"pid": 111})
        transaction = payload.begin_transaction(ctx, released_fixture("1.2.3"))
        transaction.commit_projection()

        transaction.preserve_for_recovery("handoff outcome unknown")

        journal = json.loads(
            Path(payload.transaction_journal_path(ctx)).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["state"], "recovery_required")
        self.assertEqual(journal["reason"], "handoff outcome unknown")
        self.assertTrue(Path(payload.payload_transaction_dir(ctx), "rollback").is_dir())

    def test_transaction_status_projects_only_the_read_only_recovery_contract(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        initial = payload.begin_transaction(ctx, released_fixture("1.2.2"))
        initial.commit_projection()
        initial.finalize({"pid": 111})
        transaction = payload.begin_transaction(ctx, released_fixture("1.2.3"))
        transaction.commit_projection()
        transaction.preserve_for_recovery("handoff outcome unknown")
        journal_path = Path(payload.transaction_journal_path(ctx))
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
        journal_path.write_bytes(payload._canonical_json(journal))
        before = journal_path.read_bytes()

        evidence = payload.transaction_status(ctx)

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
        transaction = payload.begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        with (
            mock.patch.object(payload.shutil, "rmtree", side_effect=OSError("cleanup blocked")),
            self.assertRaisesRegex(common.InstallError, "cleanup failed"),
        ):
            transaction.finalize({"pid": 123})

        self.assertTrue(Path(payload.installed_release_state_path(ctx)).is_file())
        self.assertTrue(Path(payload.transaction_journal_path(ctx)).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
