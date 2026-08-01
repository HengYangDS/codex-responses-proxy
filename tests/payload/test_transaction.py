#!/usr/bin/env python3
"""Receipt-bound payload transaction lifecycle and recovery contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.payload import identity as listener_identity
from codex_responses_proxy.payload import inventory
from codex_responses_proxy.payload import projection as payload_projection
from codex_responses_proxy.payload import source as payload_source
from codex_responses_proxy.payload import transaction as payload_transaction
from tests.deployment.fixtures import install_context
from tests.payload.fixtures import begin_transaction, install_payload, released_fixture


class TestPayloadTransaction(unittest.TestCase):
    """Receipt-bound payload transaction lifecycle and recovery contracts."""

    def test_begin_accepts_only_opaque_released_payload_not_a_raw_path(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        with self.assertRaises((TypeError, errors.InstallError)):
            begin_transaction(ctx, cast("payload_source.ReleasedPayload", str(ROOT)))

    def test_transaction_status_is_absent_without_a_journal(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        self.assertIsNone(payload_transaction.transaction_status(ctx))

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
        install_payload(ctx, "1.2.2")
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
        install_payload(ctx, "1.2.2")
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
        install_payload(ctx, "1.2.2")
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
        install_payload(ctx)
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
        install_payload(ctx, "1.2.2")
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
        install_payload(ctx, "1.2.2")
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
        install_payload(ctx, "1.2.2")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
