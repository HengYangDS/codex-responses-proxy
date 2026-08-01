#!/usr/bin/env python3
"""Installed payload identity, manifest, and purge behavior contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy.payload import identity as listener_identity  # noqa: E402
from codex_responses_proxy.payload import projection as payload_projection  # noqa: E402
from codex_responses_proxy.payload import transaction as payload_transaction  # noqa: E402
from codex_responses_proxy import errors  # noqa: E402
from tests.deployment.fixtures import install_context  # noqa: E402
from tests.payload.fixtures import install_payload, released_fixture  # noqa: E402


class TestPayloadIdentity(unittest.TestCase):
    """Manifest and startup-frozen aggregate contracts over opaque payload bytes."""

    def test_transaction_installs_complete_runtime_and_manifest(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx)
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
        self.assertTrue(
            Path(ctx.install_dir, "codex_responses_proxy/commands/control.py").is_file()
        )

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
        install_payload(ctx)
        proxy = Path(ctx.proxy_script)
        proxy.write_bytes(proxy.read_bytes() + b"# tampered\n")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertIn("hash mismatch", detail)

        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx)
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["serving_payload_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        ok, detail = payload_projection.verify_payload_manifest(ctx)
        self.assertFalse(ok)
        self.assertEqual(detail, "serving payload aggregate mismatch")

    def test_committed_successor_identity_is_independent_of_the_old_loaded_release(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.3")

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
            lambda value: value["files"].pop("codex_responses_proxy/commands/control.py"),
            lambda value: value["serving_files"].pop("VERSION"),
            lambda value: value["files"].__setitem__(
                "codex_responses_proxy/commands/control.py", "0" * 64
            ),
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
        self.assertIsNone(
            listener_identity.committed_payload(
                Path(ctx.install_dir, "codex_responses_proxy/commands/control.py")
            )
        )

    def test_purge_unlinks_only_manifest_owned_payload_and_preserves_unknown_content(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx)
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
        install_payload(ctx)
        script = """
import json
from pathlib import Path
from codex_responses_proxy.listener import entrypoint
root = Path.cwd()
(root / "VERSION").write_text("9.9.9\\n", encoding="utf-8")
(root / "codex_responses_proxy" / "listener" / "state.py").write_text("tampered = True\\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
