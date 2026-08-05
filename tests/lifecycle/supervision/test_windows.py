"""Windows native supervision lifecycle contracts."""

from __future__ import annotations

from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import windows
from codex_responses_proxy.service import runtime as service_runtime
from tests.lifecycle.fixtures import platform_context
from tests.lifecycle.supervision.fixtures import completed as _completed
from tests.lifecycle.supervision.fixtures import temporary_context as _temporary_context
import pytest

ROOT = Path(__file__).resolve().parents[3]


class TestWindowsLifecycle:
    def test_task_executes_the_installed_binary_in_private_watchdog_mode(self):
        ctx = platform_context(windows=True)
        rendered = windows.render_task_xml(ctx)
        assert f"<Command>{ctx.executable}</Command>" in rendered
        assert "<Arguments>--internal-watchdog</Arguments>" in rendered
        assert "python" not in rendered.lower()
        assert ".py" not in rendered

    def test_install_success_and_failure_messages(self, *, mocker):
        with _temporary_context("install_dir", windows=True) as ctx:
            invoked = mocker.patch.object(
                windows.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            )
            windows.install(ctx)
            assert invoked.call_args_list[-1].args[0] == [
                "schtasks",
                "/run",
                "/tn",
                runtime_context.SERVICE_ID,
            ]
            assert Path(windows._xml_path(ctx)).read_text(
                encoding="utf-16"
            ) == windows.render_task_xml(ctx)
            for completed, error in (
                (_completed(returncode=1, stderr=" denied ", stdout="fallback"), "denied"),
                (_completed(returncode=1, stdout=" fallback "), "fallback"),
            ):
                mocker.patch.object(
                    windows.subprocess,
                    "run",
                    side_effect=[_completed(), completed],
                )
                with pytest.raises(errors.InstallError, match=error):
                    windows.install(ctx)

    def test_current_user_and_status(self, *, mocker):
        for env, expected in (
            ({"USERNAME": "tester"}, "tester"),
            ({"USERNAME": "tester", "USERDOMAIN": "ACME"}, r"ACME\tester"),
        ):
            mocker.patch.dict(windows.os.environ, env, clear=True)
            assert windows._current_user() == expected
        for returncode, stdout, expected in (
            (1, "", "absent"),
            (0, "Ready", "installed"),
            (0, "Status: Running", "running"),
        ):
            mocker.patch.object(
                windows.subprocess,
                "run",
                return_value=_completed(returncode=returncode, stdout=stdout),
            )
            assert windows.status(platform_context(windows=True)) == expected

    def test_pid_discovery_and_uninstall(self, *, mocker):
        ctx = platform_context(windows=True)
        inventory = mocker.patch.object(
            windows.process,
            "pids_naming_executable",
            return_value=[12, 15, 18],
        )
        assert windows._running_watchdog_pids(ctx) == [12, 15, 18]
        inventory.assert_called_once_with(ctx.executable, roles={service_runtime.WATCHDOG_MODE})
        invoked = mocker.patch.object(
            windows.subprocess,
            "run",
            side_effect=[_completed(), _completed(returncode=1)],
        )
        mocker.patch.object(windows, "_running_watchdog_pids", return_value=[4242])
        terminate = mocker.patch.object(windows.process, "terminate_executable", return_value=False)

        with pytest.raises(errors.InstallError, match="verified watchdog 4242 did not exit"):
            windows.uninstall(ctx)
        assert invoked.call_args_list[0].args[0][:2] == ["schtasks", "/delete"]
        terminate.assert_called_once_with(
            4242,
            ctx.executable,
            roles={service_runtime.WATCHDOG_MODE},
        )
        mocker.patch.object(
            windows.subprocess,
            "run",
            side_effect=[_completed(), _completed(returncode=1)],
        )
        mocker.patch.object(windows, "_running_watchdog_pids", side_effect=[[4242], []])
        terminate = mocker.patch.object(windows.process, "terminate_executable", return_value=True)
        windows.uninstall(ctx)
        terminate.assert_called_once_with(
            4242,
            ctx.executable,
            roles={service_runtime.WATCHDOG_MODE},
        )

    def test_uninstall_requires_task_deletion_and_absence_proof(self, *, mocker):
        ctx = platform_context(windows=True)
        for results, message in (
            ([_completed(returncode=1, stderr="denied"), _completed()], "delete failed"),
            ([_completed(), _completed(stdout="Ready")], "remains registered"),
        ):
            mocker.patch.object(windows.subprocess, "run", side_effect=results)
            inventory = mocker.patch.object(windows, "_running_watchdog_pids")
            with pytest.raises(errors.InstallError, match=message):
                windows.uninstall(ctx)
            inventory.assert_not_called()
