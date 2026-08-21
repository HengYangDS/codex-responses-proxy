"""Payload admission, manifest, and rollback validation contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, cast

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import artifact, owned_files
from codex_responses_proxy.lifecycle import candidate as payload_candidate
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import (
    begin_transaction,
    executable_relative,
    install_context,
    released_artifact,
    runtime_files,
)

ROOT = Path(__file__).resolve().parents[2]


class TestPayloadValidation:
    """Payload admission, manifest, and rollback validation contracts."""

    def test_begin_rejects_existing_transaction_and_invalid_candidate_boundaries(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction_root = Path(payload_state.transaction_root(ctx))
        transaction_root.mkdir(parents=True)
        with pytest.raises(errors.InstallError, match="already exists"):
            begin_transaction(ctx, released_artifact(), mocker=mocker)

        valid = released_artifact()
        blobs, receipt = valid.peek_blobs(), dict(valid.receipt)
        cases = [
            (blobs, "1.2.3-rc1", "0" * 64, receipt, "version is invalid"),
            (blobs, "1.2.3", "short", receipt, "receipt digest is invalid"),
            (
                blobs,
                "1.2.3",
                "0" * 64,
                {**receipt, "version": "0.0.0"},
                "version mismatch",
            ),
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
        ) -> artifact.ArtifactFile:
            return artifact.ArtifactFile(
                path=blob.path,
                mode=mode,
                blob_oid=blob.blob_oid,
                sha256=sha256,
                content=content,
            )

        cases += (
            (
                (
                    altered_blob(mode=cast("Literal['100644', '100755']", "100600")),
                    *blobs[1:],
                ),
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
        )
        for candidate_blobs, version, digest, candidate_receipt, message in cases:
            with (
                subtests.test(message=message),
                pytest.raises(errors.InstallError, match=message),
            ):
                payload_candidate.validate(candidate_blobs, version, digest, candidate_receipt)

    def test_digest_and_unowned_collision_boundaries_fail_closed(self, *, mocker) -> None:
        valid = {
            relative: hashlib.sha256(relative.encode()).hexdigest() for relative in runtime_files()
        }
        with pytest.raises(errors.InstallError, match="declared inventory"):
            payload_projection.serving_payload_sha256({})
        invalid = dict(valid)
        invalid[inventory.PROVIDER_MANIFEST] = "invalid"
        with pytest.raises(errors.InstallError, match="invalid serving payload"):
            payload_projection.serving_payload_sha256(invalid)

        ctx = install_context(Path(tempfile.mkdtemp()))
        collision = Path(ctx.install_dir, inventory.PROVIDER_MANIFEST)
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("unowned", encoding="utf-8")
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.InstallError, match="candidate unowned collision"):
            transaction.commit_projection()

    def test_bundle_payload_accepts_manifested_nested_runtime_files(self) -> None:
        candidate = released_artifact()
        blobs = candidate.peek_blobs()
        nested_content = b"frozen-runtime"
        nested = artifact.ArtifactFile(
            path="bin/_internal/runtime.dat",
            mode="100644",
            blob_oid=hashlib.sha256(nested_content).hexdigest(),
            sha256=hashlib.sha256(nested_content).hexdigest(),
            content=nested_content,
        )
        expanded = (*blobs, nested)
        receipt = dict(candidate.receipt)
        receipt["serving_files"] = [item.path for item in expanded]
        receipt["serving_payload_sha256"] = payload_projection.serving_payload_sha256(
            {item.path: item.sha256 for item in expanded}
        )

        payload_candidate.validate(expanded, "1.2.3", "0" * 64, receipt)

    def test_bundle_prewarm_materializes_runs_and_rejects_failures(
        self, tmp_path: Path, subtests, *, mocker
    ) -> None:
        completed = mocker.patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess(("proxy", "version"), 0),
        )
        executable = tmp_path / "proxy"
        executable.write_bytes(b"native")
        payload_candidate.prewarm(executable)
        arguments = completed.call_args.args[0]
        assert arguments[0] == str(executable)
        assert arguments[1:] == ["version"]
        environment = completed.call_args.kwargs["env"]
        assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        assert "PYTHONHOME" not in environment
        assert "PYTHONPATH" not in environment
        assert completed.call_args.kwargs["timeout"] == 120

        for effect in (
            subprocess.CompletedProcess(("proxy", "version"), 2),
            OSError("cannot execute"),
            subprocess.TimeoutExpired(("proxy", "version"), 120),
        ):
            with subtests.test(effect=type(effect).__name__):
                mocker.patch.object(
                    subprocess,
                    "run",
                    side_effect=effect if isinstance(effect, BaseException) else None,
                    return_value=effect if not isinstance(effect, BaseException) else None,
                )
                with pytest.raises(errors.InstallError, match="prewarm failed"):
                    payload_candidate.prewarm(executable)

    def test_transaction_filesystem_failures_remain_fail_closed(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))

        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        mocker.patch.object(payload_digest, "sha256_file", return_value="0" * 64)
        with pytest.raises(errors.InstallError, match="installed payload digest mismatch"):
            transaction.commit_projection()

        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir(parents=True)
        snapshot = {
            "schema_version": 3,
            "present": {inventory.PROVIDER_MANIFEST: {"sha256": "0" * 64, "mode": 0o644}},
            "owned": sorted({*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA}),
        }
        (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
        with pytest.raises(errors.InstallError, match=r"rollback.*unavailable"):
            payload_rollback.restore_snapshot(ctx, rollback)

    def test_rollback_reports_symlink_and_read_failures(self, *, mocker, tmp_path: Path) -> None:
        ctx = install_context(tmp_path / "install-root")
        manifest = payload_projection.payload_manifest_path(ctx)
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(tmp_path / "missing")
        with pytest.raises(errors.InstallError, match="manifest is a symlink"):
            payload_rollback.write_snapshot(ctx, tmp_path / "snapshot")

        source = tmp_path / "source"
        source.write_bytes(b"payload")
        read = mocker.patch.object(Path, "read_bytes", side_effect=OSError("blocked"))
        with pytest.raises(errors.InstallError, match="snapshot read failed"):
            payload_rollback._snapshot_file(source, tmp_path / "target")
        mocker.stop(read)

        ctx = install_context(tmp_path / "restore-root")
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir(parents=True)
        content = b"retained"
        snapshot = {
            "schema_version": 3,
            "present": {
                inventory.PROVIDER_MANIFEST: {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "mode": 0o644,
                }
            },
            "owned": sorted({*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA}),
        }
        (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
        retained = rollback / inventory.PROVIDER_MANIFEST
        retained.parent.mkdir(parents=True, exist_ok=True)
        retained.write_bytes(content)

        mocker.patch.object(
            payload_rollback,
            "load_inventory",
            return_value=payload_rollback.RollbackInventory(
                present={
                    inventory.PROVIDER_MANIFEST: (
                        hashlib.sha256(content).hexdigest(),
                        0o644,
                    )
                },
                owned=frozenset({*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA}),
            ),
        )
        unreadable = mocker.patch.object(
            retained.__class__, "read_bytes", side_effect=OSError("blocked")
        )
        with pytest.raises(errors.InstallError, match="rollback is unreadable"):
            payload_rollback.restore_snapshot(ctx, rollback)
        mocker.stop(unreadable)
        mocker.stopall()

        retained.write_bytes(b"tampered")
        with pytest.raises(errors.InstallError, match="rollback digest mismatch"):
            payload_rollback.restore_snapshot(ctx, rollback)

        retained.write_bytes(content)
        mocker.patch.object(payload_digest, "sha256_file", return_value="0" * 64)
        with pytest.raises(errors.InstallError, match="restored payload digest mismatch"):
            payload_rollback.restore_snapshot(ctx, rollback)

    def test_manifest_verifier_reports_each_metadata_boundary(self, subtests, *, mocker) -> None:
        def installed() -> tuple[runtime_context.RuntimeContext, Path, dict[str, object]]:
            ctx = install_context(Path(tempfile.mkdtemp()))
            transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
            path = Path(payload_projection.payload_manifest_path(ctx))
            return ctx, path, json.loads(path.read_text())

        ctx = install_context(Path(tempfile.mkdtemp()))
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert detail == "installed payload manifest is unavailable"

        ctx, path, _ = installed()
        path.write_text("not-json")
        assert payload_projection.verify_payload_manifest(ctx)[1] == (
            "installed payload manifest is unavailable"
        )

        mutations = [
            (
                lambda value: value.update(schema_version=99),
                "manifest schema is unsupported",
            ),
            (lambda value: value.pop("release"), "manifest is incomplete"),
            (
                lambda value: value["files"].pop(executable_relative()),
                "manifest file set mismatch",
            ),
            (
                lambda value: value["serving_files"].pop(runtime_files()[-1]),
                "manifest serving file set mismatch",
            ),
            (
                lambda value: value["files"].update({executable_relative(): "short"}),
                "invalid digest",
            ),
            (
                lambda value: value["serving_files"].update(
                    {inventory.PROVIDER_MANIFEST: "0" * 64}
                ),
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
            with subtests.test(message=message):
                ok, detail = payload_projection.verify_payload_manifest(ctx)
                assert not ok
                assert message in detail

        ctx, _, _ = installed()
        Path(ctx.executable).unlink()
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert detail == "installed payload file is unavailable: bin/codex-responses-proxy"

        ctx, _, _ = installed()
        invalid_aggregate = mocker.patch.object(
            payload_projection,
            "serving_payload_sha256",
            side_effect=errors.InstallError("invalid serving payload digest"),
        )
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert "invalid serving payload" in detail
        mocker.stop(invalid_aggregate)

        ctx, _, _ = installed()
        unavailable_digest = mocker.patch.object(
            payload_digest,
            "sha256_file",
            side_effect=OSError("blocked"),
        )
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert detail == "installed payload file is unavailable: bin/codex-responses-proxy"
        mocker.stop(unavailable_digest)

        ctx, _, _ = installed()
        receipt = Path(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME)
        receipt.unlink()
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert detail == "installed release receipt is unavailable"

    def test_canonical_state_and_rollback_validation_fail_closed(self, subtests) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        path = Path(ctx.install_dir, "state.json")
        path.parent.mkdir(parents=True)
        path.write_text('{"value": 1}', encoding="utf-8")
        with pytest.raises(errors.InstallError, match="not canonical JSON"):
            owned_files.read_canonical_json(path, "state")
        path.write_bytes(b"\xff")
        with pytest.raises(errors.InstallError, match="unavailable or invalid"):
            owned_files.read_canonical_json(path, "state")

        installed_state = Path(payload_state.installed_path(ctx))
        installed_state.write_bytes(payload_digest.canonical_json({"schema_version": 99}))
        with pytest.raises(errors.InstallError, match="schema is unsupported"):
            payload_state.read_installed(ctx)
        with pytest.raises(errors.InstallError, match="state version is invalid"):
            payload_state.require_version({"version": "latest"})
        with pytest.raises(errors.InstallError, match="state command path is invalid"):
            payload_state.require_command({"command": "relative/command"})

        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir(parents=True)
        cases = (
            ({"schema_version": 1, "present": {}}, "snapshot is invalid"),
            (
                {
                    "schema_version": 3,
                    "present": [],
                    "owned": [],
                },
                "snapshot is invalid",
            ),
            (
                {
                    "schema_version": 3,
                    "present": {inventory.PROVIDER_MANIFEST: {"sha256": "short", "mode": 0o644}},
                    "owned": sorted({*runtime_files(), *owned_files.OWNED_PAYLOAD_METADATA}),
                },
                "metadata is invalid",
            ),
            (
                {
                    "schema_version": 3,
                    "present": {},
                    "owned": [inventory.PROVIDER_MANIFEST],
                },
                "owned inventory is invalid",
            ),
        )
        for snapshot, message in cases:
            with subtests.test(message=message):
                (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
                with pytest.raises(errors.InstallError, match=message):
                    payload_rollback.restore_snapshot(ctx, rollback)

    def test_owned_file_boundaries_reject_invalid_types_and_path_races(
        self, tmp_path: Path, *, mocker
    ) -> None:
        """Exercise each fail-closed filesystem type boundary without private host paths."""

        with pytest.raises(errors.InstallError, match="non-empty string"):
            owned_files.canonical_relative(None, "fixture")

        root_file = tmp_path / "root-file"
        root_file.write_text("not a directory", encoding="utf-8")
        with pytest.raises(errors.InstallError, match="root is not a real directory"):
            owned_files.regular_file(root_file, "payload", "fixture")

        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(errors.InstallError, match="not canonical"):
            owned_files.canonical_relative("../payload", "fixture")
        ancestor = root / "ancestor"
        ancestor.write_text("not a directory", encoding="utf-8")
        with pytest.raises(errors.InstallError, match="ancestor is not a directory"):
            owned_files.regular_file(root, "ancestor/payload", "fixture")

        linked_ancestor = root / "linked-ancestor"
        linked_ancestor.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(errors.InstallError, match="symlink ancestor"):
            owned_files.regular_file(root, "linked-ancestor/payload", "fixture")

        unavailable = mocker.patch.object(Path, "lstat", side_effect=PermissionError("blocked"))
        with pytest.raises(errors.InstallError, match="path is unavailable"):
            owned_files.regular_file(root, "payload", "fixture")
        mocker.stop(unavailable)

        symlink = root / "symlink"
        symlink.symlink_to(ancestor)
        with pytest.raises(errors.InstallError, match="path is a symlink"):
            owned_files.regular_file(root, "symlink", "fixture")

        directory = root / "directory"
        directory.mkdir()
        with pytest.raises(errors.InstallError, match="not a regular file"):
            owned_files.regular_file(root, "directory", "fixture")
        with pytest.raises(errors.InstallError, match="owned path is not a regular file"):
            owned_files.write_bytes(directory, b"content", root=root)

        target = root / "changed-type"
        calls = 0

        def change_target_type(_target: Path, _root: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                target.mkdir()

        mocker.patch.object(owned_files, "_real_parent", side_effect=change_target_type)
        with pytest.raises(errors.InstallError, match="owned path changed type"):
            owned_files.write_bytes(target, b"content", root=root)
        mocker.stopall()

        sequence = root / "sequence.json"
        sequence.write_text("[]", encoding="utf-8")
        with pytest.raises(errors.InstallError, match="not a JSON object"):
            owned_files.read_json_object(sequence, "fixture JSON")
        sequence.write_bytes(b"\xff")
        with pytest.raises(errors.InstallError, match="unavailable or invalid"):
            owned_files.read_json_object(sequence, "fixture JSON")

        outside = tmp_path / "outside" / "payload"
        with pytest.raises(errors.InstallError, match="escapes its root"):
            owned_files._real_parent(outside, root)

        real_root = tmp_path / "real-root"
        real_root.mkdir()
        linked_root = tmp_path / "linked-root"
        linked_root.symlink_to(real_root, target_is_directory=True)
        with pytest.raises(errors.InstallError, match="root is a symlink"):
            owned_files._real_parent(linked_root / "payload", linked_root)

        parent_file = real_root / "parent"
        parent_file.write_text("not a directory", encoding="utf-8")
        with pytest.raises(errors.InstallError, match="ancestor is not a directory"):
            owned_files._real_parent(parent_file / "payload", real_root)

        root_type = mocker.patch.object(Path, "mkdir")
        directory_type = mocker.patch.object(Path, "is_dir", return_value=False)
        with pytest.raises(errors.InstallError, match="root is not a real directory"):
            owned_files._real_parent(real_root / "payload", real_root)
        mocker.stop(root_type)
        mocker.stop(directory_type)

        linked_parent = real_root / "linked-parent"
        linked_parent.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(errors.InstallError, match="symlink ancestor"):
            owned_files._real_parent(linked_parent / "payload", real_root)
