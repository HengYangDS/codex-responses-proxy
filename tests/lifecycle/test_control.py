"""Contracts for installed status and protocol-v2 reload."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application
from codex_responses_proxy.lifecycle import control, uninstall
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
            control.projection,
            "verify_historical_projection",
            side_effect=errors.InstallError("historical manifest invalid"),
        )
        mocker.patch.object(control, "adapter", side_effect=RuntimeError("service unavailable"))
        mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
        evidence = control.status(ctx)
        assert evidence["payload_integrity"] == {"ok": False, "detail": str(current_error)}
        assert evidence["service"] == "unknown"

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
        version = Path(ctx.install_dir) / "VERSION"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("2.0.0\n", encoding="utf-8")
        assert control._installed_release(ctx) == "2.0.0"
        version.unlink()
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

    def test_uninstall_product_covers_success_and_fail_closed_boundaries(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        service = mocker.Mock()
        service.status.return_value = "absent"
        mocker.patch.object(uninstall, "_context", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(uninstall.projection, "purge_installed_projection", return_value=[])
        assert uninstall.uninstall_product(purge=True) == {"stopped": 0, "purged": True}
        service.uninstall.assert_called_once_with(ctx)

        service.status.return_value = "loaded"
        with pytest.raises(errors.InstallError, match="remains loaded"):
            uninstall._remove_service(service, ctx)

        service.status.return_value = "absent"
        mocker.patch.object(uninstall, "_context", return_value=ctx)
        mocker.patch.object(uninstall, "adapter", return_value=service)
        mocker.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[])
        assert uninstall.uninstall_product() == {"stopped": 0, "purged": False}
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
                "uptime_seconds": 12,
                "active_responses": 0,
                "counters": {},
                "upstream_classifications": {},
                "last_failure": None,
            }
            mocker.patch.object(control, "_runtime_metrics", return_value=runtime)
            evidence = control.status(ctx)
            assert evidence["runtime"] == runtime
            assert "authorization" not in json.dumps(evidence).lower()

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
            evidence = application.dispatch("status", mocker.Mock(port=ctx.port))
            assert evidence["payload_transaction"]["state"] == "recovery_required"
            assert "reason" not in evidence["payload_transaction"]
            rendered = json.dumps(evidence)
            for forbidden in ("secret-token", "private request", "/private/release-stage"):
                assert forbidden not in rendered
            assert journal_path.read_bytes() == before

    def test_reload_refuses_legacy_listener_without_mutation(self, *, mocker):
        ctx = install_context(Path(tempfile.mkdtemp()))
        mocker.patch.object(control, "_runtime_metrics", return_value={"pid": 12345})
        terminate = mocker.patch.object(process, "terminate_pid")
        with pytest.raises(errors.InstallError, match="verified successor release"):
            control.reload(ctx)
        terminate.assert_not_called()
