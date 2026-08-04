"""Committed and loaded service-payload identity contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import install_context, install_payload


class TestServiceIdentity:
    """Bind live service identity to one verified installed projection."""

    def test_committed_identity_rejects_runtime_and_manifest_drift(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.3", mocker=mocker)

        committed = identity.committed_payload(Path(ctx.executable))

        assert committed is not None
        assert committed.release == "1.2.3"
        assert (
            committed.handoff()["manifest_sha256"]
            == hashlib.sha256(
                Path(ctx.install_dir, inventory.MANIFEST_FILENAME).read_bytes()
            ).hexdigest()
        )

        executable = Path(ctx.executable)
        original = executable.read_bytes()
        executable.write_bytes(original + b"tampered")
        assert identity.committed_payload(executable) is None

        executable.write_bytes(original)
        manifest_path = Path(ctx.install_dir, inventory.MANIFEST_FILENAME)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value.__setitem__("schema_version", 1),
            lambda value: value.__setitem__("files", []),
            lambda value: value["files"].pop(inventory.EXECUTABLE),
            lambda value: value["serving_files"].pop(inventory.PROVIDER_MANIFEST),
            lambda value: value["files"].__setitem__(inventory.EXECUTABLE, "0" * 64),
            lambda value: value["serving_files"].__setitem__(inventory.PROVIDER_MANIFEST, "0" * 64),
            lambda value: value.__setitem__("release_receipt_sha256", "invalid"),
        )
        for mutate in mutations:
            with subtests.test(mutate=mutate):
                broken = json.loads(json.dumps(manifest))
                mutate(broken)
                manifest_path.write_text(json.dumps(broken), encoding="utf-8")
                assert identity.committed_payload(executable) is None
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert (
            identity.committed_payload(Path(ctx.install_dir, inventory.PROVIDER_MANIFEST)) is None
        )

    def test_loaded_identity_is_immutable_after_disk_drift(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, mocker=mocker)
        loaded = identity.freeze_loaded_payload(Path(ctx.executable))
        assert loaded is not None

        Path(ctx.executable).write_bytes(b"tampered-after-freeze")
        manifest = json.loads(Path(projection.payload_manifest_path(ctx)).read_text())

        assert loaded.release == "1.2.3"
        assert loaded.serving_payload_sha256 == manifest["serving_payload_sha256"]
        assert loaded.release_receipt_sha256 == manifest["release_receipt_sha256"]
