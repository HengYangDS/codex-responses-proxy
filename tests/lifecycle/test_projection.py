"""Installed payload projection and purge behavior contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import install_payload, released_artifact
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestPayloadProjection:
    """Manifest and installed-projection contracts over opaque release bytes."""

    def test_transaction_installs_complete_runtime_and_manifest(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        manifest = json.loads(
            Path(payload_projection.payload_manifest_path(ctx)).read_text(encoding="utf-8")
        )
        assert sorted(manifest["files"]) == sorted(inventory.RUNTIME_FILES)
        assert sorted(manifest["serving_files"]) == sorted(inventory.SERVING_FILES)
        assert manifest["serving_payload_sha256"] == payload_projection.serving_payload_sha256(
            manifest["serving_files"]
        )
        assert Path(ctx.executable).is_file()
        assert (Path(ctx.install_dir) / inventory.PROVIDER_MANIFEST).is_file()

    def test_fixture_manifest_can_omit_receipt_identity(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        for blob in released_artifact().peek_blobs():
            target = Path(ctx.install_dir, blob.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.content)
        path = payload_projection._write_payload_manifest_for_fixture(ctx)
        assert "release_receipt_sha256" not in json.loads(Path(path).read_text())
        assert payload_projection.verify_payload_manifest(ctx)[0]

    def test_manifest_detects_payload_and_aggregate_tampering(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        proxy = Path(ctx.executable)
        proxy.write_bytes(proxy.read_bytes() + b"# tampered\n")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert "hash mismatch" in detail

        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["serving_payload_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        assert not ok
        assert detail == "serving payload aggregate mismatch"

    def test_purge_unlinks_only_manifest_owned_payload_and_preserves_unknown_content(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        install = Path(ctx.install_dir)
        unknown = install / "operator-note.txt"
        unknown.write_text("keep\n", encoding="utf-8")

        remaining = payload_projection.purge_installed_projection(ctx)

        assert remaining == ("operator-note.txt",)
        assert unknown.read_text(encoding="utf-8") == "keep\n"
        assert not Path(payload_projection.payload_manifest_path(ctx)).exists()
        for relative in inventory.RUNTIME_FILES:
            assert not (install / relative).exists()

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
        (install / inventory.MANIFEST_FILENAME).write_bytes(payload_digest.canonical_json(manifest))

        with pytest.raises(errors.InstallError, match="file set is unsupported"):
            payload_projection.purge_installed_projection(ctx)
        assert (install / "operator-note.txt").read_bytes() == b"keep\n"

    def test_purge_fails_closed_without_one_valid_manifest(self, subtests) -> None:
        for mutate, message in (
            (lambda _ctx: None, "manifest is required"),
            (
                lambda ctx: Path(payload_projection.payload_manifest_path(ctx)).symlink_to(
                    Path(ctx.install_dir, "VERSION")
                ),
                "manifest is a symlink",
            ),
        ):
            with subtests.test(message=message):
                ctx = install_context(Path(tempfile.mkdtemp()))
                marker = Path(ctx.install_dir, "VERSION")
                marker.parent.mkdir(parents=True)
                marker.write_text("1.2.3\n", encoding="utf-8")
                mutate(ctx)
                with pytest.raises(errors.InstallError, match=message):
                    payload_projection.purge_installed_projection(ctx)
                assert marker.exists()

    def test_serving_payload_identity_is_order_independent_and_length_delimited(self) -> None:
        digests = {
            relative: hashlib.sha256(relative.encode("utf-8")).hexdigest()
            for relative in inventory.SERVING_FILES
        }
        reverse_order = dict(reversed(tuple(digests.items())))
        assert payload_projection.serving_payload_sha256(
            digests
        ) == payload_projection.serving_payload_sha256(reverse_order)
        changed = dict(digests)
        changed[inventory.SERVING_FILES[-1]] = "0" * 64
        assert payload_projection.serving_payload_sha256(
            digests
        ) != payload_projection.serving_payload_sha256(changed)
