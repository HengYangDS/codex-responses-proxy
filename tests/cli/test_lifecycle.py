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
from tests.lifecycle.fixtures import install_context


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
            timeout_seconds=30.0,
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
            "state": "running",
            "detail": "healthy",
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321},
            "payload_transaction": None,
            "command": {
                "path": "/commands/codex-responses-proxy",
                "state": "owned",
                "kind": "symlink",
            },
        }
        context = mocker.patch.object(application.runtime_context, "create", return_value="context")
        status = mocker.patch.object(application.control, "status", return_value=evidence)
        code, stdout, stderr = self.invoke("status", "--json", "--port", "8801")
        assert code == 0
        assert json.loads(stdout) == evidence
        assert stderr == ""
        context.assert_called_once_with(port=8801)
        status.assert_called_once_with("context")

    def test_status_human_output_is_aligned_and_not_serialized_json(self, *, mocker) -> None:
        evidence = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "payload_transaction": None,
            "command": {
                "path": "/commands/codex-responses-proxy",
                "state": "owned",
                "kind": "symlink",
            },
        }
        mocker.patch.object(application.control, "status", return_value=evidence)

        code, stdout, stderr = self.invoke("status")

        assert code == 0
        assert stderr == ""
        assert "Codex Responses Proxy  Status" in stdout
        assert "Release" in stdout
        assert "2.0.8" in stdout
        assert "Payload" in stdout
        assert "Verified" in stdout
        assert "Service" in stdout
        assert "Running" in stdout
        assert "Listener" in stdout
        assert "PID 321" in stdout
        assert "Command" in stdout
        assert "Owned" in stdout
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

    def test_status_human_next_action_follows_the_lifecycle_state(self) -> None:
        base = {
            "release": "2.0.58",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "command": {"state": "owned", "kind": "symlink"},
        }

        invalid = application.presentation.render(
            "status",
            {
                **base,
                "state": "invalid",
                "payload_transaction": {
                    "state": "invalid",
                    "detail": "payload transaction journal is missing",
                },
            },
        )
        recoverable = application.presentation.render(
            "status",
            {
                **base,
                "state": "recovery_required",
                "payload_transaction": {"state": "committed"},
            },
        )

        assert "codex-responses-proxy status --json" in invalid
        assert "codex-responses-proxy recover" not in invalid
        assert "codex-responses-proxy recover" in recoverable

    def test_human_projection_covers_degraded_and_complete_command_results(
        self,
    ) -> None:
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
                "next": "codex-responses-proxy reload",
                "checks": {
                    "payload": {"status": "passed"},
                    "listener": {
                        "status": "failed",
                    },
                    "ignored": "not a check",
                },
            },
        )
        assert "Payload" in doctor
        assert "Passed" in doctor
        assert "Listener" in doctor
        assert "Action required" in doctor
        assert "codex-responses-proxy reload" in doctor

        installed = application.presentation.render("install", {"runtime": {"release": "2.0.11"}})
        assert "Installed" in installed
        assert "2.0.11" in installed
        upgraded = application.presentation.render(
            "install", {"state": "upgraded", "runtime": {"release": "2.0.12"}}
        )
        assert "Upgraded" in upgraded
        assert "2.0.12" in upgraded
        assert "Reloaded" in application.presentation.render("reload", {"old_pid": 1, "new_pid": 2})
        assert "Rolled Back" in application.presentation.render(
            "recover", {"version": "2.0.11", "state": "rolled_back"}
        )
        assert "Finalized" in application.presentation.render(
            "recover", {"version": "2.0.12", "state": "finalized"}
        )
        assert "No recovery required" in application.presentation.render(
            "recover", {"state": "not_required"}
        )
        closed = application.presentation.render(
            "recover",
            {"transaction_id": "tx-closed", "version": "2.0.12", "state": "closed"},
        )
        assert "Closed" in closed
        assert "Transaction tx-closed" in closed
        assert "Release     2.0.12" in closed
        assert "Not installed" in application.presentation.render(
            "uninstall",
            {
                "state": "not_installed",
                "stopped": 0,
                "command_removed": False,
            },
        )
        assert "Purged" in application.presentation.render(
            "uninstall", {"state": "purged", "stopped": 1, "command_removed": True}
        )
        assert application.presentation.render("future", {}) == ""

    def test_status_human_output_exposes_the_classification_detail(self) -> None:
        rendered = application.presentation.render(
            "status",
            {
                "state": "invalid",
                "detail": "payload transaction journal is missing",
                "release": "2.0.58",
                "payload_integrity": {"ok": True, "detail": "verified"},
                "service": "running",
                "listener_pids": [321],
                "runtime": None,
                "payload_transaction": {
                    "state": "invalid",
                    "detail": "payload transaction journal is missing",
                },
                "command": {"state": "owned", "kind": "symlink"},
            },
        )

        assert "payload transaction journal is missing" in rendered

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
        fixture_root = Path.cwd().anchor or "/"
        context = mocker.Mock(
            port=8792,
            install_dir=str(Path(fixture_root, "product")),
            executable=str(Path(fixture_root, "product", "codex-responses-proxy")),
            command=str(Path(fixture_root, "commands", "codex-responses-proxy")),
        )
        mocker.patch.object(
            projection,
            "verify_payload_manifest",
            return_value=(True, "release 2.0.15; 2 files verified"),
        )
        mocker.patch.object(
            application.control.payload_state,
            "read_installed",
            return_value={
                "schema_version": 1,
                "version": "2.0.15",
                "command": context.command,
            },
        )
        mocker.patch.object(
            application.control.command,
            "status",
            return_value={"path": context.command, "state": "owned", "kind": "symlink"},
        )
        adapter = mocker.patch.object(application.control, "adapter")
        pids = mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[321])
        mocker.patch.object(
            application.control,
            "read_runtime",
            return_value={"pid": 321, "accepting": True},
        )
        mocker.patch.object(payload_state, "status", return_value=None)
        adapter.return_value.status.return_value = "running"
        evidence = application.control.status(context)
        payload_integrity = evidence["payload_integrity"]
        assert isinstance(payload_integrity, dict)
        assert payload_integrity["ok"]
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
            "command": {"state": "owned", "kind": "symlink"},
        }
        mocker.patch.object(application.runtime_context, "create", return_value="context")
        mocker.patch.object(application.control, "status", return_value=evidence)
        code, stdout, stderr = self.invoke("doctor", "--json")
        report = json.loads(stdout)
        assert code == 1
        assert stderr == ""
        assert not report["ok"]
        assert report["checks"]["listener"]["status"] == "failed"
        assert report["next"] == "codex-responses-proxy reload"
        assert "Traceback" not in stdout
        assert "Warning" not in stdout

    def test_doctor_classifies_a_pristine_host_without_false_failures(self) -> None:
        report = application._doctor(
            {
                "state": "not_installed",
                "release": None,
                "payload_integrity": {
                    "ok": False,
                    "detail": "installed payload manifest is unavailable",
                },
                "service": "absent",
                "listener_pids": [],
                "runtime": None,
                "payload_transaction": None,
                "command": {"state": "absent", "kind": None, "path": "/bin/proxy"},
            }
        )

        assert report == {
            "ok": False,
            "state": "not_installed",
            "next": "codex-responses-proxy install --help",
            "checks": {
                "installation": {
                    "status": "failed",
                    "detail": "not installed",
                }
            },
        }

    def test_doctor_uses_one_state_level_next_action(self) -> None:
        recovery = application._doctor(
            {
                "state": "recovery_required",
                "release": "2.0.58",
                "payload_integrity": {"ok": True, "detail": "verified"},
                "service": "running",
                "listener_pids": [321],
                "runtime": {"pid": 321, "accepting": True},
                "payload_transaction": {"state": "committed"},
                "command": {"state": "owned", "kind": "symlink"},
            }
        )
        invalid = application._doctor(
            {
                "state": "invalid",
                "detail": "payload transaction journal is missing",
                "release": "2.0.58",
                "payload_integrity": {"ok": True, "detail": "verified"},
                "service": "running",
                "listener_pids": [321],
                "runtime": {"pid": 321, "accepting": True},
                "payload_transaction": {
                    "state": "invalid",
                    "detail": "payload transaction journal is missing",
                },
                "command": {"state": "owned", "kind": "symlink"},
            }
        )

        assert recovery["next"] == "codex-responses-proxy recover"
        assert invalid["next"] == "codex-responses-proxy status --json"
        assert all("next" not in check for check in recovery["checks"].values())

        invalid_rollback = application._doctor(
            {
                "state": "invalid",
                "release": "2.0.58",
                "payload_integrity": {"ok": True, "detail": "verified"},
                "service": "running",
                "listener_pids": [321],
                "runtime": {"pid": 321, "accepting": True},
                "payload_transaction": None,
                "rollback": {"state": "invalid", "detail": "binding mismatch"},
                "command": {"state": "owned", "kind": "symlink"},
            }
        )

        assert invalid_rollback["checks"]["rollback"] == {
            "status": "failed",
            "detail": "binding mismatch",
        }

    def test_doctor_requires_integrity_service_and_exact_listener_identity(self, subtests) -> None:
        healthy = {
            "release": "2.0.8",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": {"pid": 321, "accepting": True},
            "payload_transaction": None,
            "command": {
                "path": "/commands/codex-responses-proxy",
                "state": "owned",
                "kind": "symlink",
            },
        }
        cases = (
            (healthy, True, ("passed", "passed", "passed", "passed")),
            (
                {
                    **healthy,
                    "payload_integrity": {"ok": False, "detail": "hash mismatch"},
                },
                False,
                ("failed", "passed", "passed", "passed"),
            ),
            (
                {**healthy, "service": "unknown"},
                False,
                ("passed", "failed", "passed", "passed"),
            ),
            (
                {**healthy, "listener_pids": [654]},
                False,
                ("passed", "passed", "failed", "passed"),
            ),
            (
                {
                    **healthy,
                    "command": {
                        "path": "/commands/codex-responses-proxy",
                        "state": "foreign",
                        "kind": "symlink",
                    },
                },
                False,
                ("passed", "passed", "passed", "failed"),
            ),
        )
        for evidence, expected_ok, statuses in cases:
            with subtests.test(evidence=evidence):
                report = application._doctor(evidence)
                assert report["ok"] is expected_ok
                assert (
                    tuple(
                        report["checks"][name]["status"]
                        for name in ("payload", "service", "listener", "command")
                    )
                    == statuses
                )

    def test_reload_delegates_transactionally_with_an_explicit_timeout(self, *, mocker) -> None:
        result = {"old_pid": 321, "new_pid": 654}
        mocker.patch.object(application.runtime_context, "create", return_value="context")
        reload = mocker.patch.object(application.control, "reload", return_value=result)
        code, stdout, stderr = self.invoke(
            "reload", "--json", "--port", "8801", "--timeout-seconds", "12.5"
        )
        assert code == 0
        assert json.loads(stdout) == result
        assert stderr == ""
        reload.assert_called_once_with("context", timeout_seconds=12.5)

    def test_install_delegates_with_an_explicit_timeout(self, tmp_path: Path, *, mocker) -> None:
        asset = tmp_path / "release.tar.gz"
        trust = tmp_path / "release.pub"
        install = mocker.patch.object(application.install, "install_asset", return_value={})

        self.invoke(
            "install",
            "--asset",
            str(asset),
            "--trust-anchor",
            str(trust),
            "--timeout-seconds",
            "45",
        )

        install.assert_called_once_with(asset, trust_anchor=trust, port=8792, timeout_seconds=45.0)

    def test_recover_restores_only_the_runtime_bound_retained_transaction(self, *, mocker) -> None:
        runtime = {"pid": 321, "release": "2.0.10", "accepting": True}
        context = mocker.patch.object(application.runtime_context, "create", return_value="context")
        mocker.patch.object(application.control, "read_runtime", return_value=runtime)
        recover = mocker.patch.object(
            application.transaction,
            "recover",
            return_value={"version": "2.0.13", "state": "rolled_back"},
        )

        code, stdout, stderr = self.invoke("recover", "--json", "--port", "8801")

        assert code == 0
        assert stderr == ""
        assert json.loads(stdout) == {"state": "rolled_back", "version": "2.0.13"}
        context.assert_called_once_with(port=8801)
        recover.assert_called_once_with("context", runtime=runtime)

    def test_rollback_is_discoverable_and_delegates_to_the_installed_lifecycle(
        self, *, mocker
    ) -> None:
        result = {
            "state": "rolled_back",
            "from_release": "3.0.6",
            "to_release": "3.0.5",
        }
        context = mocker.patch.object(application.runtime_context, "create", return_value="context")
        rollback = mocker.patch.object(application.control, "rollback", return_value=result)

        code, stdout, stderr = self.invoke(
            "rollback", "--json", "--port", "8801", "--timeout-seconds", "12.5"
        )

        assert code == 0
        assert stderr == ""
        assert json.loads(stdout) == result
        context.assert_called_once_with(port=8801)
        rollback.assert_called_once_with("context", timeout_seconds=12.5)

    def test_rollback_without_a_predecessor_has_matching_human_and_json_semantics(
        self, *, mocker
    ) -> None:
        unavailable = {
            "state": "unavailable",
            "detail": "no verified predecessor is retained",
        }
        mocker.patch.object(application.runtime_context, "create", return_value="context")
        mocker.patch.object(application.control, "rollback", return_value=unavailable)

        json_code, json_stdout, json_stderr = self.invoke("rollback", "--json")
        human_code, human_stdout, human_stderr = self.invoke("rollback")

        assert json_code == human_code == 0
        assert json.loads(json_stdout) == unavailable
        assert "No verified predecessor" in human_stdout
        assert json_stderr == human_stderr == ""

    @pytest.mark.parametrize("json_output", [False, True])
    def test_recover_projects_one_precise_invalid_state_contract(
        self,
        tmp_path: Path,
        json_output: bool,
        *,
        mocker,
    ) -> None:
        ctx = install_context(tmp_path)
        transaction_root = Path(payload_state.transaction_root(ctx))
        transaction_root.mkdir(parents=True)
        journal = Path(payload_state.journal_path(ctx))
        journal.write_bytes(b"{not-json\n")
        before = journal.read_bytes()
        mocker.patch.object(application.runtime_context, "create", return_value=ctx)
        mocker.patch.object(application.control, "read_runtime", return_value={"pid": 321})

        arguments = ("recover", "--json") if json_output else ("recover",)
        code, stdout, stderr = self.invoke(*arguments)

        assert code == 2
        assert stdout == ""
        assert "Traceback" not in stderr
        assert "warning" not in stderr.casefold()
        if json_output:
            assert json.loads(stderr) == {
                "error": {
                    "code": "recovery_state_invalid",
                    "message": "payload transaction journal is malformed JSON",
                    "next": "codex-responses-proxy status --json",
                }
            }
        else:
            assert "payload transaction journal is malformed JSON" in stderr
            assert "codex-responses-proxy status --json" in stderr
        assert journal.read_bytes() == before

    def test_uninstall_removes_only_the_owned_service_unless_purge_is_requested(
        self, *, mocker
    ) -> None:
        uninstall = mocker.patch.object(
            application.uninstall,
            "uninstall_product",
            return_value={
                "state": "uninstalled",
                "stopped": 1,
                "command_removed": True,
            },
        )
        code, stdout, stderr = self.invoke("uninstall", "--port", "8801")
        assert code == 0
        assert "Uninstalled" in stdout
        assert "1" in stdout
        assert not stdout.lstrip().startswith("{")
        assert stderr == ""
        uninstall.assert_called_once_with(port=8801, purge=False)
        uninstall = mocker.patch.object(
            application.uninstall,
            "uninstall_product",
            return_value={"state": "purged", "stopped": 0, "command_removed": True},
        )
        code, stdout, stderr = self.invoke("uninstall", "--purge")
        assert code == 0
        assert stderr == ""
        assert "Purged" in stdout
        assert not stdout.lstrip().startswith("{")
        uninstall.assert_called_once_with(port=8792, purge=True)

    def test_pristine_recover_and_uninstall_are_explicit_no_ops(self, *, mocker) -> None:
        context = mocker.patch.object(application.runtime_context, "create", return_value="context")
        mocker.patch.object(application.control, "read_runtime", return_value=None)
        recover = mocker.patch.object(
            application.transaction, "recover", return_value={"state": "not_required"}
        )

        code, stdout, stderr = self.invoke("recover", "--json")

        assert code == 0
        assert json.loads(stdout) == {"state": "not_required"}
        assert stderr == ""
        context.assert_called_once_with(port=8792)
        recover.assert_called_once_with("context", runtime=None)

        uninstall = mocker.patch.object(
            application.uninstall,
            "uninstall_product",
            return_value={
                "state": "not_installed",
                "stopped": 0,
                "command_removed": False,
            },
        )
        code, stdout, stderr = self.invoke("uninstall", "--purge", "--json")
        assert code == 0
        assert json.loads(stdout)["state"] == "not_installed"
        assert stderr == ""
        uninstall.assert_called_once_with(port=8792, purge=True)

    def test_expected_lifecycle_failures_are_rendered_once(self, *, mocker) -> None:
        mocker.patch.object(
            application.runtime_context,
            "create",
            side_effect=errors.InstallError(
                "bad port",
                next_command="codex-responses-proxy status --help",
            ),
        )
        code, stdout, stderr = self.invoke("status", "--json")
        assert code == 2
        assert stdout == ""
        assert json.loads(stderr) == {
            "error": {
                "code": "lifecycle_error",
                "message": "bad port",
                "next": "codex-responses-proxy status --help",
            }
        }

    def test_install_dispatches_to_its_single_owner(self, *, mocker) -> None:
        asset = Path("release.tar.gz")
        anchor = Path("allowed-signers")
        install = mocker.patch.object(
            application.install, "install_asset", return_value={"ok": True}
        )
        assert application.dispatch("install", asset=asset, trust_anchor=anchor, port=8801) == {
            "ok": True
        }
        install.assert_called_once_with(asset, trust_anchor=anchor, port=8801, timeout_seconds=30.0)

    def test_internal_dispatch_argument_contracts_fail_closed(self) -> None:
        cases = (
            (
                "install",
                {
                    "asset": "release.tar.gz",
                    "trust_anchor": Path("trust"),
                    "port": 8792,
                },
            ),
            ("status", {"port": True}),
            ("reload", {"port": 8792, "timeout_seconds": True}),
            ("uninstall", {"port": 8792, "purge": "yes"}),
        )

        for command, arguments in cases:
            with pytest.raises(TypeError):
                application.dispatch(command, **arguments)

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
        activate = mocker.patch.object(application.runtime_spec, "activate")
        executable = mocker.patch.object(
            application.service_runtime,
            "current_executable",
            return_value="/opt/proxy/bin/codex-responses-proxy",
        )
        entrypoint = mocker.patch("codex_responses_proxy.service.entrypoint.run", return_value=7)
        assert application.main([application.service_runtime.LISTENER_MODE]) == 7
        entrypoint.assert_called_once_with()
        mocker.stop(entrypoint)

        handoff = mocker.patch("codex_responses_proxy.service.entrypoint.run", return_value=8)
        assert application.main([application.service_runtime.HANDOFF_CHILD_MODE]) == 8
        handoff.assert_called_once_with(handoff_child=True)
        mocker.stop(handoff)

        watchdog = mocker.patch(
            "codex_responses_proxy.lifecycle.supervision.watchdog.run",
            return_value=None,
        )
        assert application.main([application.service_runtime.WATCHDOG_MODE]) == 0
        watchdog.assert_called_once_with()
        mocker.stop(watchdog)

        assert application.main([application.service_runtime.PREWARM_MODE]) == 0
        code, stdout, stderr = self.invoke("--help")
        assert code == 0
        assert application.service_runtime.PREWARM_MODE not in stdout
        assert stderr == ""

        assert activate.call_count == 3
        assert activate.call_args_list == [
            mocker.call("/opt/proxy/bin/codex-responses-proxy"),
            mocker.call("/opt/proxy/bin/codex-responses-proxy"),
            mocker.call("/opt/proxy/bin/codex-responses-proxy"),
        ]
        assert executable.call_count == 3

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
