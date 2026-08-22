"""Contracts for installed status and protocol-v2 reload."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import install
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle import uninstall
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import digest as payload_digest
from codex_responses_proxy.service import identity
from tests.lifecycle.fixtures import begin_transaction
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import released_artifact

ROOT = Path(__file__).resolve().parents[2]


class TestControllerLifecycle:
    def test_control_reads_bounded_runtime_and_recovers_finalized_reload(self, subtests, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        Path(ctx.install_dir).mkdir(parents=True)

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"pid": 7}'

        build = mocker.patch.object(control.urllib.request, "build_opener")
        build.return_value.open.return_value = Response()
        assert control.read_runtime(ctx) == {"pid": 7}
        build = mocker.patch.object(control.urllib.request, "build_opener")
        build.return_value.open.side_effect = OSError("offline")
        assert control.read_runtime(ctx) is None
        build = mocker.patch.object(control.urllib.request, "build_opener")
        build.return_value.open.return_value = Response()
        build.return_value.open.return_value.status = 503
        assert control.read_runtime(ctx) is None

        runtime = {"pid": 7}
        expected = {"transaction_id": "tx"}
        mocker.patch.object(control, "read_runtime", return_value=runtime)
        mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            control.projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(control.handoff, "expected_metadata", return_value=expected)
        mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
        mocker.patch.object(
            control.handoff,
            "resolve_after_controller_failure",
            return_value=("finalized", {"pid": 8}),
        )
        assert control.reload(ctx) == {
            "state": "reloaded",
            "old_pid": 7,
            "new_pid": 8,
            "transaction_id": "tx",
            "recovered_after_controller_failure": True,
        }
        mocker.patch.object(control, "read_runtime", return_value=runtime)
        mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            control.projection,
            "verify_payload_manifest",
            return_value=(False, "tampered"),
        )

        with pytest.raises(errors.InstallError, match="tampered"):
            control.reload(ctx)

        for resolution, expected_error in (
            ("unknown", errors.InstallError),
            ("rolled_back", OSError),
        ):
            mocker.patch.object(control, "read_runtime", return_value=runtime)
            mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
            mocker.patch.object(
                control.projection,
                "verify_payload_manifest",
                return_value=(True, "ok"),
            )
            mocker.patch.object(control.handoff, "expected_metadata", return_value=expected)
            mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
            mocker.patch.object(
                control.handoff,
                "resolve_after_controller_failure",
                return_value=(resolution, None),
            )
            with subtests.test(resolution=resolution), pytest.raises(expected_error):
                control.reload(ctx)

    def test_status_and_reload_bound_unobservable_failures(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        Path(ctx.install_dir).mkdir(parents=True)
        current_error = errors.InstallError("current manifest invalid")
        mocker.patch.object(
            control.projection, "verify_payload_manifest", side_effect=current_error
        )
        mocker.patch.object(
            control,
            "adapter",
            side_effect=errors.InstallError("service unavailable"),
        )
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        evidence = control.status(ctx)
        assert evidence["payload_integrity"] == {
            "ok": False,
            "detail": str(current_error),
        }
        assert evidence["service"] == "unknown"

        mocker.patch.object(
            control,
            "adapter",
            side_effect=errors.ProductAssemblyError("product assembly incomplete"),
        )
        with pytest.raises(errors.ProductAssemblyError, match="product assembly incomplete"):
            control.status(ctx)

        mocker.patch.object(control, "read_runtime", return_value={"pid": 7})
        mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            control.projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(
            control.handoff, "expected_metadata", return_value={"transaction_id": "tx"}
        )
        mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
        mocker.patch.object(
            control.handoff,
            "resolve_after_controller_failure",
            side_effect=RuntimeError("resolution unavailable"),
        )
        with pytest.raises(errors.InstallError, match="outcome is unconfirmed"):
            control.reload(ctx)

    def test_status_distinguishes_invalid_evidence_from_runtime_degradation(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        Path(ctx.install_dir).mkdir(parents=True)
        mocker.patch.object(control, "adapter").return_value.status.return_value = "absent"
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(control, "read_runtime", return_value=None)
        mocker.patch.object(
            control.command,
            "status",
            return_value={"path": ctx.command, "state": "absent", "kind": None},
        )
        mocker.patch.object(
            control.projection,
            "verify_payload_manifest",
            return_value=(False, "installed payload manifest is unavailable"),
        )

        degraded = control.status(ctx)

        assert degraded["state"] == "degraded"
        assert degraded["detail"] == "installed payload manifest is unavailable"

        transaction_root = Path(payload_state.transaction_root(ctx))
        transaction_root.mkdir()

        invalid = control.status(ctx)

        assert invalid["state"] == "invalid"
        assert invalid["detail"] == "payload transaction journal is missing"

    def test_status_reports_an_invalid_installed_state_without_losing_read_only_evidence(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        install_root = Path(ctx.install_dir)
        install_root.mkdir(parents=True)
        Path(payload_state.installed_path(ctx)).write_text("not-json", encoding="utf-8")
        mocker.patch.object(control, "adapter").return_value.status.return_value = "absent"
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(control, "read_runtime", return_value=None)
        mocker.patch.object(
            control.command,
            "status",
            return_value={"path": ctx.command, "state": "absent", "kind": None},
        )
        mocker.patch.object(
            control.projection,
            "verify_payload_manifest",
            return_value=(False, "installed payload manifest is unavailable"),
        )

        result = control.status(ctx)

        assert result["state"] == "invalid"
        assert result["release"] is None
        assert result["detail"] == "installed release state is unavailable or invalid"

    def test_process_teardown_fails_closed_when_exit_is_unproved(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(
            uninstall.process,
            "verified_proxy_listener_pids",
            side_effect=[[7], []],
        )
        mocker.patch.object(uninstall.process, "terminate_executable", return_value=False)

        with pytest.raises(errors.InstallError, match="did not exit"):
            uninstall._stop_proxy(ctx)
        mocker.patch.object(
            uninstall.process,
            "verified_proxy_listener_pids",
            side_effect=[[], [8]],
        )
        with pytest.raises(errors.InstallError, match="listeners remain"):
            uninstall._stop_proxy(ctx)

        mocker.patch.object(
            uninstall.process,
            "verified_proxy_listener_pids",
            side_effect=[[7, 8], []],
        )
        mocker.patch.object(uninstall.process, "terminate_executable", return_value=True)
        assert uninstall._stop_proxy(ctx) == 2

    def test_uninstall_product_covers_success_and_fail_closed_boundaries(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        Path(ctx.install_dir).mkdir(parents=True)
        service = mocker.Mock()
        service.status.return_value = "absent"
        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(uninstall.projection, "purge_installed_projection", return_value=[])
        remove_command = mocker.patch.object(uninstall.command, "remove", return_value=True)
        assert uninstall.uninstall_product(purge=True) == {
            "state": "purged",
            "stopped": 0,
            "command_removed": True,
        }
        remove_command.assert_called_once_with(Path(ctx.command), Path(ctx.executable))
        service.uninstall.assert_called_once_with(ctx)

        service.status.return_value = "loaded"
        with pytest.raises(errors.InstallError, match="remains loaded"):
            uninstall._remove_service(service, ctx)

        service.status.return_value = "absent"
        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        assert uninstall.uninstall_product() == {
            "state": "uninstalled",
            "stopped": 0,
            "command_removed": True,
        }
        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(
            uninstall.projection,
            "purge_installed_projection",
            return_value=["unknown.txt"],
        )

        with pytest.raises(errors.InstallError, match="unknown install content remains"):
            uninstall.uninstall_product(purge=True)

    def test_uninstall_is_idempotent_when_no_installation_exists(self, tmp_path, *, mocker):
        ctx = install_context(tmp_path)
        service = mocker.Mock()
        service.status.return_value = "absent"
        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])

        assert uninstall.uninstall_product(purge=True) == {
            "state": "not_installed",
            "stopped": 0,
            "command_removed": False,
        }
        assert not Path(ctx.install_dir).exists()

    def test_uninstall_refuses_any_retained_transaction_before_mutation(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        service = mocker.Mock()
        service.status.return_value = "absent"
        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])

        root = Path(payload_state.transaction_root(ctx))
        root.mkdir(parents=True)
        with pytest.raises(errors.RecoveryStateError, match="invalid"):
            uninstall.uninstall_product(purge=True)
        service.uninstall.assert_not_called()

        root.rmdir()
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        with pytest.raises(errors.RecoveryRequiredError, match="recovery"):
            uninstall.uninstall_product(purge=True)
        service.uninstall.assert_not_called()
        transaction.rollback()

    def test_status_and_uninstall_use_the_finalized_command_path(self, tmp_path: Path, *, mocker):
        ctx = install_context(tmp_path)
        installed_command = tmp_path / "original-bin" / "codex-responses-proxy"
        changed_environment_command = tmp_path / "changed-bin" / "codex-responses-proxy"
        ctx = replace(ctx, command=str(changed_environment_command))
        installed_state = {
            "schema_version": payload_state.INSTALLED_RELEASE_STATE_SCHEMA,
            "version": "2.0.37",
            "command": str(installed_command),
        }
        mocker.patch.object(payload_state, "read_installed", return_value=installed_state)
        command_status = mocker.patch.object(
            control.command,
            "status",
            return_value={
                "path": str(installed_command),
                "state": "owned",
                "kind": "symlink",
            },
        )
        mocker.patch.object(
            control.projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(control, "adapter").return_value.status.return_value = "running"
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(control, "read_runtime", return_value=None)

        command_evidence = control.status(ctx)["command"]
        assert isinstance(command_evidence, dict)
        assert command_evidence["path"] == str(installed_command)
        command_status.assert_called_once_with(installed_command, Path(ctx.executable))

        mocker.patch.object(uninstall.runtime_context, "create", return_value=ctx)
        service = mocker.patch.object(uninstall, "adapter").return_value
        service.status.return_value = "absent"
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        remove = mocker.patch.object(uninstall.command, "remove", return_value=True)

        uninstall.uninstall_product()

        remove.assert_called_once_with(installed_command, Path(ctx.executable))

    def test_install_and_uninstall_adapters_preserve_bounded_errors(self, *, mocker) -> None:
        ctx = install_context(Path(tempfile.mkdtemp()))
        released = mocker.Mock()
        payload_transaction = mocker.Mock()
        service = mocker.Mock()
        mocker.patch.object(install, "build_context", return_value=ctx)
        admit = mocker.patch.object(install.artifact, "admit", return_value=released)
        begin = mocker.patch.object(
            install.transaction, "begin_transaction", return_value=payload_transaction
        )
        mocker.patch(
            "codex_responses_proxy.lifecycle.supervision.native_service.adapter",
            return_value=service,
        )
        applied = mocker.patch.object(install.apply, "install", return_value={"release": "2.0.15"})
        asset = Path(ctx.install_dir) / "release.tar.gz"
        trust = Path(ctx.install_dir) / "release-trust"

        assert install.install_asset(asset, trust_anchor=trust, port=8801, timeout_seconds=4) == {
            "release": "2.0.15"
        }
        admit.assert_called_once_with(asset, trust_anchor=trust)
        begin.assert_called_once_with(ctx, released)
        applied.assert_called_once_with(
            ctx,
            payload_transaction,
            adapter=service,
            runtime_reader=control.read_runtime,
            timeout_seconds=4,
        )

        mocker.patch.object(
            uninstall.runtime_context,
            "create",
            side_effect=errors.UnsupportedPlatformError("no host"),
        )
        with pytest.raises(errors.UnsupportedPlatformError, match="no host"):
            uninstall.uninstall_product()

    def test_control_status_includes_secret_free_runtime_when_listener_is_available(
        self, *, mocker
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
            committed = identity.committed_payload(Path(ctx.executable))
            assert committed is not None
            runtime = {
                "pid": 1,
                **committed.handoff(),
                "payload_manifest_sha256": committed.manifest_sha256,
                "uptime_seconds": 12,
                "active_responses": 0,
                "counters": {},
                "upstream_classifications": {},
                "last_failure": None,
                "handoff_protocol_version": 2,
                "handoff_state": "idle",
                "handoff_transaction_id": None,
                "accepting": True,
                "draining": False,
            }
            mocker.patch.object(control, "read_runtime", return_value=runtime)
            mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[1])
            evidence = control.status(ctx)
            assert evidence["runtime"] == runtime
            assert "authorization" not in json.dumps(evidence).lower()

    def test_status_rejects_a_listener_serving_a_different_payload(
        self, tmp_path: Path, *, mocker
    ) -> None:
        ctx = install_context(tmp_path)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        transaction.finalize({"pid": 1})
        foreign = {
            "pid": 1,
            "release": "9.9.9",
            "serving_payload_sha256": "1" * 64,
            "release_receipt_sha256": "2" * 64,
            "payload_manifest_sha256": "3" * 64,
            "handoff_protocol_version": 2,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "accepting": True,
            "draining": False,
        }
        mocker.patch.object(control, "read_runtime", return_value=foreign)
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[1])
        mocker.patch.object(control, "adapter").return_value.status.return_value = "running"

        evidence = control.status(ctx)

        assert evidence["state"] == "degraded"
        assert evidence["detail"] == "listener runtime identity is unavailable"
        assert evidence["runtime"] is None

    def test_status_rejects_a_non_accepting_or_draining_runtime(
        self, tmp_path: Path, *, mocker, subtests
    ) -> None:
        ctx = install_context(tmp_path)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        transaction.finalize({"pid": 1})
        committed = identity.committed_payload(Path(ctx.executable))
        assert committed is not None
        healthy = {
            "pid": 1,
            **committed.handoff(),
            "payload_manifest_sha256": committed.manifest_sha256,
            "handoff_protocol_version": 2,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "accepting": True,
            "draining": False,
        }
        runtime = mocker.patch.object(control, "read_runtime")
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[1])
        mocker.patch.object(control, "adapter").return_value.status.return_value = "running"

        for overrides in ({"accepting": False}, {"draining": True}):
            with subtests.test(overrides=overrides):
                runtime.return_value = {**healthy, **overrides}
                evidence = control.status(ctx)
                assert evidence["state"] == "degraded"
                assert evidence["detail"] == "listener runtime identity is unavailable"
                assert evidence["runtime"] is None

    def test_status_rejects_runtime_from_an_unowned_listener(self, tmp_path: Path, *, mocker):
        ctx = install_context(tmp_path)
        transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
        transaction.commit_projection()
        transaction.finalize({"pid": 1})
        foreign = {
            "pid": 76541,
            "release": "foreign",
            "serving_payload_sha256": "1" * 64,
            "release_receipt_sha256": "2" * 64,
            "payload_manifest_sha256": "3" * 64,
            "accepting": True,
        }
        mocker.patch.object(control, "read_runtime", return_value=foreign)
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])

        evidence = control.status(ctx)

        assert evidence["listener_pids"] == []
        assert evidence["runtime"] is None

    def test_control_status_json_reports_recovery_without_private_transaction_data(self, *, mocker):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            initial = begin_transaction(ctx, released_artifact("1.2.2"), mocker=mocker)
            initial.commit_projection()
            initial.finalize({"pid": 1})
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
            mocker.patch.object(application.runtime_context, "create", return_value=ctx)
            mocker.patch.object(application.control, "read_runtime", return_value=None)
            adapter = mocker.patch.object(application.control, "adapter")
            adapter.return_value.status.return_value = "running"
            evidence = application.dispatch("status", port=ctx.port)
            transaction_evidence = evidence["payload_transaction"]
            assert isinstance(transaction_evidence, dict)
            assert transaction_evidence["state"] == "recovery_required"
            assert "reason" not in transaction_evidence
            rendered = json.dumps(evidence)
            for forbidden in (
                "secret-token",
                "private request",
                "/private/release-stage",
            ):
                assert forbidden not in rendered
            assert journal_path.read_bytes() == before

    def test_reload_refuses_incompatible_listener_without_mutation(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        Path(ctx.install_dir).mkdir(parents=True)
        mocker.patch.object(control, "read_runtime", return_value={"pid": 12345})
        terminate = mocker.patch.object(process, "terminate_pid")
        with pytest.raises(errors.InstallError, match="not healthy enough to reload"):
            control.reload(ctx)
        terminate.assert_not_called()
