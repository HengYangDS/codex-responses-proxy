"""Historical payload migration and rollback safety contracts."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path, PurePosixPath

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle import transaction as payload_transaction
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import (
    executable_relative,
    install_context,
    write_retired_projection,
    write_supported_predecessor_projection,
)
from tests.lifecycle.fixtures import begin_transaction, install_payload, released_artifact
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestPayloadMigration:
    """Historical payload migration and rollback safety contracts."""

    def test_only_the_supported_predecessor_is_migratable(self) -> None:
        assert set(payload_projection._SUPPORTED_PREDECESSOR_INVENTORIES) == {
            payload_projection.SUPPORTED_PREDECESSOR_RELEASE
        }

    def _supported_predecessor(self) -> tuple[runtime_context.RuntimeContext, Path]:
        ctx = install_context(Path(tempfile.mkdtemp()))
        write_supported_predecessor_projection(ctx)
        return ctx, Path(ctx.install_dir)

    def test_supported_predecessor_upgrades_and_rolls_back(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        previous = write_supported_predecessor_projection(ctx)
        renamed = {
            install / old: install / current
            for current, old in payload_projection._PREDECESSOR_PATHS.items()
        }
        receipt = install / payload_projection._PREDECESSOR_RECEIPT_FILENAME
        installed_state = install / inventory.INSTALLED_RELEASE_STATE_FILENAME
        previous_receipt = receipt.read_bytes()
        installed_state.unlink()

        transaction = begin_transaction(ctx, released_artifact("2.0.8"), mocker=mocker)
        transaction.commit_projection()

        for old, current in renamed.items():
            assert not old.exists()
            assert current.is_file()
        transaction.rollback()
        for old, current in renamed.items():
            relative = old.relative_to(install).as_posix()
            assert old.read_bytes() == previous[relative]
            assert not current.exists()
        assert receipt.read_bytes() == previous_receipt
        assert not installed_state.exists()

    def test_predecessor_receipt_is_canonical_and_version_bound(self, subtests) -> None:
        cases = (
            ("noncanonical", None, "canonical"),
            ("wrong-version", "9.9.9", "version"),
        )
        for name, version, message in cases:
            with subtests.test(name=name):
                ctx, install = self._supported_predecessor()
                receipt_path = install / payload_projection._PREDECESSOR_RECEIPT_FILENAME
                receipt = json.loads(receipt_path.read_bytes())
                if version is not None:
                    receipt["version"] = version
                    receipt_bytes = payload_digest.canonical_json(receipt)
                else:
                    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
                receipt_path.write_bytes(receipt_bytes)
                manifest_path = install / inventory.MANIFEST_FILENAME
                manifest = json.loads(manifest_path.read_bytes())
                manifest["release_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
                manifest_path.write_bytes(payload_projection.manifest_bytes(manifest))

                with pytest.raises(errors.InstallError, match=message):
                    payload_projection.verify_historical_projection(ctx)

    def test_predecessor_install_state_must_match_when_present(self, subtests) -> None:
        cases = (
            ("wrong-version", {"version": "9.9.9"}),
            ("wrong-receipt", {"receipt_sha256": "0" * 64}),
        )
        for name, changes in cases:
            with subtests.test(name=name):
                ctx, install = self._supported_predecessor()
                state_path = install / inventory.INSTALLED_RELEASE_STATE_FILENAME
                installed = json.loads(state_path.read_bytes())
                installed.update(changes)
                state_path.write_bytes(payload_digest.canonical_json(installed))

                with pytest.raises(errors.InstallError, match="installed release state"):
                    payload_projection.verify_historical_projection(ctx)

    def test_matching_predecessor_install_state_is_owned(self) -> None:
        ctx, _install = self._supported_predecessor()

        historical = payload_projection.verify_historical_projection(ctx)

        assert inventory.INSTALLED_RELEASE_STATE_FILENAME in historical.metadata

    def test_predecessor_serving_and_receipt_identity_are_bound(self, subtests) -> None:
        cases = (
            (
                "serving-digest",
                lambda manifest: manifest["serving_files"].__setitem__("VERSION", "0" * 64),
                "serving identity",
            ),
            (
                "serving-aggregate",
                lambda manifest: manifest.__setitem__("serving_payload_sha256", "0" * 64),
                "serving aggregate",
            ),
            (
                "receipt-digest",
                lambda manifest: manifest.__setitem__("release_receipt_sha256", "0" * 64),
                "receipt digest",
            ),
        )
        for name, mutate, message in cases:
            with subtests.test(name=name):
                ctx, install = self._supported_predecessor()
                manifest_path = install / inventory.MANIFEST_FILENAME
                manifest = json.loads(manifest_path.read_bytes())
                mutate(manifest)
                manifest_path.write_bytes(payload_projection.manifest_bytes(manifest))

                with pytest.raises(errors.InstallError, match=message):
                    payload_projection.verify_historical_projection(ctx)

    def test_unknown_schema_two_inventory_remains_rejected(self) -> None:
        ctx, install = self._supported_predecessor()
        manifest_path = install / inventory.MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"].pop(next(iter(payload_projection._PREDECESSOR_PATHS.values())))
        manifest_path.write_bytes(payload_projection.manifest_bytes(manifest))

        with pytest.raises(errors.InstallError, match="file set is unsupported"):
            payload_projection.verify_historical_projection(ctx)

    def test_retired_security_boundaries(self, subtests, *, mocker) -> None:
        cases = (
            self._assert_current_manifest_is_verified,
            self._assert_pretty_legacy_manifest_is_accepted,
            self._assert_candidate_symlinks_are_rejected,
            self._assert_failed_snapshot_releases_transaction,
        )
        for case in cases:
            with subtests.test(case=case.__name__):
                try:
                    case(mocker=mocker)
                finally:
                    mocker.stopall()
        with subtests.test(case=self._assert_snapshot_paths_are_bounded.__name__):
            self._assert_snapshot_paths_are_bounded()

    def _assert_current_manifest_is_verified(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        unknown = Path(ctx.install_dir, "proxy", "local.py")
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b"local\n")
        manifest_path = Path(payload_projection.payload_manifest_path(ctx))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][executable_relative()] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.InstallError, match="hash mismatch"):
            transaction.commit_projection()
        assert unknown.read_bytes() == b"local\n"
        assert not Path(payload_state.transaction_root(ctx)).exists()

    def _assert_pretty_legacy_manifest_is_accepted(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        assert not (install / "proxy/dmx_responses_proxy.py").exists()

    def _assert_candidate_symlinks_are_rejected(self, *, mocker) -> None:
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
                (install / "bin").symlink_to(external, target_is_directory=True)
            transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
            with pytest.raises(errors.InstallError, match="symlink"):
                transaction.commit_projection()
            assert tuple(external.iterdir()) == ()

    def _assert_failed_snapshot_releases_transaction(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        marker = Path(ctx.install_dir, "proxy", "owned.py")
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"unowned\n")
        first = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.InstallError, match="manifest is required"):
            first.commit_projection()
        assert not Path(payload_state.transaction_root(ctx)).exists()
        marker.unlink()
        marker.parent.rmdir()
        begin_transaction(ctx, released_artifact(), mocker=mocker).rollback()

    def _assert_snapshot_paths_are_bounded(self) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
        rollback.mkdir(parents=True)
        for relative in ("unknown.py", "C:/escape.py", "//server/share.py"):
            snapshot = {
                "schema_version": 2,
                "present": {relative: {"sha256": "0" * 64, "mode": 0o644}},
                "retired": [],
                "retired_owned_sha256": payload_rollback.path_set_sha256(set()),
                "previous_owned": [],
            }
            (rollback / "snapshot.json").write_bytes(payload_digest.canonical_json(snapshot))
            with pytest.raises(errors.InstallError, match="path|inventory"):
                payload_rollback.restore_snapshot(ctx, rollback)

    def test_retired_transaction_resists_races_and_unowned_collisions(
        self, subtests, *, mocker
    ) -> None:
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
            with subtests.test(case=case.__name__):
                try:
                    case(mocker=mocker)
                finally:
                    mocker.stopall()

    def _legacy_transaction(
        self, files: dict[str, bytes], *, version: str = "1.0.27", mocker
    ) -> tuple[runtime_context.RuntimeContext, payload_transaction.PayloadTransaction]:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        retired = write_retired_projection(ctx, version=version, schema=2)
        for relative, content in files.items():
            target = install / relative
            if relative not in retired:
                raise AssertionError(f"not a historical schema-2 path: {relative}")
            target.write_bytes(content)
        manifest = json.loads((install / inventory.MANIFEST_FILENAME).read_text())
        manifest["files"].update(
            {relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()}
        )
        (install / inventory.MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return ctx, begin_transaction(ctx, released_artifact(), mocker=mocker)

    def _assert_rollback_preflights_all_sources(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install_payload(ctx, "1.2.2", mocker=mocker)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        live = Path(ctx.executable)
        before = live.read_bytes()
        Path(
            payload_state.transaction_root(ctx),
            "rollback",
            executable_relative(),
        ).unlink()
        with pytest.raises(errors.InstallError, match="rollback.*unavailable"):
            transaction.rollback()
        assert live.read_bytes() == before

    def _assert_rollback_conflicting_retired_target_fails(self, *, mocker) -> None:
        ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, mocker=mocker
        )
        transaction.commit_projection()
        conflict = Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py")
        conflict.parent.mkdir(parents=True, exist_ok=True)
        conflict.write_bytes(b"new unknown\n")
        with pytest.raises(errors.InstallError, match="conflicts"):
            transaction.rollback()
        assert conflict.read_bytes() == b"new unknown\n"

    def _assert_retired_unlink_revalidates_snapshot_digest(self, *, mocker) -> None:
        ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, mocker=mocker
        )
        original = payload_rollback.write_snapshot

        def mutate_after_snapshot(context, rollback, version):
            snapshot = original(context, rollback, version)
            Path(context.install_dir, "proxy", "dmx_responses_proxy.py").write_bytes(b"changed\n")
            return snapshot

        mocker.patch.object(payload_rollback, "write_snapshot", side_effect=mutate_after_snapshot)

        with pytest.raises(errors.InstallError, match="changed after snapshot"):
            transaction.commit_projection()
        assert Path(ctx.install_dir, "proxy", "dmx_responses_proxy.py").read_bytes() == b"changed\n"

    def _assert_retired_snapshot_binds_owned_manifest(self, *, mocker) -> None:
        ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, mocker=mocker
        )
        transaction.commit_projection()
        rollback = Path(payload_state.transaction_root(ctx), "rollback")
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
        snapshot_path.write_bytes(payload_digest.canonical_json(snapshot))
        with pytest.raises(errors.InstallError, match="owned proof"):
            transaction.rollback()
        assert not Path(ctx.install_dir, "proxy", "user.py").exists()

    def _assert_retired_directory_scan_errors_are_typed(self, *, mocker) -> None:
        ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, mocker=mocker
        )
        original = Path.rglob

        def fail_scan(path: Path, pattern: str):
            if path == Path(ctx.install_dir, "proxy"):
                raise OSError("blocked")
            return original(path, pattern)

        mocker.patch.object(Path, "rglob", autospec=True, side_effect=fail_scan)

        with pytest.raises(errors.InstallError, match="cleanup failed"):
            transaction.commit_projection()

    def _assert_legacy_downgrade_is_refused(self, *, mocker) -> None:
        _ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, version="9.9.9", mocker=mocker
        )
        with pytest.raises(errors.InstallError, match="downgrade"):
            transaction.commit_projection()

    def _assert_candidate_collision_is_refused(self, *, mocker) -> None:
        ctx, transaction = self._legacy_transaction(
            {"proxy/dmx_responses_proxy.py": b"owned\n"}, mocker=mocker
        )
        collision = Path(ctx.executable)
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"unknown\n")
        with pytest.raises(errors.InstallError, match="unowned collision"):
            transaction.commit_projection()
        assert collision.read_bytes() == b"unknown\n"

    def _assert_manifest_only_legacy_collision_is_refused(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        write_retired_projection(ctx, version="1.0.8", schema=1)
        collision = install / executable_relative()
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"unknown\n")
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.InstallError, match="unowned collision"):
            transaction.commit_projection()
        assert collision.read_bytes() == b"unknown\n"

    def test_retired_manifest_files_are_removed_without_touching_unknown_content(
        self, *, mocker
    ) -> None:
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
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()

        retired_roots = {"platform_adapters", "proxy", "tests"}
        for relative in owned:
            if PurePosixPath(relative).parts[0] in retired_roots:
                assert not (install / relative).exists()
        for relative, content in unknown.items():
            assert (install / relative).read_bytes() == content

        transaction.rollback()

        for relative, content in owned.items():
            assert (install / relative).read_bytes() == content
        for relative, content in unknown.items():
            assert (install / relative).read_bytes() == content

    def test_retired_empty_directories_are_pruned_but_unknown_directories_remain(
        self, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        install = Path(ctx.install_dir)
        files = write_retired_projection(ctx, schema=2)
        owned = install / "proxy" / "dmx_responses_proxy.py"

        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()

        assert not (install / "proxy").exists()

        transaction.rollback()
        assert owned.read_bytes() == files["proxy/dmx_responses_proxy.py"]

    def test_retired_projection_requires_a_valid_manifest_before_mutation(
        self, subtests, *, mocker
    ) -> None:
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
            with subtests.test(message=message):
                ctx = install_context(Path(tempfile.mkdtemp()))
                install = Path(ctx.install_dir)
                marker = install / "proxy" / "owned.py"
                marker.parent.mkdir(parents=True)
                marker.write_bytes(b"untouched\n")
                (install / "VERSION").write_bytes(b"1.0.27\n")
                if manifest is not None:
                    (install / inventory.MANIFEST_FILENAME).write_bytes(
                        payload_digest.canonical_json(manifest)
                    )
                transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
                with pytest.raises(errors.InstallError, match=message):
                    transaction.commit_projection()
                assert marker.read_bytes() == b"untouched\n"

    def test_retired_manifest_rejects_noncanonical_paths_and_symlink_boundaries(
        self, subtests, *, mocker
    ) -> None:
        invalid_paths = (
            "/proxy/owned.py",
            "../proxy/owned.py",
            "proxy/../owned.py",
            "proxy//owned.py",
            "proxy\\owned.py",
        )
        for relative in invalid_paths:
            with subtests.test(relative=relative):
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
                (install / inventory.MANIFEST_FILENAME).write_bytes(
                    payload_digest.canonical_json(manifest)
                )
                transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
                with pytest.raises(errors.InstallError, match="path is not canonical"):
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
        manifest_path = install / inventory.MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["proxy/dmx_responses_proxy.py"] = hashlib.sha256(
            b"external\n"
        ).hexdigest()
        manifest_path.write_bytes(payload_digest.canonical_json(manifest))
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.InstallError, match="symlink"):
            transaction.commit_projection()
        assert external_file.read_bytes() == b"external\n"

    def test_privacy_cleanup_failure_refuses_before_transaction_or_live_payload_write(
        self, *, mocker
    ) -> None:
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

        mocker.patch.object(Path, "unlink", autospec=True, side_effect=fail_capture_unlink)

        with pytest.raises(errors.InstallError, match="capture cleanup failed"):
            begin_transaction(ctx, released_artifact(), mocker=mocker)

        assert marker.read_bytes() == b"existing live payload\n"
        assert capture.is_file()
        assert not Path(payload_state.transaction_root(ctx)).exists()
        mocker.patch.object(Path, "iterdir", autospec=True, side_effect=OSError("blocked"))

        with pytest.raises(errors.InstallError, match="residue inventory failed"):
            begin_transaction(ctx, released_artifact(), mocker=mocker)

    def test_residue_inventory_and_retired_directory_types_fail_closed(
        self, subtests, *, mocker
    ) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        Path(ctx.log_dir).mkdir(parents=True)
        mocker.patch.object(Path, "iterdir", side_effect=OSError("denied"))
        with (
            subtests.test("capture inventory"),
            pytest.raises(errors.InstallError, match="residue inventory failed"),
        ):
            payload_transaction.migration.remove_legacy_captures(ctx)
        mocker.stopall()

        install = Path(ctx.install_dir)
        retired = install / next(
            iter(payload_transaction.migration.owned_files.RETIRED_INSTALL_DIRECTORIES)
        )
        retired.parent.mkdir(parents=True, exist_ok=True)
        retired.write_text("not a directory", encoding="utf-8")
        with (
            subtests.test("retired directory type"),
            pytest.raises(errors.InstallError, match="is not a directory"),
        ):
            payload_transaction.migration._remove_empty_retired_directories(install)
