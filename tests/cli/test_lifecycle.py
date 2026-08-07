"""Command-boundary contracts for installed product lifecycle operations."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process


class CliLifecycleContracts:
    """Keep parsing, composition, and rendering at one public boundary."""

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = application.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_install_delegates_exact_asset_trust_anchor_and_port(self, *, mocker) -> None:
        install = mocker.patch.object(
            application.install, "install_asset", return_value={"release": "2.0.8"}
        )
        code, stdout, stderr = self.invoke(
            "install",
            "--asset",
            "/release/proxy.tar.gz",
            "--trust-anchor",
            "/release/trust.json",
            "--port",
            "8801",
        )
        assert code == 0
        assert "Installed" in stdout
        assert "2.0.8" in stdout
        assert not stdout.lstrip().startswith("{")
        assert stderr == ""
        install.assert_called_once_with(
            Path("/release/proxy.tar.gz"),
            trust_anchor=Path("/release/trust.json"),
            port=8801,
        )

    def test_source_version_requires_the_real_src_checkout_shape(self, tmp_path, *, mocker) -> None:
        mocker.patch.object(application, "__file__", str(tmp_path / "installed.py"))
        assert application._source_version() is None

    def test_frozen_and_source_release_versions_use_their_bound_owners(
        self, tmp_path, *, mocker
    ) -> None:
        (tmp_path / "VERSION").write_text("9.8.7\n", encoding="utf-8")
        mocker.patch.object(sys, "_MEIPASS", str(tmp_path), create=True)
        assert application._release_version() == "9.8.7"
        mocker.patch.object(sys, "_MEIPASS", None)
        mocker.patch.object(application, "_source_version", return_value="2.0.8")
        assert application._release_version() == "2.0.8"

    def test_status_uses_the_read_only_lifecycle_owner(self, *, mocker) -> None:
        evidence = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321},
            "payload_transaction": None,
        }
        context = mocker.patch.object(application.control, "_context", return_value="context")
        status = mocker.patch.object(application.control, "status", return_value=evidence)
        code, stdout, stderr = self.invoke("status", "--json", "--port", "8801")
        assert code == 0
        assert json.loads(stdout) == evidence
        assert stderr == ""
        context.assert_called_once_with(8801)
        status.assert_called_once_with("context")

    def test_status_human_output_is_aligned_and_not_serialized_json(self, *, mocker) -> None:
        evidence = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "payload_transaction": None,
        }
        mocker.patch.object(application.control, "status", return_value=evidence)

        code, stdout, stderr = self.invoke("status")

        assert code == 0
        assert stderr == ""
        assert "Codex Responses Proxy  Status" in stdout
        assert "Release" in stdout and "2.0.8" in stdout
        assert "Payload" in stdout and "Verified" in stdout
        assert "Service" in stdout and "Running" in stdout
        assert "Listener" in stdout and "PID 321" in stdout
        assert not stdout.lstrip().startswith("{")
        lines = stdout.splitlines()
        value_columns = {
            line.index(value)
            for line, value in (
                (next(line for line in lines if "2.0.8" in line), "2.0.8"),
                (next(line for line in lines if "Verified" in line), "Verified"),
                (next(line for line in lines if "Running" in line), "Running"),
            )
        }
        assert len(value_columns) == 1

    def test_human_projection_covers_degraded_and_complete_command_results(self) -> None:
        degraded = application.presentation.render(
            "status",
            {
                "release": "",
                "payload_integrity": {"ok": False},
                "service": "",
                "listener_pids": [],
            },
        )
        assert "Not installed" in degraded
        assert "Action required" in degraded
        assert "codex-responses-proxy doctor" in degraded

        doctor = application.presentation.render(
            "doctor",
            {
                "checks": {
                    "payload": {"status": "passed"},
                    "listener": {
                        "status": "failed",
                        "next": "run `codex-responses-proxy reload`, then inspect the service log",
                    },
                    "ignored": "not a check",
                }
            },
        )
        assert "Payload" in doctor and "Passed" in doctor
        assert "Listener" in doctor and "Action required" in doctor
        assert "codex-responses-proxy reload" in doctor

        installed = application.presentation.render("install", {"runtime": {"release": "2.0.11"}})
        assert "Installed" in installed and "2.0.11" in installed
        assert "Reloaded" in application.presentation.render("reload", {"old_pid": 1, "new_pid": 2})
        assert "Purged" in application.presentation.render(
            "uninstall", {"stopped": 1, "purged": True}
        )
        assert application.presentation.render("future", {}) == ""

    def test_status_returns_bounded_current_runtime_evidence(self, *, mocker) -> None:
        evidence = {
            "release": "2.0.10",
            "payload_integrity": {
                "ok": True,
                "detail": "release 2.0.15; 2 files verified",
            },
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "payload_transaction": None,
        }
        mocker.patch.object(application.control, "status", return_value=evidence)
        code, stdout, stderr = self.invoke("status", "--json")
        assert code == 0
        assert json.loads(stdout) == evidence
        assert stderr == ""

    def test_status_binds_listener_identity_to_the_installed_executable(self, *, mocker) -> None:
        context = mocker.Mock(port=8792, executable="/product/codex-responses-proxy")
        mocker.patch.object(
            projection,
            "verify_payload_manifest",
            return_value=(True, "release 2.0.15; 2 files verified"),
        )
        mocker.patch.object(application.control, "_installed_release", return_value="2.0.15")
        adapter = mocker.patch.object(application.control, "adapter")
        pids = mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[321])
        mocker.patch.object(
            application.control,
            "_runtime_metrics",
            return_value={"pid": 321, "accepting": True},
        )
        mocker.patch.object(payload_state, "status", return_value=None)
        adapter.return_value.status.return_value = "running"
        evidence = application.control.status(context)
        assert evidence["payload_integrity"]["ok"]
        assert evidence["listener_pids"] == [321]
        pids.assert_called_once_with(context)

    def test_doctor_classifies_an_unavailable_listener_without_false_success(
        self, *, mocker
    ) -> None:
        evidence = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "installed",
            "listener_pids": [],
            "runtime": None,
            "payload_transaction": None,
        }
        mocker.patch.object(application.control, "_context", return_value="context")
        mocker.patch.object(application.control, "status", return_value=evidence)
        code, stdout, stderr = self.invoke("doctor", "--json")
        report = json.loads(stdout)
        assert code == 1
        assert stderr == ""
        assert not report["ok"]
        assert report["checks"]["listener"]["status"] == "failed"
        assert (
            report["checks"]["listener"]["next"]
            == "run `codex-responses-proxy reload`, then inspect the service log"
        )
        assert "Traceback" not in stdout
        assert "Warning" not in stdout

    def test_doctor_requires_integrity_service_and_exact_listener_identity(self, subtests) -> None:
        healthy = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "payload_transaction": None,
        }
        cases = (
            (healthy, True, ("passed", "passed", "passed")),
            (
                {**healthy, "payload_integrity": {"ok": False, "detail": "hash mismatch"}},
                False,
                ("failed", "passed", "passed"),
            ),
            ({**healthy, "service": "unknown"}, False, ("passed", "failed", "passed")),
            (
                {**healthy, "listener_pids": [654]},
                False,
                ("passed", "passed", "failed"),
            ),
        )
        for evidence, expected_ok, statuses in cases:
            with subtests.test(evidence=evidence):
                report = application._doctor(evidence)
                assert report["ok"] is expected_ok
                assert (
                    tuple(
                        report["checks"][name]["status"]
                        for name in ("payload", "service", "listener")
                    )
                    == statuses
                )

    def test_reload_delegates_transactionally_with_an_explicit_timeout(self, *, mocker) -> None:
        result = {"old_pid": 321, "new_pid": 654}
        mocker.patch.object(application.control, "_context", return_value="context")
        reload = mocker.patch.object(application.control, "reload", return_value=result)
        code, stdout, stderr = self.invoke(
            "reload", "--json", "--port", "8801", "--timeout-seconds", "12.5"
        )
        assert code == 0
        assert json.loads(stdout) == result
        assert stderr == ""
        reload.assert_called_once_with("context", timeout_seconds=12.5)

    def test_recover_restores_only_the_runtime_bound_retained_transaction(self, *, mocker) -> None:
        runtime = {"pid": 321, "release": "2.0.10", "accepting": True}
        context = mocker.patch.object(application.control, "_context", return_value="context")
        mocker.patch.object(application.control, "_runtime_metrics", return_value=runtime)
        recover = mocker.patch.object(
            application.transaction,
            "rollback_recovery",
            return_value={"version": "2.0.13", "state": "rolled_back"},
        )

        code, stdout, stderr = self.invoke("recover", "--json", "--port", "8801")

        assert code == 0
        assert stderr == ""
        assert json.loads(stdout) == {"state": "rolled_back", "version": "2.0.13"}
        context.assert_called_once_with(8801)
        recover.assert_called_once_with("context", runtime=runtime)

    def test_uninstall_removes_only_the_owned_service_unless_purge_is_requested(
        self, *, mocker
    ) -> None:
        uninstall = mocker.patch.object(
            application.uninstall, "uninstall_product", return_value={"stopped": 1, "purged": False}
        )
        code, stdout, stderr = self.invoke("uninstall", "--port", "8801")
        assert code == 0
        assert "Uninstalled" in stdout and "1" in stdout
        assert not stdout.lstrip().startswith("{")
        assert stderr == ""
        uninstall.assert_called_once_with(port=8801, purge=False)
        uninstall = mocker.patch.object(
            application.uninstall,
            "uninstall_product",
            return_value={"stopped": 0, "purged": True},
        )
        code, stdout, stderr = self.invoke("uninstall", "--purge")
        assert code == 0
        assert stderr == ""
        assert "Purged" in stdout
        assert not stdout.lstrip().startswith("{")
        uninstall.assert_called_once_with(port=8792, purge=True)

    def test_expected_lifecycle_failures_are_rendered_once(self, *, mocker) -> None:
        mocker.patch.object(
            application.control, "_context", side_effect=errors.InstallError("bad port")
        )
        code, stdout, stderr = self.invoke("status", "--json")
        assert code == 2
        assert stdout == ""
        assert json.loads(stderr) == {"error": {"message": "bad port"}}

    def test_install_and_version_dispatch_to_their_single_owners(self, *, mocker) -> None:
        asset = Path("release.tar.gz")
        anchor = Path("allowed-signers")
        install = mocker.patch.object(
            application.install, "install_asset", return_value={"ok": True}
        )
        version = mocker.patch.object(application, "_release_version", return_value="2.0.8")

        assert application.dispatch("install", asset=asset, trust_anchor=anchor, port=8801) == {
            "ok": True
        }
        assert application.dispatch("version") == "2.0.8"
        install.assert_called_once_with(asset, trust_anchor=anchor, port=8801)
        version.assert_called_once_with()

    def test_subcommand_help_and_parse_errors_are_bounded(self) -> None:
        for arguments in (("status", "--help"), ("install", "--help")):
            code, stdout, stderr = self.invoke(*arguments)
            assert code == 0
            assert "Usage:" in stdout
            assert stderr == ""

        code, stdout, stderr = self.invoke("install")
        assert code == 2
        assert stdout == ""
        assert "required" in stderr

        code, stdout, stderr = self.invoke("status", "--unknown")
        assert code == 2
        assert stdout == ""
        assert "Unknown option" in stderr

    def test_no_command_uses_sys_argv_and_renders_public_help(self, *, mocker) -> None:
        mocker.patch.object(application.sys, "argv", ["codex-responses-proxy"])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = application.main()

        assert code == 0
        assert "COMMAND" in stdout.getvalue()
        assert stderr.getvalue() == ""

    def test_internal_roles_are_exact_and_never_public_commands(self, *, mocker) -> None:
        entrypoint = mocker.patch("codex_responses_proxy.service.entrypoint.run", return_value=7)
        assert application.main([application.service_runtime.LISTENER_MODE]) == 7
        entrypoint.assert_called_once_with()
        mocker.stop(entrypoint)

        handoff = mocker.patch("codex_responses_proxy.service.entrypoint.run", return_value=8)
        assert application.main([application.service_runtime.HANDOFF_CHILD_MODE]) == 8
        handoff.assert_called_once_with(handoff_child=True)
        mocker.stop(handoff)

        watchdog = mocker.patch(
            "codex_responses_proxy.lifecycle.supervision.watchdog.run", return_value=None
        )
        assert application.main([application.service_runtime.WATCHDOG_MODE]) == 0
        watchdog.assert_called_once_with()
        mocker.stop(watchdog)

        for arguments in (
            [application.service_runtime.LISTENER_MODE, "extra"],
            ["--internal-unknown"],
        ):
            code, stdout, stderr = self.invoke(*arguments)
            assert code == 2
            assert stdout == ""
            assert "internal" in stderr

    def test_rendering_none_and_unknown_dispatch_have_explicit_boundaries(self, *, mocker) -> None:
        rendered = mocker.patch.object(application, "print")
        application._render("status", None, as_json=False)
        rendered.assert_not_called()

        with pytest.raises(ValueError, match="not implemented"):
            application.dispatch("future", port=8792)
