#!/usr/bin/env python3
"""Windows native supervision lifecycle contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.supervision import windows
from tests.deployment.fixtures import platform_context
from tests.supervision.fixtures import completed as _completed
from tests.supervision.fixtures import temporary_context as _temporary_context


class TestWindowsLifecycle(unittest.TestCase):
    def test_install_success_and_failure_messages(self):
        with _temporary_context("install_dir") as ctx:
            with mock.patch.object(
                windows.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            ) as invoked:
                windows.install(ctx)
            self.assertEqual(
                invoked.call_args_list[-1].args[0],
                ["schtasks", "/run", "/tn", runtime_context.SERVICE_ID],
            )
            self.assertEqual(
                Path(windows._launcher_path(ctx)).read_text(encoding="utf-8"),
                windows.render_launcher(ctx).replace("\r\n", "\n"),
            )
            self.assertEqual(
                Path(windows._xml_path(ctx)).read_text(encoding="utf-16"),
                windows.render_task_xml(ctx),
            )
            for completed, error in (
                (_completed(returncode=1, stderr=" denied ", stdout="fallback"), "denied"),
                (_completed(returncode=1, stdout=" fallback "), "fallback"),
            ):
                with (
                    mock.patch.object(
                        windows.subprocess,
                        "run",
                        side_effect=[_completed(), completed],
                    ),
                    self.assertRaisesRegex(errors.InstallError, error),
                ):
                    windows.install(ctx)

    def test_current_user_and_status(self):
        for env, expected in (
            ({"USERNAME": "tester"}, "tester"),
            ({"USERNAME": "tester", "USERDOMAIN": "ACME"}, r"ACME\tester"),
        ):
            with mock.patch.dict(windows.os.environ, env, clear=True):
                self.assertEqual(windows._current_user(), expected)
        for returncode, stdout, expected in (
            (1, "", "absent"),
            (0, "Ready", "installed"),
            (0, "Status: Running", "running"),
        ):
            with mock.patch.object(
                windows.subprocess,
                "run",
                return_value=_completed(returncode=returncode, stdout=stdout),
            ):
                self.assertEqual(windows.status(platform_context()), expected)

    def test_pid_discovery_and_uninstall(self):
        ctx = platform_context()
        launcher = windows._launcher_path(ctx)
        watchdog = ctx.watchdog_script
        with mock.patch.object(
            windows.process,
            "pids_naming_path",
            side_effect=[[12, 15], [15, 18]],
        ) as inventory:
            self.assertEqual(windows._running_watchdog_pids(ctx), [12, 15, 18])
        self.assertEqual(
            inventory.call_args_list,
            [mock.call(launcher), mock.call(watchdog)],
        )

        with (
            mock.patch.object(
                windows.subprocess,
                "run",
                side_effect=[_completed(), _completed(returncode=1)],
            ) as invoked,
            mock.patch.object(windows, "_running_watchdog_pids", return_value=[4242]),
            mock.patch.object(
                windows.process, "terminate_pid", side_effect=[False, False]
            ) as terminate,
            self.assertRaisesRegex(errors.InstallError, "verified watchdog 4242 did not exit"),
        ):
            windows.uninstall(ctx)
        self.assertEqual(invoked.call_args_list[0].args[0][:2], ["schtasks", "/delete"])
        self.assertEqual(
            terminate.call_args_list,
            [
                mock.call(4242, expected_path=launcher),
                mock.call(4242, expected_path=watchdog),
            ],
        )

        with (
            mock.patch.object(
                windows.subprocess,
                "run",
                side_effect=[_completed(), _completed(returncode=1)],
            ),
            mock.patch.object(windows, "_running_watchdog_pids", side_effect=[[4242], []]),
            mock.patch.object(windows.process, "terminate_pid", return_value=True) as terminate,
        ):
            windows.uninstall(ctx)
        terminate.assert_called_once_with(4242, expected_path=launcher)

    def test_uninstall_requires_task_deletion_and_absence_proof(self):
        ctx = platform_context()
        for results, message in (
            ([_completed(returncode=1, stderr="denied"), _completed()], "delete failed"),
            ([_completed(), _completed(stdout="Ready")], "remains registered"),
        ):
            with (
                mock.patch.object(windows.subprocess, "run", side_effect=results),
                mock.patch.object(windows, "_running_watchdog_pids") as inventory,
                self.assertRaisesRegex(errors.InstallError, message),
            ):
                windows.uninstall(ctx)
            inventory.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
