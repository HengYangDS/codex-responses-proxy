"""Linux native supervision lifecycle contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle.supervision import linux
from codex_responses_proxy.service import runtime as service_runtime
from tests.lifecycle.fixtures import platform_context
from tests.lifecycle.supervision.fixtures import completed as _completed
from tests.lifecycle.supervision.fixtures import set_file as _set_file
from tests.lifecycle.supervision.fixtures import temporary_context as _temporary_context

ROOT = Path(__file__).resolve().parents[3]


class TestLinuxLifecycle:
    def test_service_carrier_uses_the_context_user_home(self, tmp_path) -> None:
        owned_home = tmp_path / "owned-home"
        ctx = platform_context()
        ctx.user_home = str(owned_home)

        assert linux._unit_path(ctx) == str(
            owned_home / ".config" / "systemd" / "user" / f"{ctx.service_id}.service"
        )

    def test_probe_and_install_dispatch(self, *, mocker):
        for executable, output, expected in (
            (None, None, False),
            ("systemctl", _completed(stderr="Failed to connect to bus"), False),
            ("systemctl", _completed(stdout="degraded"), True),
        ):
            mocker.patch.object(linux.shutil, "which", return_value=executable)
            invoked = mocker.patch.object(linux.subprocess, "run", return_value=output)
            assert linux._has_user_systemd() == expected
            assert invoked.call_count == int(executable is not None)
            mocker.stopall()

        ctx = platform_context()
        for available in (False, True):
            mocker.patch.object(linux, "_has_user_systemd", return_value=available)
            called = mocker.patch.object(linux, "_install_systemd")
            if available:
                linux.install(ctx)
                called.assert_called_once_with(ctx)
            else:
                with pytest.raises(errors.ManualStartRequiredError, match="systemd user manager"):
                    linux.install(ctx)
                called.assert_not_called()
            mocker.stopall()

    def test_native_service_contract_never_persists_python_or_source_paths(self):
        ctx = platform_context()
        unit = linux.render_unit(ctx)
        assert f'ExecStart="{ctx.executable}" --internal-watchdog' in unit
        assert "python" not in unit.lower()
        assert ".py" not in unit

    def test_systemd_supervisor_never_signals_detached_runtime_generations(self):
        """Replacing the watchdog must not kill a listener-owned handoff child."""
        unit = linux.render_unit(platform_context())

        assert "KillMode=process" in unit

    def test_systemd_unit_quotes_path_values_and_specifier_tokens(self):
        ctx = platform_context()
        ctx.install_dir = '/tmp/product path/%i/"payload"'
        ctx.executable = f"{ctx.install_dir}/bin/codex-responses-proxy"
        ctx.log_dir = '/tmp/state path/%h/"logs"'
        ctx.user_home = '/tmp/home path/%u/"user"'

        unit = linux.render_unit(ctx)

        assert (
            'ExecStart="/tmp/product path/%%i/\\"payload\\"/bin/codex-responses-proxy" '
            "--internal-watchdog"
        ) in unit

        with _temporary_context("log_dir") as temporary:
            temporary.executable = ctx.executable
            _set_file(linux._unit_path(temporary), unit)
            assert linux.configured_executable(temporary) == ctx.executable

    def test_systemd_unit_rejects_control_characters(self):
        ctx = platform_context()
        ctx.executable = "/tmp/bin/codex-responses-proxy\nother"

        with pytest.raises(errors.InstallError, match="control character"):
            linux.render_unit(ctx)

    def test_configured_executable_reads_only_one_valid_exec_start(self):
        with _temporary_context("log_dir") as ctx:
            unit = Path(linux._unit_path(ctx))
            assert linux.configured_executable(ctx) is None
            _set_file(unit, linux.render_unit(ctx))
            assert linux.configured_executable(ctx) == ctx.executable
            _set_file(unit, "[Service]\nExecStart=/one\nExecStart=/two\n")
            assert linux.configured_executable(ctx) is None

    def test_status_observes_registered_service_without_a_unit_file(self, *, mocker):
        ctx = platform_context()
        mocker.patch.object(linux.shutil, "which", return_value="/usr/bin/systemctl")
        mocker.patch.object(linux, "_has_user_systemd", return_value=True)
        mocker.patch.object(
            linux.subprocess,
            "run",
            return_value=_completed(stdout="LoadState=loaded\nActiveState=active\n"),
        )

        assert linux.status(ctx) == "running"

    def test_systemd_install_success_and_failure(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            unit = Path(linux._unit_path(ctx))
            mocker.patch.dict(linux.os.environ, {"USER": "tester"})
            invoked = mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            )
            linux._install_systemd(ctx)
            assert unit.read_text(encoding="utf-8") == linux.render_unit(ctx)
            assert invoked.call_args_list[1].args[0] == [
                "systemctl",
                "--user",
                "enable",
                "--now",
                str(unit),
            ]
            assert invoked.call_args_list[-1].args[0][0] == "loginctl"
            mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[_completed(), _completed(returncode=1, stderr=" denied ")],
            )

            with pytest.raises(errors.InstallError, match="systemctl enable failed: denied"):
                linux._install_systemd(ctx)

    def test_uninstall_and_status(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            unit = Path(linux._unit_path(ctx))
            _set_file(unit, "unit")
            mocker.patch.object(linux.shutil, "which", return_value="systemctl")
            invoked = mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[
                    _completed(stdout="LoadState=loaded\nActiveState=inactive\n"),
                    _completed(),
                    _completed(),
                    _completed(stdout="LoadState=not-found\nActiveState=inactive\n"),
                ],
            )
            mocker.patch.object(linux.process, "pids_naming_executable", return_value=[])
            linux.uninstall(ctx)
            assert not unit.exists()
            mocker.patch.object(linux.shutil, "which", return_value=None)
            invoked = mocker.patch.object(linux.subprocess, "run")
            mocker.patch.object(linux.process, "pids_naming_executable", return_value=[])
            linux.uninstall(ctx)
            invoked.assert_not_called()
            for systemd, executable, output, expected in (
                (
                    True,
                    "systemctl",
                    "LoadState=loaded\nActiveState=active\n",
                    "running",
                ),
                (
                    True,
                    "systemctl",
                    "LoadState=loaded\nActiveState=inactive\n",
                    "installed",
                ),
                (False, None, "", "absent"),
            ):
                _set_file(unit, "unit" if systemd else None)
                mocker.patch.object(linux.shutil, "which", return_value=executable)
                mocker.patch.object(
                    linux.subprocess,
                    "run",
                    return_value=_completed(stdout=output),
                )
                assert linux.status(ctx) == expected

    def test_uninstall_fails_closed_until_systemd_and_cron_are_proven_absent(self, *, mocker):
        with _temporary_context("log_dir") as ctx:
            unit = _set_file(linux._unit_path(ctx), "unit")
            mocker.patch.object(linux.shutil, "which", return_value=None)
            with pytest.raises(errors.InstallError, match="systemctl is unavailable"):
                linux.uninstall(ctx)
            assert unit.exists()

            mocker.patch.object(linux.shutil, "which", return_value="systemctl")
            mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[
                    _completed(stdout="LoadState=loaded\nActiveState=inactive\n"),
                    _completed(returncode=1, stderr="denied"),
                ],
            )
            with pytest.raises(errors.InstallError, match="systemctl disable failed"):
                linux.uninstall(ctx)
            assert unit.exists()

            _set_file(unit, "unit")
            mocker.patch.object(linux.shutil, "which", return_value="systemctl")
            mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[
                    _completed(stdout="LoadState=loaded\nActiveState=inactive\n"),
                    _completed(),
                    _completed(returncode=1),
                ],
            )
            with pytest.raises(errors.InstallError, match="daemon-reload failed"):
                linux.uninstall(ctx)

            _set_file(unit, "unit")
            mocker.patch.object(linux.shutil, "which", return_value="crontab")
            mocker.patch.object(
                linux.subprocess,
                "run",
                side_effect=[_completed(), _completed()],
            )
            mocker.patch.object(linux, "status", return_value="installed")
            with pytest.raises(errors.InstallError, match="remains registered"):
                linux.uninstall(ctx)

    def test_uninstall_refuses_unproved_process_terminal_states(self, subtests, *, mocker) -> None:
        ctx = platform_context()
        mocker.patch.object(linux.os.path, "exists", return_value=False)
        mocker.patch.object(linux.process, "pids_naming_executable", return_value=[])
        mocker.patch.object(linux.process, "pids_naming_executable", side_effect=[[17], []])
        mocker.patch.object(linux.process, "terminate_executable", return_value=False)
        with (
            subtests.test("termination"),
            pytest.raises(errors.InstallError, match="17 did not exit"),
        ):
            linux.uninstall(ctx)

        mocker.patch.object(linux.process, "pids_naming_executable", side_effect=[[], [19]])
        with (
            subtests.test("residue"),
            pytest.raises(errors.InstallError, match=r"watchdogs remain: \[19\]"),
        ):
            linux.uninstall(ctx)

    def test_uninstall_terminates_each_verified_linux_watchdog(self, *, mocker):
        ctx = platform_context()
        mocker.patch.object(linux.os.path, "exists", return_value=False)
        mocker.patch.object(linux.shutil, "which", return_value=None)
        mocker.patch.object(
            linux.process,
            "pids_naming_executable",
            side_effect=[[17], []],
        )
        terminate = mocker.patch.object(linux.process, "terminate_executable", return_value=True)
        linux.uninstall(ctx)
        terminate.assert_called_once_with(
            17,
            ctx.executable,
            roles={service_runtime.WATCHDOG_MODE},
        )
