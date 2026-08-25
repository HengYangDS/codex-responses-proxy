"""Receipt-bound payload transaction lifecycle and recovery contracts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import artifact
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
    candidate_identity: listener_identity.LoadedPayloadIdentity,
) -> dict[str, object]:
    """Project one accepting runtime against the committed candidate manifest."""

    return {
        "pid": 321,
        "release": runtime_identity.release,
        "serving_payload_sha256": runtime_identity.serving_payload_sha256,
        "release_receipt_sha256": runtime_identity.release_receipt_sha256,
        "payload_manifest_sha256": candidate_identity.manifest_sha256,
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


def test_commit_prewarms_the_exact_installed_executable(tmp_path: Path, *, mocker) -> None:
    ctx = install_context(tmp_path)
    candidate = released_artifact()
    prewarm = mocker.patch.object(payload_transaction.payload_candidate, "prewarm")

    transaction = payload_transaction.begin_transaction(ctx, candidate)
    prewarm.assert_not_called()

    transaction.commit_projection()

    prewarm.assert_called_once_with(Path(ctx.executable))
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
    introduced = Path(ctx.install_dir, extra.path)
    assert introduced.read_bytes() == content
    transaction.rollback()
    assert not introduced.exists()


def test_upgrade_retires_previous_only_owned_files_and_rollback_restores_them(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    install_payload(ctx, "1.2.2", mocker=mocker)
    previous_only = Path(ctx.install_dir, "bin/_internal/legacy.dist-info/METADATA")
    previous_only.parent.mkdir(parents=True)
    previous_only.write_bytes(b"legacy release metadata\n")
    obsolete_empty_directory = previous_only.parent / "licenses"
    nested_obsolete_empty_directory = obsolete_empty_directory / "metadata"
    nested_obsolete_empty_directory.mkdir(parents=True)
    manifest_path = Path(ctx.install_dir, inventory.MANIFEST_FILENAME)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_digest = hashlib.sha256(previous_only.read_bytes()).hexdigest()
    manifest["files"]["bin/_internal/legacy.dist-info/METADATA"] = previous_digest
    manifest["serving_files"]["bin/_internal/legacy.dist-info/METADATA"] = previous_digest
    manifest["serving_payload_sha256"] = payload_projection.manifest_serving_payload_sha256(
        manifest["serving_files"]
    )
    manifest_path.write_bytes(payload_projection.manifest_bytes(manifest))
    unknown = Path(ctx.install_dir, "operator-notes.txt")
    unknown.write_bytes(b"preserve me\n")

    transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
    transaction.commit_projection()

    assert not previous_only.exists()
    assert not previous_only.parent.exists()
    assert not obsolete_empty_directory.exists()
    assert not nested_obsolete_empty_directory.exists()
    assert unknown.read_bytes() == b"preserve me\n"

    transaction.rollback()

    assert previous_only.read_bytes() == b"legacy release metadata\n"
    assert not obsolete_empty_directory.exists()
    assert unknown.read_bytes() == b"preserve me\n"


def test_finalized_upgrade_purge_leaves_only_unknown_content(tmp_path: Path, *, mocker) -> None:
    ctx = install_context(tmp_path)
    install_payload(ctx, "1.2.2", mocker=mocker)
    previous_only = Path(ctx.install_dir, "bin/_internal/legacy.dist-info/METADATA")
    previous_only.parent.mkdir(parents=True)
    previous_only.write_bytes(b"legacy release metadata\n")
    manifest_path = Path(ctx.install_dir, inventory.MANIFEST_FILENAME)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_digest = hashlib.sha256(previous_only.read_bytes()).hexdigest()
    manifest["files"]["bin/_internal/legacy.dist-info/METADATA"] = previous_digest
    manifest["serving_files"]["bin/_internal/legacy.dist-info/METADATA"] = previous_digest
    manifest["serving_payload_sha256"] = payload_projection.manifest_serving_payload_sha256(
        manifest["serving_files"]
    )
    manifest_path.write_bytes(payload_projection.manifest_bytes(manifest))
    unknown = Path(ctx.install_dir, "operator-notes.txt")
    unknown.write_bytes(b"preserve me\n")

    transaction = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
    transaction.commit_projection()
    transaction.finalize({"pid": 2})

    remaining = payload_projection.purge_installed_projection(ctx)

    assert remaining == ("operator-notes.txt",)
    assert unknown.read_bytes() == b"preserve me\n"
    assert not previous_only.exists()
    assert not Path(ctx.install_dir, inventory.RUNTIME_CONFIG_FILENAME).exists()


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

    def test_finalize_retains_no_generation_for_a_fresh_install(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))

        install_payload(ctx, "1.2.2", mocker=mocker)

        assert not payload_state.retained_rollback_root(ctx).exists()

    def test_finalize_retains_exactly_the_displaced_predecessor(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)

        successor.commit_projection()
        successor.finalize({"pid": 2})

        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"
        assert retained.successor.release == "1.2.3"
        assert tuple(payload_state.retained_generations(ctx)) == (retained.root,)

    def test_a_later_finalize_replaces_the_retained_predecessor(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        middle = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        middle.commit_projection()
        middle.finalize({"pid": 2})
        first = payload_rollback.load_retained(ctx)
        latest = begin_transaction(ctx, released_artifact("1.2.4"), mocker=mocker)

        latest.commit_projection()
        latest.finalize({"pid": 3})

        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.3"
        assert retained.successor.release == "1.2.4"
        assert retained.root != first.root
        assert tuple(payload_state.retained_generations(ctx)) == (retained.root,)

    def test_finalize_preserves_recoverable_state_when_retention_promotion_fails(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        mocker.patch.object(
            payload_transaction.payload_rollback,
            "promote",
            side_effect=errors.InstallError("retention failed"),
        )

        with pytest.raises(errors.InstallError, match="retention failed"):
            successor.finalize({"pid": 2})

        journal = payload_state.status(ctx)
        assert journal is not None
        assert journal["state"] == "recovery_required"
        assert payload_state.read_journal(ctx)["reason"] == "finalization failed: retention failed"
        assert Path(payload_state.transaction_root(ctx), "rollback").is_dir()

    def test_recovery_finalization_promotes_the_retained_predecessor(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        projected = listener_identity.committed_payload(Path(ctx.executable))
        assert projected is not None

        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(projected, projected),
        )

        assert result["state"] == "finalized"
        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"
        assert retained.successor.release == "1.2.3"

    def test_recovery_finalization_failure_remains_recoverable(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        projected = listener_identity.committed_payload(Path(ctx.executable))
        assert projected is not None
        mocker.patch.object(
            payload_transaction.payload_rollback,
            "promote",
            side_effect=errors.InstallError("retention failed"),
        )

        with pytest.raises(errors.InstallError, match="retention failed"):
            payload_transaction.recover(
                ctx,
                runtime=recovery_runtime(projected, projected),
            )

        journal = payload_state.read_journal(ctx)
        assert journal["state"] == "recovery_required"
        assert journal["reason"] == "finalization failed: retention failed"

    def test_recovery_retries_retention_after_installed_state_was_written(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        projected = listener_identity.committed_payload(Path(ctx.executable))
        assert projected is not None
        original_promote = payload_transaction.payload_rollback.promote
        promote = mocker.patch.object(
            payload_transaction.payload_rollback,
            "promote",
            side_effect=[errors.InstallError("retention failed"), None],
        )
        with pytest.raises(errors.InstallError, match="retention failed"):
            successor.finalize(recovery_runtime(projected, projected))
        promote.side_effect = original_promote

        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(projected, projected),
        )

        assert result["state"] == "finalized"
        retained = payload_rollback.load_retained(ctx)
        assert retained.predecessor.release == "1.2.2"
        assert retained.successor.release == "1.2.3"

    def test_recovery_resumes_after_generation_move_before_selection(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        projected = listener_identity.committed_payload(Path(ctx.executable))
        assert projected is not None
        pointer = payload_state.retained_rollback_pointer(ctx)
        original_write = payload_rollback.owned_files.write_bytes

        def interrupt_selection(target, content, **kwargs):
            if target == pointer:
                raise errors.InstallError("selection interrupted")
            return original_write(target, content, **kwargs)

        write_bytes = mocker.patch.object(
            payload_rollback.owned_files,
            "write_bytes",
            side_effect=interrupt_selection,
        )

        with pytest.raises(errors.InstallError, match="selection interrupted"):
            successor.finalize(recovery_runtime(projected, projected))

        transaction_root = payload_state.transaction_root(ctx)
        generation = (
            payload_state.retained_rollback_root(ctx)
            / "generations"
            / str(successor.expected["transaction_id"])
        )
        assert not (transaction_root / "rollback").exists()
        assert generation.is_dir()
        assert not pointer.exists()
        assert payload_state.read_journal(ctx)["state"] == "recovery_required"
        write_bytes.side_effect = original_write

        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(projected, projected),
        )

        assert result["state"] == "finalized"
        assert payload_rollback.load_retained(ctx).root == generation
        assert not transaction_root.exists()

    def test_recovery_resumes_after_selection_before_obsolete_cleanup(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        middle = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        middle.commit_projection()
        middle.finalize({"pid": 2})
        old_generation = payload_rollback.load_retained(ctx).root
        latest = begin_transaction(ctx, released_artifact("1.2.4"), mocker=mocker)
        latest.commit_projection()
        projected = listener_identity.committed_payload(Path(ctx.executable))
        assert projected is not None
        original_remove = payload_rollback.shutil.rmtree

        def interrupt_cleanup(path):
            if path == old_generation:
                raise OSError("cleanup interrupted")
            return original_remove(path)

        remove = mocker.patch.object(
            payload_rollback.shutil,
            "rmtree",
            side_effect=interrupt_cleanup,
        )

        with pytest.raises(errors.InstallError, match="generation cleanup failed"):
            latest.finalize(recovery_runtime(projected, projected))

        pointer = payload_state.retained_rollback_pointer(ctx)
        selected = payload_digest.canonical_json(
            {
                "schema_version": payload_rollback.RETAINED_BINDING_SCHEMA,
                "generation": latest.expected["transaction_id"],
            }
        )
        assert pointer.read_bytes() == selected
        assert old_generation.is_dir()
        assert payload_state.read_journal(ctx)["state"] == "recovery_required"
        remove.side_effect = original_remove

        result = payload_transaction.recover(
            ctx,
            runtime=recovery_runtime(projected, projected),
        )

        retained = payload_rollback.load_retained(ctx)
        assert result["state"] == "finalized"
        assert retained.predecessor.release == "1.2.3"
        assert retained.successor.release == "1.2.4"
        assert not old_generation.exists()
        assert tuple(payload_state.retained_generations(ctx)) == (retained.root,)

    def test_retained_predecessor_mints_an_exact_reverse_transaction(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(payload_transaction.payload_candidate, "prewarm")
        first = payload_transaction.begin_transaction(ctx, released_artifact("1.2.2"))
        first.commit_projection()
        first.finalize({"pid": 1})
        successor = payload_transaction.begin_transaction(ctx, released_artifact("1.2.3"))
        successor.commit_projection()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)

        reverse = payload_transaction.begin_rollback_transaction(ctx, retained)
        reverse.commit_projection()

        restored = listener_identity.committed_payload(Path(ctx.executable))
        assert restored is not None
        assert restored.release == "1.2.2"
        reverse.rollback()
        current = listener_identity.committed_payload(Path(ctx.executable))
        assert current is not None
        assert current.release == "1.2.3"

    def test_retained_predecessor_rejects_corruption_before_mutation(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        executable = retained.root / executable_relative()
        executable.write_bytes(b"corrupt")
        before = Path(ctx.executable).read_bytes()

        with pytest.raises(errors.InstallError, match="predecessor identity"):
            payload_rollback.load_retained(ctx)

        assert Path(ctx.executable).read_bytes() == before

    @pytest.mark.parametrize(
        "mutation",
        [
            "pointer_symlink",
            "pointer_generation_path",
            "extra_generation",
            "extra_generation_file",
            "extra_generation_symlink",
            "binding_successor",
        ],
    )
    def test_retained_predecessor_rejects_ambiguous_carrier_shape(
        self, tmp_path: Path, mutation: str, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        pointer = payload_state.retained_rollback_pointer(ctx)
        external = tmp_path / "external.json"

        if mutation == "pointer_symlink":
            external.write_bytes(pointer.read_bytes())
            pointer.unlink()
            pointer.symlink_to(external)
        elif mutation == "pointer_generation_path":
            pointer.write_bytes(
                payload_digest.canonical_json({"schema_version": 1, "generation": "../outside"})
            )
        elif mutation == "extra_generation":
            (retained.root.parent / ("f" * 32)).mkdir()
        elif mutation == "extra_generation_file":
            (retained.root.parent / "unexpected").write_text("residue\n", encoding="utf-8")
        elif mutation == "extra_generation_symlink":
            target = tmp_path / "external-generation"
            target.mkdir()
            (retained.root.parent / "unexpected").symlink_to(target, target_is_directory=True)
        else:
            binding_path = retained.root / payload_rollback.RETAINED_BINDING_FILENAME
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["successor"]["release"] = "9.9.9"
            binding_path.write_bytes(payload_digest.canonical_json(binding))

        with pytest.raises(errors.InstallError, match="retained rollback"):
            payload_rollback.load_retained(ctx)

    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ("root_file", "root is unavailable or invalid"),
            ("generation_missing", "generation is unavailable or invalid"),
            ("successor_missing", "successor is unavailable"),
        ],
    )
    def test_retained_predecessor_rejects_missing_authority_surfaces(
        self, tmp_path: Path, mutation: str, expected: str, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        successor.commit_projection()
        successor.finalize({"pid": 2})
        retained = payload_rollback.load_retained(ctx)
        retained_root = payload_state.retained_rollback_root(ctx)

        if mutation == "root_file":
            external = tmp_path / "retained-copy"
            retained_root.rename(external)
            retained_root.write_text("not a retained store\n", encoding="utf-8")
        elif mutation == "generation_missing":
            retained.root.rename(tmp_path / "removed-generation")
        else:
            Path(ctx.executable).unlink()

        with pytest.raises(errors.InstallError, match=expected):
            payload_rollback.load_retained(ctx)

    def test_retained_promotion_rejects_ambiguous_and_unmovable_sources(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = listener_identity.committed_payload(Path(ctx.executable))
        assert successor is not None
        source = tmp_path / "source"
        generation = tmp_path / "generation"
        source.mkdir()
        generation.mkdir()

        with pytest.raises(errors.InstallError, match="source is ambiguous"):
            payload_rollback._materialize_generation(source, generation, "a" * 32, successor)

        generation.rmdir()
        source.rmdir()
        source.write_text("not a directory\n", encoding="utf-8")
        generation.mkdir()
        with pytest.raises(errors.InstallError, match="source is invalid"):
            payload_rollback._materialize_generation(source, generation, "b" * 32, successor)

        source.unlink()
        generation.rmdir()
        source.mkdir()
        payload_rollback.write_snapshot(ctx, source)
        payload_rollback.command.write_snapshot(
            source,
            payload_rollback.command.snapshot(Path(ctx.command), Path(ctx.executable)),
        )
        original_replace = payload_rollback.os.replace

        def reject_generation_move(source_path: Path, target_path: Path) -> None:
            if source_path == source and target_path == generation:
                raise OSError("offline")
            original_replace(source_path, target_path)

        mocker.patch.object(payload_rollback.os, "replace", side_effect=reject_generation_move)
        with pytest.raises(errors.InstallError, match="generation move failed"):
            payload_rollback._materialize_generation(source, generation, "c" * 32, successor)

    def test_retained_promotion_and_removal_reject_symlinked_store(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_payload(ctx, "1.2.2", mocker=mocker)
        successor = listener_identity.committed_payload(Path(ctx.executable))
        assert successor is not None
        installed = payload_state.read_installed(ctx)
        assert installed is not None
        transaction_id = str(installed["transaction_id"])
        retained_root = payload_state.retained_rollback_root(ctx)
        external = tmp_path / "external-retained"
        external.mkdir()
        retained_root.symlink_to(external, target_is_directory=True)

        with pytest.raises(errors.InstallError, match="root is a symbolic link"):
            payload_rollback.promote(
                ctx,
                tmp_path / "snapshot",
                transaction_id=transaction_id,
                successor=successor.handoff(),
            )
        with pytest.raises(errors.InstallError, match="root is a symbolic link"):
            payload_rollback.remove_retained(ctx)
        assert external.is_dir()

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"payload": ["not-an-entry"]},
            {"payload": [{"path": "proxy", "mode": "invalid"}]},
        ],
    )
    def test_retained_candidate_rejects_malformed_release_receipts(
        self, tmp_path: Path, payload: dict[str, object]
    ) -> None:
        root = tmp_path / "retained"
        root.mkdir()
        (root / inventory.RELEASE_RECEIPT_FILENAME).write_bytes(
            payload_digest.canonical_json(payload)
        )
        identity = listener_identity.LoadedPayloadIdentity(
            release="1.2.2",
            serving_payload_sha256="a" * 64,
            release_receipt_sha256="b" * 64,
            manifest_sha256="c" * 64,
            root=root,
        )
        retained = payload_rollback.RetainedRollback(root, identity, identity)

        with pytest.raises(errors.InstallError, match="release receipt is invalid"):
            payload_rollback.candidate(retained)

    def test_retained_candidate_rejects_payload_digest_drift(self, tmp_path: Path) -> None:
        root = tmp_path / "retained"
        root.mkdir()
        relative = inventory.PROVIDER_MANIFEST
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"changed\n")
        receipt = {
            "payload": [
                {
                    "path": relative,
                    "mode": "100644",
                    "blob_oid": "a" * 40,
                    "sha256": hashlib.sha256(b"expected\n").hexdigest(),
                }
            ]
        }
        (root / inventory.RELEASE_RECEIPT_FILENAME).write_bytes(
            payload_digest.canonical_json(receipt)
        )
        identity = listener_identity.LoadedPayloadIdentity(
            release="1.2.2",
            serving_payload_sha256="a" * 64,
            release_receipt_sha256="b" * 64,
            manifest_sha256="c" * 64,
            root=root,
        )

        with pytest.raises(errors.InstallError, match="digest mismatch"):
            payload_rollback.candidate(payload_rollback.RetainedRollback(root, identity, identity))

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

        assert Path(ctx.install_dir, "payload-manifest.json").is_file()
        assert Path(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME).is_file()
        journal = json.loads(Path(payload_state.journal_path(ctx)).read_text(encoding="utf-8"))
        assert journal["state"] == "committed"
        assert not Path(payload_state.installed_path(ctx)).exists()

        transaction.finalize({"pid": 123, "accepting": True})

        state = json.loads(Path(payload_state.installed_path(ctx)).read_text(encoding="utf-8"))
        assert state["version"] == "1.2.3"
        assert state["receipt_sha256"] == transaction.receipt_sha256
        assert state["command"] == ctx.command
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def test_fresh_transaction_projects_and_rolls_back_the_user_command(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)

        transaction.commit_projection()

        command_path = Path(ctx.command)
        runtime_config = Path(ctx.install_dir, inventory.RUNTIME_CONFIG_FILENAME)
        assert os.path.samefile(command_path, ctx.executable)
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
        before = {
            relative: Path(ctx.install_dir, relative).read_bytes()
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

        for relative, content in before.items():
            assert Path(ctx.install_dir, relative).read_bytes() == content
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
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        previous_identity = listener_identity.committed_payload(rollback / executable_relative())
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = recovery_runtime(previous_identity, candidate_identity)

        result = payload_transaction.recover(ctx, runtime=runtime)

        assert result["state"] == "rolled_back"
        assert Path(ctx.executable).read_bytes() == previous
        assert not Path(payload_state.transaction_root(ctx)).exists()

        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate.preserve_for_recovery("handoff outcome unknown")
        root = Path(payload_state.transaction_root(ctx))
        rollback = root / "rollback"
        previous_identity = listener_identity.committed_payload(rollback / executable_relative())
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
        assert previous_identity is not None
        assert candidate_identity is not None
        runtime = recovery_runtime(previous_identity, candidate_identity)
        with pytest.raises(errors.InstallError, match="does not match"):
            payload_transaction.recover(
                ctx,
                runtime={**runtime, "release": "wrong"},
            )
        journal_path = Path(payload_state.journal_path(ctx))
        journal = json.loads(journal_path.read_text())
        journal["receipt_sha256"] = "0" * 64
        journal_path.write_bytes(payload_digest.canonical_json(journal))
        with pytest.raises(errors.InstallError, match="candidate does not match"):
            payload_transaction.recover(ctx, runtime=runtime)
        journal["receipt_sha256"] = candidate.receipt_sha256
        journal_path.write_bytes(payload_digest.canonical_json(journal))
        candidate_executable = Path(ctx.executable)
        candidate_bytes = candidate_executable.read_bytes()
        candidate_executable.write_bytes(b"tampered\n")
        with pytest.raises(errors.InstallError, match="candidate projection identity"):
            payload_transaction.recover(ctx, runtime=runtime)
        candidate_executable.write_bytes(candidate_bytes)
        (root / "rollback" / executable_relative()).write_bytes(b"tampered\n")
        with pytest.raises(errors.InstallError, match="runtime identity is invalid"):
            payload_transaction.recover(ctx, runtime=runtime)
        assert root.exists()

    def test_recovery_rolls_back_an_interrupted_committed_upgrade(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        previous = Path(ctx.executable).read_bytes()
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        previous_identity = listener_identity.committed_payload(rollback / executable_relative())
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
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
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
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

    def test_recovery_cleans_a_finalized_transaction_without_rolling_back(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        candidate = begin_transaction(ctx, released_artifact("1.2.3"), mocker=mocker)
        candidate.commit_projection()
        candidate_identity = listener_identity.committed_payload(Path(ctx.executable))
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
