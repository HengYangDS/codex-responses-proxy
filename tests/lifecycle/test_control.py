"""Contracts for installed status and protocol-v2 reload."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application
from codex_responses_proxy.lifecycle import control, install, uninstall
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import digest as payload_digest
from tests.lifecycle.fixtures import install_context
from tests.lifecycle.fixtures import begin_transaction, released_artifact
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestControllerLifecycle:
    def test_control_reads_bounded_runtime_and_recovers_finalized_reload(self, subtests, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))

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
        assert control._runtime_metrics(ctx) == {"pid": 7}
        build = mocker.patch.object(control.urllib.request, "build_opener")
        build.return_value.open.side_effect = OSError("offline")
        assert control._runtime_metrics(ctx) is None
        build = mocker.patch.object(control.urllib.request, "build_opener")
        build.return_value.open.return_value = Response()
        build.return_value.open.return_value.status = 503
        assert control._runtime_metrics(ctx) is None

        runtime = {"pid": 7}
        expected = {"transaction_id": "tx"}
        mocker.patch.object(control, "_runtime_metrics", return_value=runtime)
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
            "old_pid": 7,
            "new_pid": 8,
            "transaction_id": "tx",
            "recovered_after_controller_failure": True,
        }
        mocker.patch.object(control, "_runtime_metrics", return_value=runtime)
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
            mocker.patch.object(control, "_runtime_metrics", return_value=runtime)
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
        assert evidence["payload_integrity"] == {"ok": False, "detail": str(current_error)}
        assert evidence["service"] == "unknown"

        mocker.patch.object(
            control,
            "adapter",
            side_effect=errors.ProductAssemblyError("product assembly incomplete"),
        )
        with pytest.raises(errors.ProductAssemblyError, match="product assembly incomplete"):
            control.status(ctx)

        mocker.patch.object(control, "_runtime_metrics", return_value={"pid": 7})
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

    def test_lifecycle_helpers_cover_local_files_and_process_failures(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        assert uninstall._context(8801).port == 8801
        installed_state = mocker.patch.object(
            control.payload_state,
            "read_installed",
            return_value={"schema_version": 1, "version": "2.0.0"},
        )
        assert control._installed_release(ctx) == "2.0.0"
        installed_state.return_value = None
        assert control._installed_release(ctx) is None
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
        service = mocker.Mock()
        service.status.return_value = "absent"
        mocker.patch.object(uninstall, "_context", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(uninstall.projection, "purge_installed_projection", return_value=[])
        remove_command = mocker.patch.object(uninstall.command, "remove", return_value=True)
        assert uninstall.uninstall_product(purge=True) == {
            "stopped": 0,
            "command_removed": True,
            "purged": True,
        }
        remove_command.assert_called_once_with(Path(ctx.command), Path(ctx.executable))
        service.uninstall.assert_called_once_with(ctx)

        service.status.return_value = "loaded"
        with pytest.raises(errors.InstallError, match="remains loaded"):
            uninstall._remove_service(service, ctx)

        service.status.return_value = "absent"
        mocker.patch.object(uninstall, "_context", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        assert uninstall.uninstall_product() == {
            "stopped": 0,
            "command_removed": True,
            "purged": False,
        }
        mocker.patch.object(uninstall, "_context", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(
            uninstall.projection,
            "purge_installed_projection",
            return_value=["unknown.txt"],
        )

        with pytest.raises(errors.InstallError, match="unknown install content remains"):
            uninstall.uninstall_product(purge=True)

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
            return_value={"path": str(installed_command), "available": True, "owned": True},
        )
        mocker.patch.object(
            control.projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(control, "adapter").return_value.status.return_value = "running"
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(control, "_runtime_metrics", return_value=None)

        assert control.status(ctx)["command"]["path"] == str(installed_command)
        command_status.assert_called_once_with(installed_command, Path(ctx.executable))

        mocker.patch.object(uninstall, "_context", return_value=ctx)
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
            runtime_reader=install.apply.read_runtime,
            timeout_seconds=4,
        )

        mocker.patch.object(
            uninstall, "_context", side_effect=errors.UnsupportedPlatform("no host")
        )
        with pytest.raises(errors.InstallError, match="no host"):
            uninstall.uninstall_product()

    def test_control_status_includes_secret_free_runtime_metrics_when_listener_is_available(
        self, *, mocker
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = begin_transaction(ctx, released_artifact(), mocker=mocker)
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
            runtime = {
                "pid": 1,
                "uptime_seconds": 12,
                "active_responses": 0,
                "counters": {},
                "upstream_classifications": {},
                "last_failure": None,
            }
            mocker.patch.object(control, "_runtime_metrics", return_value=runtime)
            mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[1])
            evidence = control.status(ctx)
            assert evidence["runtime"] == runtime
            assert "authorization" not in json.dumps(evidence).lower()

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
        mocker.patch.object(control, "_runtime_metrics", return_value=foreign)
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
            mocker.patch.object(application.control, "_context", return_value=ctx)
            mocker.patch.object(application.control, "_runtime_metrics", return_value=None)
            adapter = mocker.patch.object(application.control, "adapter")
            adapter.return_value.status.return_value = "running"
            evidence = application.dispatch("status", port=ctx.port)
            assert evidence["payload_transaction"]["state"] == "recovery_required"
            assert "reason" not in evidence["payload_transaction"]
            rendered = json.dumps(evidence)
            for forbidden in ("secret-token", "private request", "/private/release-stage"):
                assert forbidden not in rendered
            assert journal_path.read_bytes() == before

    def test_reload_refuses_incompatible_listener_without_mutation(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(control, "_runtime_metrics", return_value={"pid": 12345})
        terminate = mocker.patch.object(process, "terminate_pid")
        with pytest.raises(errors.InstallError, match="transactional reload"):
            control.reload(ctx)
        terminate.assert_not_called()
