"""Receipt-bound payload transaction lifecycle and recovery contracts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import generation as payload_generation
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle import transaction as payload_transaction
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import identity as listener_identity
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import begin_transaction
from tests.lifecycle.fixtures import executable_relative
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import install_payload
from tests.lifecycle.fixtures import released_artifact
from tests.lifecycle.fixtures import runtime_files


def recovery_runtime(
    runtime_identity: listener_identity.LoadedPayloadIdentity,
    candidate_identity: listener_identity.LoadedPayloadIdentity | None = None,
) -> dict[str, object]:
    """Project one accepting runtime for one exact committed payload."""

    return {
        "pid": 321,
        "release": runtime_identity.release,
        "serving_payload_sha256": runtime_identity.serving_payload_sha256,
        "release_receipt_sha256": runtime_identity.release_receipt_sha256,
        "payload_manifest_sha256": (candidate_identity or runtime_identity).manifest_sha256,
        "accepting": True,
        "draining": False,
        "handoff_state": "idle",
    }


def _retained_carrier_snapshot(root: Path, external_target: Path) -> tuple[object, ...]:
    """Capture exact test-owned carrier shape and bytes without following links."""
    if root.is_symlink():
        return (
            "root-link",
            os.readlink(root),
            (external_target / "evidence").read_bytes(),
        )
    if root.is_file():
        return ("root-file", root.read_bytes())
    entries: list[tuple[object, ...]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append((relative, "link", os.readlink(path)))
        elif path.is_dir():
            entries.append((relative, "directory"))
        else:
            entries.append((relative, "file", path.read_bytes()))
    target = external_target.read_bytes() if external_target.is_file() else None
    return ("root-directory", tuple(entries), target)


def _project_as_legacy_flat_install(ctx, installed) -> None:
    """Recreate the released flat layout accepted by the one-time migrator."""
    generation_root = Path(installed.context.payload_dir)
    install_root = Path(ctx.install_dir)
    for child in tuple(generation_root.iterdir()):
        child.rename(install_root / child.name)
    payload_generation.clear(ctx)
    generation_root.rmdir()
    ctx.executable = str(install_root / executable_relative())
    command_path = Path(ctx.command)
    command_path.unlink()
    command_path.symlink_to(ctx.executable)


def test_commit_prewarms_the_exact_candidate_executable(tmp_path: Path, *, mocker) -> None:
    ctx = install_context(tmp_path)
    candidate = released_artifact()
    prewarm = mocker.patch.object(payload_transaction.payload_candidate, "prewarm")

    transaction = payload_transaction.begin_transaction(ctx, candidate)
    prewarm.assert_not_called()

    transaction.commit_projection()

    prewarm.assert_called_once_with(Path(transaction.context.executable))
    transaction.rollback()


def test_upgrade_rollback_removes_candidate_only_runtime_members(tmp_path: Path, *, mocker) -> None:
    ctx = install_context(tmp_path)
    install_payload(ctx, "1.2.2", mocker=mocker)
    base = released_artifact("1.2.3")
    content = b"candidate-only-runtime"
    extra = artifact.ArtifactFile(
        path="bin/_internal/runtime.dat",
        mode="100644",
        blob_oid=hashlib.sha256(content).hexdigest(),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )
    blobs = (*base.peek_blobs(), extra)
    serving = {item.path: item.sha256 for item in blobs}
    receipt = {
        "schema_version": 1,
        "version": "1.2.3",
        "serving_payload_sha256": payload_projection.manifest_serving_payload_sha256(serving),
        "serving_files": [item.path for item in blobs],
        "payload": [
            {
                "path": item.path,
                "mode": item.mode,
                "blob_oid": item.blob_oid,
                "sha256": item.sha256,
            }
            for item in blobs
        ],
    }
    receipt_sha256 = hashlib.sha256(payload_digest.canonical_json(receipt)).hexdigest()
    candidate = artifact.mint(
        blobs,
        receipt,
        {
            "schema_version": 1,
            "algorithm": "sha256",
            "receipt_sha256": receipt_sha256,
            "serving_payload_sha256": receipt["serving_payload_sha256"],
        },
    )
    transaction = begin_transaction(ctx, candidate, mocker=mocker)
    transaction.commit_projection()
    introduced = Path(transaction.context.payload_dir, extra.path)
    assert introduced.read_bytes() == content
    transaction.rollback()
    assert not introduced.exists()


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

    def test_recovery_is_idempotent_when_no_transaction_exists(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))

        assert payload_transaction.recover(ctx, runtime=None) == {"state": "not_required"}

    def test_finalize_selects_no_predecessor_for_a_fresh_install(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))

        install_payload(ctx, "1.2.2", mocker=mocker)

        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.predecessor is None
        assert tuple(payload_generation.root(ctx).iterdir()) == (
            payload_generation.path(ctx, selection.active),
        )

    def test_finalize_retains_exactly_the_displaced_predecessor(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)

        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})

        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"
        assert retained.successor.release == "1.2.3"
        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.predecessor is not None
        assert retained.root == payload_generation.path(ctx, selection.predecessor)

    def test_a_later_finalize_replaces_the_retained_predecessor(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        middle = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        middle.commit_projection()
        middle.activate()
        middle.finalize({"pid": 2})
        first = payload_rollback.load_retained(ctx)
        latest = begin_transaction(ctx, released_artifact("1.2.4"), mocker=mocker)

        latest.commit_projection()
        latest.activate()
        latest.finalize({"pid": 3})

        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.3"
        assert retained.successor.release == "1.2.4"
        assert retained.root != first.root
        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.predecessor is not None
        assert retained.root == payload_generation.path(ctx, selection.predecessor)

    def test_recovery_finalization_selects_the_displaced_predecessor(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        projected = listener_identity.committed_payload(Path(successor.context.executable))
        assert projected is not None

        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(projected, projected),
        )

        assert result["state"] == "finalized"
        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"
        assert retained.successor.release == "1.2.3"

    def test_legacy_migration_failure_preserves_snapshot_for_recovery(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """A failed legacy migration must leave one complete retry source."""
        ctx = install_context(tmp_path)
        legacy = begin_transaction(ctx, released_artifact("1.2.2"), mocker=mocker)
        legacy.commit_projection()
        legacy.activate()
        legacy.finalize({"pid": 1})
        _project_as_legacy_flat_install(ctx, legacy)

        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        snapshot = Path(payload_state.transaction_root(ctx), "rollback")
        before = {
            relative: Path(snapshot, relative).read_bytes()
            for relative in (*runtime_files(), inventory.MANIFEST_FILENAME)
        }
        original_copy = payload_generation.shutil.copyfile
        attempts = 0

        def interrupt_second_file(source: Path, target: Path, **kwargs) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError("migration interrupted")
            original_copy(source, target, **kwargs)

        copy = mocker.patch.object(
            payload_generation.shutil,
            "copyfile",
            side_effect=interrupt_second_file,
        )

        with pytest.raises(errors.InstallError, match="legacy payload migration failed"):
            successor.finalize({"pid": 2})

        mocker.stop(copy)
        assert {
            relative: Path(snapshot, relative).read_bytes()
            for relative in (*runtime_files(), inventory.MANIFEST_FILENAME)
        } == before
        assert not payload_generation.path(ctx, str(legacy.expected["transaction_id"])).exists()

        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(candidate, candidate),
        )

        assert result["state"] == "finalized"
        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"

    def test_legacy_migration_retires_flat_payload_without_unknown_content(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Successful migration leaves only selected generations as payload authority."""
        ctx = install_context(tmp_path)
        legacy = begin_transaction(ctx, released_artifact("1.2.2"), mocker=mocker)
        legacy.commit_projection()
        legacy.activate()
        legacy.finalize({"pid": 1})
        _project_as_legacy_flat_install(ctx, legacy)
        unknown = Path(ctx.install_dir, "operator-notes.txt")
        unknown.write_text("preserve\n", encoding="utf-8")

        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})

        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.predecessor == str(legacy.expected["transaction_id"])
        for relative in (*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA):
            assert not Path(ctx.install_dir, relative).exists()
        assert unknown.read_text(encoding="utf-8") == "preserve\n"

    def test_legacy_retirement_resumes_after_partial_deletion(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Recovery completes the exact retirement plan after interruption."""
        ctx = install_context(tmp_path)
        legacy = begin_transaction(ctx, released_artifact("1.2.2"), mocker=mocker)
        legacy.commit_projection()
        legacy.activate()
        legacy.finalize({"pid": 1})
        _project_as_legacy_flat_install(ctx, legacy)
        unknown = Path(ctx.install_dir, "operator-notes.txt")
        unknown.write_text("preserve\n", encoding="utf-8")

        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        original_unlink = Path.unlink
        deleted: list[Path] = []

        def interrupt_second_owned_file(target: Path, *args, **kwargs) -> None:
            if target.is_relative_to(ctx.install_dir) and "generations" not in target.parts:
                deleted.append(target)
                if len(deleted) == 2:
                    raise OSError("retirement interrupted")
            original_unlink(target, *args, **kwargs)

        unlink = mocker.patch.object(
            Path,
            "unlink",
            autospec=True,
            side_effect=interrupt_second_owned_file,
        )
        with pytest.raises(errors.InstallError, match="legacy payload retirement failed"):
            successor.finalize({"pid": 2})
        mocker.stop(unlink)
        assert deleted[0].exists() is False

        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(candidate, candidate),
        )

        assert result["state"] == "finalized"
        for relative in (*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA):
            assert not Path(ctx.install_dir, relative).exists()
        assert unknown.read_text(encoding="utf-8") == "preserve\n"

    def test_activated_legacy_upgrade_recovers_the_flat_predecessor(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Rollback restores the sole legacy authority and retires the candidate generation."""
        ctx = install_context(tmp_path)
        legacy = install_payload(ctx, "1.2.2", mocker=mocker)
        _project_as_legacy_flat_install(ctx, legacy)
        predecessor = listener_identity.committed_payload(Path(ctx.executable))
        assert predecessor is not None
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.preserve_for_recovery("controller outcome unknown")

        result = payload_transaction.recover(ctx, runtime=recovery_runtime(predecessor))

        assert result["state"] == "rolled_back"
        restored = listener_identity.committed_payload(Path(ctx.executable))
        assert restored is not None
        assert restored.release == "1.2.2"
        assert payload_generation.read(ctx) is None
        assert not Path(successor.context.payload_dir).exists()
        assert Path(ctx.command).samefile(ctx.executable)

    def test_activated_legacy_upgrade_rejects_an_unproved_predecessor_runtime(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Legacy rollback preserves all evidence until its live predecessor is proven."""
        ctx = install_context(tmp_path)
        legacy = install_payload(ctx, "1.2.2", mocker=mocker)
        _project_as_legacy_flat_install(ctx, legacy)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.preserve_for_recovery("controller outcome unknown")
        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        wrong_runtime = recovery_runtime(candidate)
        wrong_runtime["release"] = "9.9.9"

        with pytest.raises(errors.RecoveryStateError, match="rollback projection"):
            payload_transaction.recover(ctx, runtime=wrong_runtime)

        assert Path(payload_state.transaction_root(ctx)).is_dir()
        assert Path(successor.context.payload_dir).is_dir()

    def test_retained_predecessor_reuses_an_exact_reverse_transaction(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(payload_transaction.payload_candidate, "prewarm")
        first = payload_transaction.begin_transaction(ctx, released_artifact("1.2.2"))
        first.commit_projection()
        first.activate()
        first.finalize({"pid": 1})
        successor = payload_transaction.begin_transaction(ctx, released_artifact("1.2.3"))
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        control_executable = Path(ctx.command).resolve(strict=True)
        assert control_executable.samefile(successor.context.executable)

        reverse = payload_transaction.begin_rollback_transaction(ctx, retained)
        reverse.commit_projection()

        restored = listener_identity.committed_payload(Path(reverse.context.executable))
        assert restored is not None
        assert restored.release == "1.2.2"
        reverse.activate()
        assert Path(ctx.command).resolve(strict=True).samefile(control_executable)
        reverse.rollback()
        selection = payload_generation.read(ctx)
        assert selection is not None
        current = listener_identity.committed_payload(
            Path(payload_generation.context(ctx, selection.active).executable)
        )
        assert current is not None
        assert current.release == "1.2.3"

    def test_finalized_reverse_transition_keeps_newest_control_upgrade_floor(
        self, *, mocker
    ) -> None:
        """Serving rollback cannot make an older release the install authority."""
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(payload_transaction.payload_candidate, "prewarm")
        first = payload_transaction.begin_transaction(ctx, released_artifact("1.2.2"))
        first.commit_projection()
        first.activate()
        first.finalize({"pid": 1})
        successor = payload_transaction.begin_transaction(ctx, released_artifact("1.2.3"))
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        control_executable = Path(ctx.command).resolve(strict=True)
        reverse = payload_transaction.begin_rollback_transaction(
            ctx, payload_rollback.load_retained(ctx)
        )
        reverse.commit_projection()
        reverse.activate()
        reverse.finalize({"pid": 3})

        assert Path(ctx.command).resolve(strict=True).samefile(control_executable)
        with pytest.raises(errors.InstallError, match="replay"):
            payload_transaction.begin_transaction(ctx, released_artifact("1.2.3"))

        forward = payload_transaction.begin_transaction(ctx, released_artifact("1.2.4"))
        forward.rollback()

    def test_interrupted_reverse_transition_recovers_the_original_successor(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Recovery reverses an activated rollback without inventing another payload copy."""
        ctx = install_context(tmp_path)
        _first = install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        original_selection = payload_generation.read(ctx)
        assert original_selection is not None
        retained = payload_rollback.load_retained(ctx)
        reverse = payload_transaction.begin_rollback_transaction(ctx, retained)
        assert reverse.expected["release"] == "1.2.2"
        reverse.commit_projection()
        reverse.activate()
        reverse.preserve_for_recovery("rollback controller outcome unknown")
        original_successor = listener_identity.committed_payload(
            Path(payload_generation.context(ctx, original_selection.active).executable)
        )
        assert original_successor is not None

        result = payload_transaction.recover(ctx, runtime=recovery_runtime(original_successor))

        assert result["state"] == "rolled_back"
        assert payload_generation.read(ctx) == original_selection

    def test_interrupted_reverse_transition_rejects_the_wrong_runtime(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Reverse recovery cannot select a successor not proven by the live runtime."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        reverse = payload_transaction.begin_rollback_transaction(ctx, retained)
        reverse.commit_projection()
        reverse.activate()
        reverse.preserve_for_recovery("rollback controller outcome unknown")

        wrong_runtime = recovery_runtime(retained.successor)
        wrong_runtime["release"] = "9.9.9"
        with pytest.raises(errors.RecoveryStateError, match="prior selected generation"):
            payload_transaction.recover(ctx, runtime=wrong_runtime)

    @pytest.mark.parametrize("drift", ["installed", "selection", "root"])
    def test_reverse_transition_rejects_stale_authority(
        self, tmp_path: Path, drift: str, *, mocker
    ) -> None:
        """Rollback admission rechecks installed state, selection, and predecessor root."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        if drift == "installed":
            installed_path = Path(payload_state.installed_path(ctx))
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            installed["version"] = "1.2.4"
            installed_path.write_bytes(payload_digest.canonical_json(installed))
            expected = "successor changed"
        elif drift == "selection":
            selection = payload_generation.read(ctx)
            assert selection is not None
            payload_generation.select(ctx, active=selection.active, predecessor=None)
            expected = "selection changed"
        else:
            retained = replace(retained, root=tmp_path / "unrelated-generation")
            expected = "predecessor changed"

        with pytest.raises(errors.InstallError, match=expected):
            payload_transaction.begin_rollback_transaction(ctx, retained)

    def test_reverse_transition_rechecks_predecessor_before_materialization(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """An admitted rollback still fails if the retained generation later changes."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        reverse = payload_transaction.begin_rollback_transaction(ctx, retained)
        Path(reverse.context.executable).write_bytes(b"corrupt")

        with pytest.raises(errors.InstallError, match="changed before materialization"):
            reverse.commit_projection()

    def test_retained_predecessor_rejects_corruption_before_mutation(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.activate()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        executable = retained.root / executable_relative()
        executable.write_bytes(b"corrupt")
        before = Path(ctx.executable).read_bytes()

        with pytest.raises(errors.InstallError, match="predecessor generation identity"):
            payload_rollback.load_retained(ctx)

        assert Path(ctx.executable).read_bytes() == before

    def test_transaction_status_classifies_an_existing_invalid_carrier(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        root = Path(payload_state.transaction_root(ctx))
        root.mkdir(parents=True)

        assert payload_state.status(ctx) == {
            "state": "invalid",
            "detail": "payload transaction journal is missing",
        }
        with pytest.raises(errors.InstallError, match="journal is missing"):
            payload_transaction.recover(ctx, runtime=None)

    @pytest.mark.parametrize(
        ("carrier", "expected"),
        [
            ("root_symlink", "payload transaction root is a symbolic link"),
            ("root_regular_file", "payload transaction root is not a directory"),
            ("journal_missing", "payload transaction journal is missing"),
            ("journal_symlink", "payload transaction journal is a symbolic link"),
            ("journal_directory", "payload transaction journal is not a regular file"),
            ("journal_unreadable", "payload transaction journal could not be read"),
            ("journal_invalid_utf8", "payload transaction journal is malformed JSON"),
            ("journal_malformed", "payload transaction journal is malformed JSON"),
            (
                "journal_noncanonical",
                "payload transaction journal is not canonical JSON",
            ),
            (
                "journal_unsupported_schema",
                "payload transaction journal schema is unsupported",
            ),
            (
                "journal_invalid_fields",
                "payload transaction journal fields are invalid",
            ),
        ],
    )
    def test_recovery_classifies_invalid_carriers_without_mutation(
        self,
        tmp_path: Path,
        carrier: str,
        expected: str,
        *,
        mocker,
    ) -> None:
        ctx = install_context(tmp_path)
        root = Path(payload_state.transaction_root(ctx))
        journal = Path(payload_state.journal_path(ctx))
        target = tmp_path / "retained-target"
        root.parent.mkdir(parents=True, exist_ok=True)
        if carrier == "root_symlink":
            target.mkdir()
            (target / "evidence").write_bytes(b"retained\n")
            root.symlink_to(target, target_is_directory=True)
        elif carrier == "root_regular_file":
            root.write_bytes(b"retained root\n")
        else:
            root.mkdir(parents=True)
            if carrier == "journal_symlink":
                target.write_bytes(b"retained journal\n")
                journal.symlink_to(target)
            elif carrier == "journal_directory":
                journal.mkdir()
                (journal / "evidence").write_bytes(b"retained\n")
            elif carrier == "journal_unreadable":
                journal.write_bytes(b"retained unreadable journal\n")
            elif carrier == "journal_invalid_utf8":
                journal.write_bytes(b"\xff\xfe\x00")
            elif carrier == "journal_malformed":
                journal.write_bytes(b"{not-json\n")
            elif carrier == "journal_noncanonical":
                journal.write_bytes(
                    b'{"schema_version": 1, "state": "prepared", "transaction_id": "tx", '
                    b'"version": "1.2.3", "receipt_sha256": "' + b"0" * 64 + b'", "fresh": true}\n'
                )
            elif carrier == "journal_unsupported_schema":
                journal.write_bytes(
                    payload_digest.canonical_json(
                        {
                            "schema_version": 2,
                            "state": "prepared",
                            "transaction_id": "tx",
                            "version": "1.2.3",
                            "receipt_sha256": "0" * 64,
                            "fresh": True,
                        }
                    )
                )
            elif carrier == "journal_invalid_fields":
                journal.write_bytes(
                    payload_digest.canonical_json(
                        {
                            "schema_version": payload_state.TRANSACTION_JOURNAL_SCHEMA,
                            "state": "prepared",
                            "transaction_id": "",
                            "version": "1.2",
                            "receipt_sha256": "not-a-digest",
                            "fresh": True,
                        }
                    )
                )

        before = _retained_carrier_snapshot(root, target)

        if carrier == "journal_unreadable":
            read_bytes = mocker.patch.object(
                Path,
                "read_bytes",
                side_effect=PermissionError("denied"),
            )
            with pytest.raises(errors.RecoveryStateError, match=expected):
                payload_transaction.recover(ctx, runtime=None)
            mocker.stop(read_bytes)
        else:
            with pytest.raises(errors.RecoveryStateError, match=expected):
                payload_transaction.recover(ctx, runtime=None)

        assert _retained_carrier_snapshot(root, target) == before

    @pytest.mark.parametrize("corruption", ["identity", "release", "receipt"])
    def test_recovery_rejects_candidate_identity_drift(
        self, tmp_path: Path, corruption: str, *, mocker
    ) -> None:
        """Recovery binds the candidate generation to the durable transaction journal."""
        ctx = install_context(tmp_path)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        journal_path = Path(payload_state.journal_path(ctx))
        if corruption == "identity":
            Path(candidate.context.executable).write_bytes(b"corrupt")
            expected = "candidate projection identity is invalid"
        else:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if corruption == "release":
                journal["version"] = "1.2.4"
            else:
                journal["receipt_sha256"] = "f" * 64
            journal_path.write_bytes(payload_digest.canonical_json(journal))
            expected = "candidate does not match the transaction"

        with pytest.raises(errors.RecoveryStateError, match=expected):
            payload_transaction.recover(ctx, runtime=None)

    def test_materialized_recovery_rejects_selection_drift(self, tmp_path: Path, *, mocker) -> None:
        """An unselected candidate may be discarded only from its exact prior selection."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        payload_generation.select(
            ctx,
            active=str(candidate.expected["transaction_id"]),
            predecessor=None,
        )

        with pytest.raises(errors.RecoveryStateError, match="selection changed"):
            payload_transaction.recover(ctx, runtime=None)

    def test_fresh_recovery_rejects_an_unrelated_live_runtime(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """A fresh interrupted projection cannot erase an unrelated accepting runtime."""
        ctx = install_context(tmp_path)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.activate()
        candidate.preserve_for_recovery("runtime identity is unresolved")
        projected = listener_identity.committed_payload(Path(candidate.context.executable))
        assert projected is not None
        unrelated = recovery_runtime(projected)
        unrelated["release"] = "9.9.9"

        with pytest.raises(errors.InstallError, match="does not match the candidate"):
            payload_transaction.recover(ctx, runtime=unrelated)

    def test_installed_state_rejects_a_symlink_even_when_its_target_is_absent(
        self, tmp_path: Path
    ) -> None:
        ctx = install_context(tmp_path)
        installed = Path(payload_state.installed_path(ctx))
        installed.parent.mkdir(parents=True)
        installed.symlink_to(tmp_path / "missing-installed-state.json")

        with pytest.raises(errors.InstallError, match="installed release state is invalid"):
            payload_state.read_installed(ctx)

    def test_recovery_closes_an_unmutated_prepared_transaction(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        before = Path(ctx.executable).read_bytes()
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)

        result = payload_transaction.recover(ctx, runtime=None)

        assert result == {
            "state": "closed",
            "transaction_id": candidate.expected["transaction_id"],
            "version": "1.2.3",
        }
        assert Path(ctx.executable).read_bytes() == before
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_recovery_refuses_a_prepared_transaction_with_unowned_content(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        residue = Path(payload_state.transaction_root(ctx), "unexpected")
        residue.write_text("unknown\n", encoding="utf-8")

        with pytest.raises(errors.InstallError, match="prepared transaction is not empty"):
            payload_transaction.recover(ctx, runtime=None)

        assert residue.is_file()

    def test_fresh_commit_writes_manifest_receipt_and_pending_journal_then_finalize_state(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)

        transaction.commit_projection()

        assert Path(transaction.context.payload_dir, "payload-manifest.json").is_file()
        assert Path(transaction.context.payload_dir, inventory.RELEASE_RECEIPT_FILENAME).is_file()
        journal = json.loads(Path(payload_state.journal_path(ctx)).read_text(encoding="utf-8"))
        assert journal["state"] == "materialized"
        assert not Path(payload_state.installed_path(ctx)).exists()

        transaction.activate()
        transaction.finalize({"pid": 123, "accepting": True})

        state = json.loads(Path(payload_state.installed_path(ctx)).read_text(encoding="utf-8"))
        assert state["version"] == "1.2.3"
        assert state["receipt_sha256"] == transaction.receipt_sha256
        assert state["command"] == ctx.command
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_upgrade_materializes_an_immutable_candidate_generation(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        predecessor_bytes = b"predecessor-native-executable"
        successor_bytes = b"successor-native-executable"
        predecessor = begin_transaction(
            ctx,
            released_artifact("1.2.2", executable_content=predecessor_bytes),
            mocker=mocker,
        )
        predecessor.commit_projection()
        predecessor.activate()
        predecessor.finalize({"pid": 1})
        predecessor_executable = Path(predecessor.context.executable)

        successor = begin_transaction(
            ctx,
            released_artifact("1.2.3", executable_content=successor_bytes),
            mocker=mocker,
        )
        successor.commit_projection()

        assert predecessor_executable.read_bytes() == predecessor_bytes
        assert Path(successor.context.executable).read_bytes() == successor_bytes
        assert Path(successor.context.executable) != predecessor_executable
        assert Path(ctx.executable) != Path(successor.context.executable)

    def test_generation_upgrade_does_not_copy_a_payload_snapshot(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Selected generations remain the recovery authority during upgrade."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)

        successor.commit_projection()

        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        assert (rollback / "command.json").is_file()
        assert not payload_rollback.legacy_snapshot_path(rollback).exists()
        successor.rollback()

    def test_activated_generation_recovery_restores_the_exact_prior_selection(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Forward recovery reverses to the prior active and predecessor generations."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        middle = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        middle.commit_projection()
        middle.activate()
        middle.finalize({"pid": 2})
        before = payload_generation.read(ctx)
        assert before is not None
        candidate = begin_transaction(ctx, released_artifact("1.2.4"), mocker=mocker)
        candidate.commit_projection()
        candidate.activate()
        candidate.preserve_for_recovery("controller outcome unknown")
        previous = listener_identity.committed_payload(
            Path(payload_generation.context(ctx, before.active).executable)
        )
        assert previous is not None

        result = payload_transaction.recover(ctx, runtime=recovery_runtime(previous))

        assert result["state"] == "rolled_back"
        assert payload_generation.read(ctx) == before
        assert not Path(candidate.context.payload_dir).exists()
        assert Path(ctx.command).samefile(payload_generation.context(ctx, before.active).executable)

    def test_activation_selects_candidate_and_retains_only_the_predecessor(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        predecessor = begin_transaction(
            ctx,
            released_artifact("1.2.2", executable_content=b"predecessor"),
            mocker=mocker,
        )
        predecessor.commit_projection()
        predecessor.activate()
        predecessor.finalize({"pid": 1})
        ctx.executable = predecessor.context.executable
        successor = begin_transaction(
            ctx,
            released_artifact("1.2.3", executable_content=b"successor"),
            mocker=mocker,
        )
        successor.commit_projection()

        successor.activate()

        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.active == Path(successor.context.payload_dir).name
        assert selection.predecessor == Path(predecessor.context.payload_dir).name
        assert Path(ctx.command).samefile(successor.context.executable)

    def test_recovery_finishes_activation_when_selection_precedes_command_projection(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Recover the durable selected generation when command projection is interrupted."""
        ctx = install_context(tmp_path)
        predecessor = install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        old_target = Path(predecessor.context.executable)
        expected_target = Path(successor.context.executable)
        interrupted = mocker.patch.object(
            payload_transaction.command,
            "project",
            side_effect=errors.InstallError("command projection interrupted"),
        )
        with pytest.raises(errors.InstallError, match="command projection interrupted"):
            successor.activate()
        mocker.stop(interrupted)

        selection = payload_generation.read(ctx)
        assert selection is not None
        assert selection.active == str(successor.expected["transaction_id"])
        assert Path(ctx.command).samefile(old_target)

        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(candidate, candidate),
        )

        assert result["state"] == "finalized"
        assert Path(ctx.command).samefile(expected_target)

    def test_recovery_rolls_back_when_selection_precedes_the_candidate_runtime(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """A selected candidate is reversible while the predecessor still serves."""
        ctx = install_context(tmp_path)
        predecessor = install_payload(ctx, "1.2.2", mocker=mocker)
        before = payload_generation.read(ctx)
        assert before is not None
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        interrupted = mocker.patch.object(
            payload_transaction.command,
            "project",
            side_effect=errors.InstallError("command projection interrupted"),
        )
        with pytest.raises(errors.InstallError, match="command projection interrupted"):
            successor.activate()
        mocker.stop(interrupted)
        previous = listener_identity.committed_payload(Path(predecessor.context.executable))
        assert previous is not None

        result = payload_transaction.recover(ctx, runtime=recovery_runtime(previous))

        assert result["state"] == "rolled_back"
        assert payload_generation.read(ctx) == before
        assert Path(ctx.command).samefile(predecessor.context.executable)
        assert not Path(successor.context.payload_dir).exists()

    def test_fresh_recovery_rolls_back_a_selected_candidate_without_a_runtime(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """A first-install selector alone does not prove an installed runtime."""
        ctx = install_context(tmp_path)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        interrupted = mocker.patch.object(
            payload_transaction.command,
            "project",
            side_effect=errors.InstallError("command projection interrupted"),
        )
        with pytest.raises(errors.InstallError, match="command projection interrupted"):
            candidate.activate()
        mocker.stop(interrupted)

        result = payload_transaction.recover(ctx, runtime=None)

        assert result["state"] == "rolled_back"
        assert payload_generation.read(ctx) is None
        assert not Path(ctx.install_dir).exists()
        assert not Path(ctx.command).exists()

    def test_recovery_finishes_activation_when_command_precedes_phase_journal(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Recognize durable selector and command state even if the phase journal lags."""
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        expected_target = Path(successor.context.executable).resolve()
        original_write = payload_transaction.state.write_journal

        def interrupt_activated_journal(*args, **kwargs):
            if kwargs.get("state") == "activated":
                raise errors.InstallError("activation journal interrupted")
            return original_write(*args, **kwargs)

        mocker.patch.object(
            payload_transaction.state,
            "write_journal",
            side_effect=interrupt_activated_journal,
        )
        with pytest.raises(errors.InstallError, match="activation journal interrupted"):
            successor.activate()

        assert Path(ctx.command).samefile(expected_target)
        assert payload_state.read_journal(ctx)["state"] == "materialized"

        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(candidate, candidate),
        )

        assert result["state"] == "finalized"
        assert Path(ctx.command).samefile(expected_target)

    def test_recovery_finishes_activation_when_selector_precedes_command_and_phase(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Reconcile a selector-only activation after process interruption."""
        ctx = install_context(tmp_path)
        predecessor = install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        old_target = Path(predecessor.context.executable).resolve()
        expected_target = Path(successor.context.executable).resolve()
        interrupted = mocker.patch.object(
            payload_transaction.command,
            "project",
            side_effect=errors.InstallError("command projection interrupted"),
        )
        with pytest.raises(errors.InstallError, match="command projection interrupted"):
            successor.activate()
        mocker.stop(interrupted)

        assert Path(ctx.command).samefile(old_target)
        assert payload_state.read_journal(ctx)["state"] == "materialized"

        candidate = listener_identity.committed_payload(Path(successor.context.executable))
        assert candidate is not None
        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(candidate, candidate),
        )

        assert result["state"] == "finalized"
        assert Path(ctx.command).samefile(expected_target)

    def test_fresh_transaction_projects_and_rolls_back_the_user_command(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)

        transaction.commit_projection()
        transaction.activate()

        command_path = Path(ctx.command)
        runtime_config = Path(transaction.context.payload_dir, inventory.RUNTIME_CONFIG_FILENAME)
        assert os.path.samefile(command_path, transaction.context.executable)
        assert command_path.is_symlink() is (os.name != "nt")
        assert runtime_config.is_file()

        transaction.rollback()

        assert not command_path.exists()
        assert not runtime_config.exists()

    def test_upgrade_rollback_restores_the_prior_user_command_target(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        prior_target = Path(ctx.executable)
        command_path = Path(ctx.command)
        assert os.path.samefile(command_path, prior_target)

        transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        transaction.commit_projection()
        transaction.activate()
        transaction.rollback()

        assert os.path.samefile(command_path, prior_target)
        assert command_path.is_symlink() is (os.name != "nt")

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
        selection = payload_generation.read(ctx)
        assert selection is not None
        active = payload_generation.context(ctx, selection.active)
        before = {
            relative: Path(active.payload_dir, relative).read_bytes()
            for relative in (
                *runtime_files(),
                inventory.MANIFEST_FILENAME,
                inventory.RELEASE_RECEIPT_FILENAME,
            )
        }
        before_state = Path(payload_state.installed_path(ctx)).read_bytes()

        second = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        second.commit_projection()
        second.rollback()

        restored = payload_generation.read(ctx)
        assert restored == selection
        for relative, content in before.items():
            assert Path(active.payload_dir, relative).read_bytes() == content
        assert Path(payload_state.installed_path(ctx)).read_bytes() == before_state
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_upgrade_rollback_preserves_unknown_content(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local content\n")

        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        transaction.activate()
        assert unknown.read_bytes() == b"local content\n"
        transaction.rollback()

        assert unknown.read_bytes() == b"local content\n"

    def test_nonfresh_rollback_without_retained_snapshot_only_closes_transaction(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir()
        rollback.rmdir()

        transaction.rollback()

        assert not Path(payload_state.transaction_root(ctx)).exists()
        transaction.rollback()

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
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        previous = Path(ctx.executable).read_bytes()
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        selection = payload_generation.read(ctx)
        assert selection is not None
        previous_identity = listener_identity.committed_payload(
            Path(payload_generation.context(ctx, selection.active).executable)
        )
        candidate_identity = listener_identity.committed_payload(Path(candidate.context.executable))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = recovery_runtime(previous_identity)

        result = payload_transaction.recover(ctx, runtime=runtime)

        assert result["state"] == "rolled_back"
        assert Path(ctx.executable).read_bytes() == previous
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_recovery_rolls_back_an_interrupted_committed_upgrade(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        previous = Path(ctx.executable).read_bytes()
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        selection = payload_generation.read(ctx)
        assert selection is not None
        previous_identity = listener_identity.committed_payload(
            Path(payload_generation.context(ctx, selection.active).executable)
        )
        candidate_identity = listener_identity.committed_payload(Path(candidate.context.executable))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = recovery_runtime(previous_identity, candidate_identity)

        result = payload_transaction.recover(ctx, runtime=runtime)

        assert result["state"] == "rolled_back"
        assert Path(ctx.executable).read_bytes() == previous
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_recovery_finalizes_a_verified_successor_after_controller_loss(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.preserve_for_recovery("controller outcome unknown")
        candidate_identity = listener_identity.committed_payload(Path(candidate.context.executable))
        assert candidate_identity is not None
        runtime = recovery_runtime(candidate_identity, candidate_identity)

        result = payload_transaction.recover(ctx, runtime=runtime)

        assert result == {
            "transaction_id": result["transaction_id"],
            "version": "1.2.3",
            "state": "finalized",
        }
        installed = payload_state.read_installed(ctx)
        assert installed is not None
        assert installed["transaction_id"] == result["transaction_id"]
        assert installed["version"] == "1.2.3"
        assert installed["runtime"] == runtime
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_recovery_finalizes_an_activated_fresh_candidate(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """An activated first install can finish after its runtime proves the candidate."""
        ctx = install_context(tmp_path)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.activate()
        candidate.preserve_for_recovery("controller outcome unknown")
        candidate_identity = listener_identity.committed_payload(Path(candidate.context.executable))
        assert candidate_identity is not None

        result = payload_transaction.recover(ctx, runtime=recovery_runtime(candidate_identity))

        assert result["state"] == "finalized"
        assert payload_generation.read(ctx) == payload_generation.Selection(
            str(candidate.expected["transaction_id"]),
            None,
        )
        assert Path(ctx.command).samefile(candidate.context.executable)

    def test_recovery_cleans_a_finalized_transaction_without_rolling_back(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate_identity = listener_identity.committed_payload(Path(candidate.context.executable))
        assert candidate_identity is not None
        runtime = recovery_runtime(candidate_identity, candidate_identity)
        installed = {
            "schema_version": payload_state.INSTALLED_RELEASE_STATE_SCHEMA,
            "version": "1.2.3",
            "receipt_sha256": candidate.receipt_sha256,
            "transaction_id": json.loads(
                Path(payload_state.journal_path(ctx)).read_text(encoding="utf-8")
            )["transaction_id"],
            "command": ctx.command,
            "runtime": runtime,
        }
        Path(payload_state.installed_path(ctx)).write_bytes(
            payload_digest.canonical_json(installed)
        )
        candidate_bytes = Path(ctx.executable).read_bytes()

        result = payload_transaction.recover(ctx, runtime=runtime)

        assert result["state"] == "finalized"
        assert Path(ctx.executable).read_bytes() == candidate_bytes
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_recovery_removes_an_interrupted_fresh_projection_without_a_runtime(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()

        result = payload_transaction.recover(ctx, runtime=None)

        assert result["state"] == "rolled_back"
        assert not Path(ctx.install_dir).exists()
        assert not Path(ctx.command).exists()
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_empty_control_root_remains_a_fresh_install(self, tmp_path: Path, *, mocker) -> None:
        """An empty pre-created control directory does not invent a predecessor."""
        ctx = install_context(tmp_path)
        Path(ctx.install_dir).mkdir(parents=True)

        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        journal = payload_state.read_journal(ctx)

        assert journal["fresh"] is True
        assert "previous_generation" not in journal
        candidate.commit_projection()
        candidate.rollback()
        assert not Path(ctx.install_dir).exists()

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
            "state": "invalid",
            "detail": "payload transaction journal fields are invalid",
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
        transaction.activate()
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
        with pytest.raises(errors.InstallError, match="not activated"):
            transaction.finalize()
        with pytest.raises(errors.InstallError, match="only a materialized"):
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
                previous_generation=None,
            )

        fresh = begin_transaction(
            install_context(Path(tempfile.mkdtemp())),
            released_artifact(),
            mocker=mocker,
        )
        fresh.rollback()
        payload_transaction._remove_transaction_root(fresh._ctx)

    def test_commit_and_cleanup_fail_closed_on_unproved_terminal_state(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        mocker.patch.object(
            payload_transaction.projection,
            "verify_payload_manifest",
            return_value=(False, "tampered"),
        )
        with (
            subtests.test("integrity"),
            pytest.raises(
                errors.InstallError,
                match="committed payload integrity check failed: tampered",
            ),
        ):
            transaction.commit_projection()
        mocker.stopall()

        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        mocker.patch.object(
            payload_transaction.payload_candidate,
            "write_projection",
            side_effect=OSError("write failed"),
        )
        mocker.patch.object(
            payload_transaction.PayloadTransaction,
            "rollback",
            side_effect=errors.InstallError("restore failed"),
        )
        with (
            subtests.test("rollback"),
            pytest.raises(
                errors.InstallError,
                match="payload commit failed and rollback failed: restore failed",
            ),
        ):
            transaction.commit_projection()
        mocker.stopall()

        ctx = install_context(Path(tempfile.mkdtemp()))
        root = payload_transaction.state.transaction_root(ctx)
        root.mkdir(parents=True)
        mocker.patch.object(payload_transaction.shutil, "rmtree", return_value=None)
        with (
            subtests.test("cleanup"),
            pytest.raises(errors.InstallError, match="cleanup did not remove"),
        ):
            payload_transaction._remove_transaction_root(ctx)
