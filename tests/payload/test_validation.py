#!/usr/bin/env python3
"""Payload admission, manifest, and rollback validation contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path
from typing import Literal, cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.payload import candidate as payload_candidate
from codex_responses_proxy.payload import inventory
from codex_responses_proxy.payload import projection as payload_projection
from codex_responses_proxy.payload import rollback as payload_rollback
from codex_responses_proxy.payload import source as payload_source
from codex_responses_proxy.payload import digest as payload_digest
from codex_responses_proxy.payload import owned_files
from codex_responses_proxy.payload import state as payload_state
from codex_responses_proxy.runtime import context as runtime_context
from tests.deployment.fixtures import install_context
from tests.payload.fixtures import begin_transaction, released_fixture


class TestPayloadValidation(unittest.TestCase):
    """Payload admission, manifest, and rollback validation contracts."""

    def test_begin_rejects_existing_transaction_and_invalid_candidate_boundaries(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        transaction_root = Path(payload_state.transaction_root(ctx))
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
        ) -> payload_source.ReleasedBlob:
            return payload_source.ReleasedBlob(
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
                payload_candidate.validate(candidate_blobs, version, digest, candidate_receipt)

    def test_digest_boundary_and_retired_residue_types_fail_closed(self) -> None:
        valid = {
            relative: hashlib.sha256(relative.encode()).hexdigest()
            for relative in inventory.SERVING_FILES
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
            mock.patch.object(payload_digest, "sha256_file", return_value="0" * 64),
            self.assertRaisesRegex(errors.InstallError, "installed payload digest mismatch"),
        ):
            transaction.commit_projection()

        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir(parents=True)
        retired = "proxy/dmx_responses_proxy.py"
        snapshot = {
            "schema_version": 2,
            "present": {retired: {"sha256": "0" * 64, "mode": 0o644}},
            "retired": [retired],
            "retired_owned_sha256": payload_rollback.path_set_sha256({retired}),
            "previous_owned": [retired],
        }
        (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
        with self.assertRaisesRegex(errors.InstallError, "rollback.*unavailable"):
            payload_rollback.restore_snapshot(ctx, rollback)

    def test_manifest_verifier_reports_each_metadata_boundary(self) -> None:
        def installed() -> tuple[runtime_context.RuntimeContext, Path, dict[str, object]]:
            ctx = install_context(Path(tempfile.mkdtemp()))
            transaction = begin_transaction(ctx, released_fixture())
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
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
            (
                lambda value: value["files"].pop("codex_responses_proxy/commands/control.py"),
                "manifest file set mismatch",
            ),
            (
                lambda value: value["serving_files"].pop(inventory.SERVING_FILES[-1]),
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
        Path(ctx.install_dir, "codex_responses_proxy/commands/control.py").unlink()
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
            payload_digest,
            "sha256_file",
            side_effect=OSError("blocked"),
        ):
            ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("payload unavailable", detail)

        ctx, _, _ = installed()
        receipt = Path(ctx.install_dir, inventory.RELEASE_RECEIPT_FILENAME)
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
            owned_files.read_canonical_json(path, "state")
        path.write_bytes(b"\xff")
        with self.assertRaisesRegex(errors.InstallError, "unavailable or invalid"):
            owned_files.read_canonical_json(path, "state")

        installed_state = Path(payload_state.installed_path(ctx))
        installed_state.write_bytes(payload_digest.canonical_json({"schema_version": 99}))
        with self.assertRaisesRegex(errors.InstallError, "schema is unsupported"):
            payload_state.read_installed(ctx)
        with self.assertRaisesRegex(errors.InstallError, "state version is invalid"):
            payload_state.require_version({"version": "latest"})

        rollback = Path(payload_state.transaction_root(ctx), "rollback")
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
                    "retired_owned_sha256": payload_rollback.path_set_sha256(set()),
                    "previous_owned": ["VERSION"],
                },
                "metadata is invalid",
            ),
            (
                {
                    "schema_version": 2,
                    "present": {},
                    "retired": ["proxy/owned.py"],
                    "retired_owned_sha256": payload_rollback.path_set_sha256({"proxy/owned.py"}),
                    "previous_owned": ["proxy/owned.py"],
                },
                "retired inventory is incomplete",
            ),
        )
        for snapshot, message in cases:
            with self.subTest(message=message):
                (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
                with self.assertRaisesRegex(errors.InstallError, message):
                    payload_rollback.restore_snapshot(ctx, rollback)


if __name__ == "__main__":
    unittest.main(verbosity=2)
