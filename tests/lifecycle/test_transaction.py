"""Receipt-bound payload transaction lifecycle and recovery contracts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle import transaction as payload_transaction
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import identity as listener_identity
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import begin_transaction, install_payload, released_artifact
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestPayloadTransaction:
    """Receipt-bound payload transaction lifecycle and recovery contracts."""

    def test_begin_accepts_only_opaque_released_payload_not_a_raw_path(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        with pytest.raises((TypeError, errors.InstallError)):
            begin_transaction(ctx, cast("artifact.VerifiedArtifact", str(ROOT)), mocker=mocker)

    def test_transaction_status_is_absent_without_a_journal(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        assert payload_state.status(ctx) is None

    def test_fresh_commit_writes_manifest_receipt_and_pending_journal_then_finalize_state(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)

        transaction.commit_projection()

        assert Path(ctx.install_dir, "payload-manifest.json").is_file()
        assert Path(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME).is_file()
        journal = json.loads(Path(payload_state.journal_path(ctx)).read_text(encoding="utf-8"))
        assert journal["state"] == "committed"
        assert not Path(payload_state.installed_path(ctx)).exists()

        transaction.finalize({"pid": 123, "accepting": True})

        state = json.loads(Path(payload_state.installed_path(ctx)).read_text(encoding="utf-8"))
        assert state["version"] == "1.2.3"
        assert state["receipt_sha256"] == transaction.receipt_sha256
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_failed_commit_rolls_back_before_propagating(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        before = Path(ctx.executable).read_bytes()
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        mocker.patch.object(
            payload_projection,
            "verify_payload_manifest",
            return_value=(False, "tampered"),
        )
        with pytest.raises(errors.InstallError, match="integrity check failed"):
            transaction.commit_projection()
        assert Path(ctx.executable).read_bytes() == before
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_upgrade_rollback_restores_payload_receipt_and_installed_state_exactly(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        before = {
            relative: Path(ctx.install_dir, relative).read_bytes()
            for relative in (
                *inventory.RUNTIME_FILES,
                inventory.MANIFEST_FILENAME,
                inventory.RELEASE_RECEIPT_FILENAME,
            )
        }
        before_state = Path(payload_state.installed_path(ctx)).read_bytes()

        second = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        second.commit_projection()
        second.rollback()

        for relative, content in before.items():
            assert Path(ctx.install_dir, relative).read_bytes() == content
        assert Path(payload_state.installed_path(ctx)).read_bytes() == before_state
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_upgrade_rollback_preserves_unknown_retired_content(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local content\n")

        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        assert unknown.read_bytes() == b"local content\n"
        transaction.rollback()

        assert unknown.read_bytes() == b"local content\n"

    def test_replay_and_downgrade_are_rejected_before_any_live_write(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        marker = Path(ctx.executable).read_bytes()

        for version, message in (("1.2.3", "replay"), ("1.2.2", "downgrade")):
            with (
                subtests.test(version=version),
                pytest.raises(errors.InstallError, match=message),
            ):
                begin_transaction(ctx, released_artifact(version), mocker=mocker)
            assert Path(ctx.executable).read_bytes() == marker
            assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_preserve_for_recovery_keeps_journal_and_rollback_visible(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        transaction.commit_projection()

        transaction.preserve_for_recovery("handoff outcome unknown")

        journal = json.loads(Path(payload_state.journal_path(ctx)).read_text(encoding="utf-8"))
        assert journal["state"] == "recovery_required"
        assert journal["reason"] == "handoff outcome unknown"
        assert Path(payload_state.transaction_root(ctx), "rollback").is_dir()

    def test_recovery_rollback_restores_previous_projection_and_removes_hold(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        previous = Path(ctx.executable).read_bytes()
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        previous_identity = listener_identity.committed_payload(
            rollback / inventory.executable_name()
        )
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
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

        assert result["state"] == "rolled_back"
        assert Path(ctx.executable).read_bytes() == previous
        assert not Path(payload_state.transaction_root(ctx)).exists()

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
            with subtests.test(journal=journal):
                root = Path(payload_state.transaction_root(ctx))
                root.mkdir()
                Path(payload_state.journal_path(ctx)).write_bytes(
                    payload_digest.canonical_json(journal)
                )
                with pytest.raises(errors.InstallError, match="unavailable or invalid"):
                    payload_transaction.rollback_recovery(ctx, runtime=runtime)
                for path in sorted(root.rglob("*"), reverse=True):
                    path.unlink() if path.is_file() else path.rmdir()
                root.rmdir()

        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        root = Path(payload_state.transaction_root(ctx))
        rollback = root / "rollback"
        previous_identity = listener_identity.committed_payload(
            rollback / inventory.executable_name()
        )
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = {
            **previous_identity.handoff(),
            "payload_manifest_sha256": candidate_identity.manifest_sha256,
            "accepting": True,
            "handoff_state": "idle",
        }
        runtime.pop("manifest_sha256")
        with pytest.raises(errors.InstallError, match="does not match"):
            payload_transaction.rollback_recovery(
                ctx,
                runtime={**runtime, "release": "wrong"},
            )
        candidate_executable = Path(ctx.executable)
        candidate_bytes = candidate_executable.read_bytes()
        candidate_executable.write_bytes(b"tampered\n")
        with pytest.raises(errors.InstallError, match="candidate projection identity"):
            payload_transaction.rollback_recovery(ctx, runtime=runtime)
        candidate_executable.write_bytes(candidate_bytes)
        (root / "rollback" / inventory.executable_name()).write_bytes(b"tampered\n")
        with pytest.raises(errors.InstallError, match="runtime identity is invalid"):
            payload_transaction.rollback_recovery(ctx, runtime=runtime)
        assert root.exists()

    def test_transaction_status_projects_only_the_read_only_recovery_contract(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        transaction.commit_projection()
        transaction.preserve_for_recovery("handoff outcome unknown")
        journal_path = Path(payload_state.journal_path(ctx))
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
        journal_path.write_bytes(payload_digest.canonical_json(journal))
        before = journal_path.read_bytes()

        evidence = payload_state.status(ctx)

        assert evidence == {
            "transaction_id": journal["transaction_id"],
            "version": "1.2.3",
            "receipt_sha256": transaction.receipt_sha256,
            "state": "recovery_required",
            "fresh": False,
        }
        serialized = json.dumps(evidence, sort_keys=True)
        for forbidden in ("secret-token", "private request", "/private/release-stage"):
            assert forbidden not in serialized
        assert journal_path.read_bytes() == before

    def test_finalize_reports_cleanup_failure_without_erasing_success_state(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        mocker.patch.object(
            payload_transaction.shutil, "rmtree", side_effect=OSError("cleanup blocked")
        )

        with pytest.raises(errors.InstallError, match="cleanup failed"):
            transaction.finalize({"pid": 123})

        assert Path(payload_state.installed_path(ctx)).is_file()
        assert Path(payload_state.journal_path(ctx)).is_file()

    def test_transaction_state_machine_rejects_invalid_order_and_duplicate_commit(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        assert transaction.release == "1.2.3"
        assert transaction.expected["release"] == "1.2.3"
        with pytest.raises(errors.InstallError, match="not committed"):
            transaction.finalize()
        with pytest.raises(errors.InstallError, match="only a committed"):
            transaction.preserve_for_recovery("not committed")
        transaction.commit_projection()
        with pytest.raises(errors.InstallError, match="not prepared"):
            transaction.commit_projection()
        transaction.rollback()
        transaction.rollback()
        with pytest.raises(TypeError):
            payload_transaction.PayloadTransaction(
                ctx=ctx,
                blobs=(),
                version="1.2.3",
                receipt_sha256="0" * 64,
                receipt={},
                transaction_id="test",
                fresh=True,
            )

        fresh = begin_transaction(
            install_context(Path(tempfile.mkdtemp())), released_artifact(), mocker=mocker
        )
        fresh.rollback()
        payload_transaction._remove_transaction_root(fresh._ctx)
