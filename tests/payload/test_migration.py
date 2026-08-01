#!/usr/bin/env python3
"""Historical payload migration and rollback safety contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path, PurePosixPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.payload import projection as payload_projection
from codex_responses_proxy.payload import rollback as payload_rollback
from codex_responses_proxy.payload import transaction as payload_transaction
from codex_responses_proxy.runtime import context as runtime_context
from tests.deployment.fixtures import install_context, write_retired_projection
from tests.payload.fixtures import begin_transaction, install_payload, released_fixture


class TestPayloadMigration(unittest.TestCase):
    """Historical payload migration and rollback safety contracts."""

    def test_retired_security_boundaries(self) -> None:
        cases = (
            self._assert_current_manifest_is_verified,
            self._assert_pretty_legacy_manifest_is_accepted,
            self._assert_candidate_symlinks_are_rejected,
            self._assert_failed_snapshot_releases_transaction,
            self._assert_snapshot_paths_are_bounded,
        )
        for case in cases:
            with self.subTest(case=case.__name__):
                case()

    def _assert_current_manifest_is_verified(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2")
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local\n")
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["VERSION"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "hash mismatch"):
            transaction.commit_projection()
        self.assertEqual(unknown.read_bytes(), b"local\n")
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

    def _assert_pretty_legacy_manifest_is_accepted(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()
        self.assertFalse((install / "proxy/dmx_responses_proxy.py").exists())

    def _assert_candidate_symlinks_are_rejected(self) -> None:
        for boundary in ("install", "ancestor"):
            root = Path(tempfile.mkdtemp())
            ctx = install_context(root)
            external = root / "external"
            external.mkdir()
            install = Path(ctx.install_dir)
            if boundary == "install":
                install.parent.mkdir(parents=True)
                install.symlink_to(external, target_is_directory=True)
            else:
                install.mkdir(parents=True)
                (install / "codex_responses_proxy").symlink_to(external, target_is_directory=True)
            transaction = begin_transaction(ctx, released_fixture())
            with self.assertRaisesRegex(errors.InstallError, "symlink"):
                transaction.commit_projection()
            self.assertEqual(tuple(external.iterdir()), ())

    def _assert_failed_snapshot_releases_transaction(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        marker = Path(ctx.install_dir, "proxy", "owned.py")
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"unowned\n")
        first = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "manifest is required"):
            first.commit_projection()
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())
        marker.unlink()
        marker.parent.rmdir()
        begin_transaction(ctx, released_fixture()).rollback()

    def _assert_snapshot_paths_are_bounded(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        rollback.mkdir(parents=True)
        for relative in ("unknown.py", "C:/escape.py", "//server/share.py"):
            snapshot = {
                "schema_version": 2,
                "present": {relative: {"sha256": "0" * 64, "mode": 0o644}},
                "retired": [],
                "retired_owned_sha256": payload_rollback.path_set_sha256(set()),
                "previous_owned": [],
            }
            (rollback / "snapshot.json").write_bytes(
                payload_transaction.digest.canonical_json(snapshot)
            )
            with self.assertRaisesRegex(errors.InstallError, "path|inventory"):
                payload_rollback.restore_snapshot(ctx, rollback)

    def test_retired_transaction_resists_races_and_unowned_collisions(self) -> None:
        cases = (
            self._assert_rollback_preflights_all_sources,
            self._assert_rollback_conflicting_retired_target_fails,
            self._assert_retired_unlink_revalidates_snapshot_digest,
            self._assert_retired_snapshot_binds_owned_manifest,
            self._assert_retired_directory_scan_errors_are_typed,
            self._assert_legacy_downgrade_is_refused,
            self._assert_candidate_collision_is_refused,
            self._assert_manifest_only_legacy_collision_is_refused,
        )
        for case in cases:
            with self.subTest(case=case.__name__):
                case()

    def _legacy_transaction(
        self, files: dict[str, bytes], *, version: str = "1.0.27"
    ) -> tuple[runtime_context.RuntimeContext, payload_transaction.PayloadTransaction]:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        retired = write_retired_projection(ctx, version=version, schema=2)
        for relative, content in files.items():
            target = install / relative
            if relative not in retired:
                raise AssertionError(f"not a historical schema-2 path: {relative}")
            target.write_bytes(content)
        manifest = json.loads((install / payload_projection.PAYLOAD_MANIFEST_FILENAME).read_text())
        manifest["files"].update(
            {relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()}
        )
        (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return ctx, begin_transaction(ctx, released_fixture())

    def _assert_rollback_preflights_all_sources(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2")
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()
        live = Path(ctx.install_dir, "codex_responses_proxy/commands/control.py")
        before = live.read_bytes()
        Path(payload_transaction.payload_transaction_dir(ctx), "rollback", "VERSION").unlink()
        with self.assertRaisesRegex(errors.InstallError, "rollback.*unavailable"):
            transaction.rollback()
        self.assertEqual(live.read_bytes(), before)

    def _assert_rollback_conflicting_retired_target_fails(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        transaction.commit_projection()
        conflict = Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py")
        conflict.parent.mkdir(parents=True, exist_ok=True)
        conflict.write_bytes(b"new unknown\n")
        with self.assertRaisesRegex(errors.InstallError, "conflicts"):
            transaction.rollback()
        self.assertEqual(conflict.read_bytes(), b"new unknown\n")

    def _assert_retired_unlink_revalidates_snapshot_digest(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        original = payload_rollback.write_snapshot

        def mutate_after_snapshot(context, rollback, version):
            snapshot = original(context, rollback, version)
            Path(context.install_dir, "proxy", "dmx_responses_proxy.py").write_bytes(b"changed\n")
            return snapshot

        with (
            mock.patch.object(
                payload_rollback, "write_snapshot", side_effect=mutate_after_snapshot
            ),
            self.assertRaisesRegex(errors.InstallError, "changed after snapshot"),
        ):
            transaction.commit_projection()
        self.assertEqual(
            Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py").read_bytes(), b"changed\n"
        )

    def _assert_retired_snapshot_binds_owned_manifest(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        transaction.commit_projection()
        rollback = Path(payload_transaction.payload_transaction_dir(ctx), "rollback")
        injected = rollback / "proxy" / "user.py"
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.write_bytes(b"injected\n")
        snapshot_path = rollback / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["present"]["proxy/user.py"] = {
            "sha256": hashlib.sha256(b"injected\n").hexdigest(),
            "mode": 0o644,
        }
        snapshot["retired"].append("proxy/user.py")
        snapshot_path.write_bytes(payload_transaction.digest.canonical_json(snapshot))
        with self.assertRaisesRegex(errors.InstallError, "owned proof"):
            transaction.rollback()
        self.assertFalse(Path(ctx.install_dir, "proxy", "user.py").exists())

    def _assert_retired_directory_scan_errors_are_typed(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        original = Path.rglob

        def fail_scan(path: Path, pattern: str):
            if path == Path(ctx.install_dir, "proxy"):
                raise OSError("blocked")
            return original(path, pattern)

        with (
            mock.patch.object(Path, "rglob", autospec=True, side_effect=fail_scan),
            self.assertRaisesRegex(errors.InstallError, "cleanup failed"),
        ):
            transaction.commit_projection()

    def _assert_legacy_downgrade_is_refused(self) -> None:
        _ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, version="9.9.9"
        )
        with self.assertRaisesRegex(errors.InstallError, "downgrade"):
            transaction.commit_projection()

    def _assert_candidate_collision_is_refused(self) -> None:
        ctx, transaction = self._legacy_transaction({"proxy/dmx_responses_proxy.py": b"owned\n"})
        collision = Path(ctx.install_dir, "codex_responses_proxy", "errors.py")
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"unknown\n")
        with self.assertRaisesRegex(errors.InstallError, "unowned collision"):
            transaction.commit_projection()
        self.assertEqual(collision.read_bytes(), b"unknown\n")

    def _assert_manifest_only_legacy_collision_is_refused(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        collision = install / "codex_responses_proxy" / "errors.py"
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"unknown\n")
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "unowned collision"):
            transaction.commit_projection()
        self.assertEqual(collision.read_bytes(), b"unknown\n")

    def test_retired_manifest_files_are_removed_without_touching_unknown_content(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        owned = write_retired_projection(ctx, schema=2)
        unknown = {
            "proxy/local.py": b"user proxy\n",
            "tests/fixtures/data.txt": b"user fixture\n",
        }
        for relative, content in unknown.items():
            target = install / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        retired_roots = {"platform_adapters", "proxy", "tests"}
        for relative in owned:
            if PurePosixPath(relative).parts[0] in retired_roots:
                self.assertFalse((install / relative).exists())
        for relative, content in unknown.items():
            self.assertEqual((install / relative).read_bytes(), content)

        transaction.rollback()

        for relative, content in owned.items():
            self.assertEqual((install / relative).read_bytes(), content)
        for relative, content in unknown.items():
            self.assertEqual((install / relative).read_bytes(), content)

    def test_retired_empty_directories_are_pruned_but_unknown_directories_remain(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        files = write_retired_projection(ctx, schema=2)
        owned = install / "proxy" / "dmx_responses_proxy.py"

        transaction = begin_transaction(ctx, released_fixture())
        transaction.commit_projection()

        self.assertFalse((install / "proxy").exists())

        transaction.rollback()
        self.assertEqual(owned.read_bytes(), files["proxy/dmx_responses_proxy.py"])

    def test_retired_projection_requires_a_valid_manifest_before_mutation(self) -> None:
        cases = (
            (None, "manifest is required"),
            ({"schema_version": 99, "release": "1.0.27", "files": {}}, "unsupported"),
            (
                {
                    "schema_version": 1,
                    "release": "1.0.27",
                    "files": {"VERSION": "0" * 64},
                },
                "file set is unsupported",
            ),
        )
        for manifest, message in cases:
            with self.subTest(message=message):
                ctx = install_context(Path(tempfile.mkdtemp()))
                install = Path(ctx.install_dir)
                marker = install / "proxy" / "owned.py"
                marker.parent.mkdir(parents=True)
                marker.write_bytes(b"untouched\n")
                (install / "VERSION").write_bytes(b"1.0.27\n")
                if manifest is not None:
                    (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_bytes(
                        payload_transaction.digest.canonical_json(manifest)
                    )
                transaction = begin_transaction(ctx, released_fixture())
                with self.assertRaisesRegex(errors.InstallError, message):
                    transaction.commit_projection()
                self.assertEqual(marker.read_bytes(), b"untouched\n")

    def test_retired_manifest_rejects_noncanonical_paths_and_symlink_boundaries(self) -> None:
        invalid_paths = (
            "/proxy/owned.py",
            "../proxy/owned.py",
            "proxy/../owned.py",
            "proxy//owned.py",
            "proxy\\owned.py",
        )
        for relative in invalid_paths:
            with self.subTest(relative=relative):
                ctx = install_context(Path(tempfile.mkdtemp()))
                install = Path(ctx.install_dir)
                install.mkdir(parents=True)
                version = b"1.0.27\n"
                (install / "VERSION").write_bytes(version)
                manifest = {
                    "schema_version": 1,
                    "release": "1.0.27",
                    "files": {
                        "VERSION": hashlib.sha256(version).hexdigest(),
                        relative: hashlib.sha256(b"owned\n").hexdigest(),
                    },
                }
                (install / payload_projection.PAYLOAD_MANIFEST_FILENAME).write_bytes(
                    payload_transaction.digest.canonical_json(manifest)
                )
                transaction = begin_transaction(ctx, released_fixture())
                with self.assertRaisesRegex(errors.InstallError, "path is not canonical"):
                    transaction.commit_projection()

        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        external = install.parent / "external"
        external.mkdir(parents=True)
        external_file = external / "dmx_responses_proxy.py"
        external_file.write_bytes(b"external\n")
        write_retired_projection(ctx, schema=2)
        for path in (install / "proxy").iterdir():
            path.unlink()
        (install / "proxy").rmdir()
        (install / "proxy").symlink_to(external, target_is_directory=True)
        manifest_path = install / payload_projection.PAYLOAD_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["proxy/dmx_responses_proxy.py"] = hashlib.sha256(
            b"external\n"
        ).hexdigest()
        manifest_path.write_bytes(payload_transaction.digest.canonical_json(manifest))
        transaction = begin_transaction(ctx, released_fixture())
        with self.assertRaisesRegex(errors.InstallError, "symlink"):
            transaction.commit_projection()
        self.assertEqual(external_file.read_bytes(), b"external\n")

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
            self.assertRaisesRegex(errors.InstallError, "capture cleanup failed"),
        ):
            begin_transaction(ctx, released_fixture())

        self.assertEqual(marker.read_bytes(), b"existing live payload\n")
        self.assertTrue(capture.is_file())
        self.assertFalse(Path(payload_transaction.payload_transaction_dir(ctx)).exists())

        with (
            mock.patch.object(Path, "iterdir", autospec=True, side_effect=OSError("blocked")),
            self.assertRaisesRegex(errors.InstallError, "residue inventory failed"),
        ):
            begin_transaction(ctx, released_fixture())


if __name__ == "__main__":
    unittest.main(verbosity=2)
