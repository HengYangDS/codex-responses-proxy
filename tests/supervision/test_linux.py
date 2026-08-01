#!/usr/bin/env python3
"""Linux native supervision lifecycle contracts."""

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
from codex_responses_proxy.supervision import linux
from tests.deployment.fixtures import platform_context
from tests.supervision.fixtures import assert_executable_mode as _assert_executable_mode
from tests.supervision.fixtures import completed as _completed
from tests.supervision.fixtures import set_file as _set_file
from tests.supervision.fixtures import temporary_context as _temporary_context


class TestLinuxLifecycle(unittest.TestCase):
    def test_probe_and_install_dispatch(self):
        for executable, output, expected in (
            (None, None, False),
            ("systemctl", _completed(stderr="Failed to connect to bus"), False),
            ("systemctl", _completed(stdout="degraded"), True),
        ):
            with (
                mock.patch.object(linux.shutil, "which", return_value=executable),
                mock.patch.object(linux.subprocess, "run", return_value=output) as invoked,
            ):
                self.assertEqual(linux._has_user_systemd(), expected)
                self.assertEqual(invoked.call_count, int(executable is not None))

        ctx = platform_context()
        for available, target, skipped in (
            (False, "_install_cron", "_install_systemd"),
            (True, "_install_systemd", "_install_cron"),
        ):
            with (
                mock.patch.object(linux, "_has_user_systemd", return_value=available),
                mock.patch.object(linux, target) as called,
                mock.patch.object(linux, skipped) as not_called,
            ):
                linux.install(ctx)
            called.assert_called_once_with(ctx)
            not_called.assert_not_called()

    def test_systemd_install_success_and_failure(self):
        with _temporary_context("home") as ctx:
            unit = Path(linux._unit_path(ctx))
            with (
                mock.patch.dict(linux.os.environ, {"USER": "tester"}),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(), _completed()],
                ) as invoked,
            ):
                linux._install_systemd(ctx)
            self.assertEqual(unit.read_text(encoding="utf-8"), linux.render_unit(ctx))
            self.assertEqual(invoked.call_args_list[-1].args[0][0], "loginctl")

            with (
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(returncode=1, stderr=" denied ")],
                ),
                self.assertRaisesRegex(errors.InstallError, "systemctl enable failed: denied"),
            ):
                linux._install_systemd(ctx)

    def test_cron_install_and_service_removal(self):
        self.assertFalse(issubclass(errors.ManualStartRequired, errors.InstallError))
        with _temporary_context("install_dir") as ctx:
            wrapper = linux._cron_wrapper_path(ctx)
            existing = f"@reboot {wrapper} # {runtime_context.SERVICE_ID}\n@reboot /keep-me\n"
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(stdout=existing), _completed()],
                ) as invoked,
                mock.patch.object(linux.subprocess, "Popen") as popen,
            ):
                linux._install_cron(ctx)
            text = Path(wrapper).read_text(encoding="utf-8")
            self.assertIn('export CODEX_RESPONSES_PROXY_PROXY_PORT="8791"', text)
            _assert_executable_mode(self, Path(wrapper).stat().st_mode & 0o777)
            installed = invoked.call_args_list[1].kwargs["input"]
            self.assertEqual(installed.count(runtime_context.SERVICE_ID), 1)
            self.assertIn("@reboot /keep-me", installed)
            popen.assert_called_once()

            with (
                mock.patch.object(linux.shutil, "which", return_value=None),
                mock.patch.object(linux.subprocess, "Popen") as popen,
                self.assertRaises(errors.ManualStartRequired),
            ):
                linux._install_cron(ctx)
            popen.assert_not_called()
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(stdout=existing), _completed(returncode=1)],
                ),
                self.assertRaises(errors.InstallError),
            ):
                linux._install_cron(ctx)

    def test_uninstall_and_status(self):
        with _temporary_context("home") as ctx:
            unit = Path(linux._unit_path(ctx))
            owned = f"@reboot /owned # {runtime_context.SERVICE_ID}\n@reboot /keep-me\n"
            _set_file(unit, "unit")
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[
                        _completed(),
                        _completed(),
                        _completed(stdout="inactive"),
                        _completed(stdout=owned),
                        _completed(),
                        _completed(stdout="@reboot /keep-me\n"),
                    ],
                ) as invoked,
                mock.patch.object(linux.process, "pids_naming_path", return_value=[]),
            ):
                linux.uninstall(ctx)
            self.assertFalse(unit.exists())
            self.assertEqual(invoked.call_args_list[-2].kwargs["input"], "@reboot /keep-me\n")

            with (
                mock.patch.object(linux.shutil, "which", return_value=None),
                mock.patch.object(linux.subprocess, "run") as invoked,
                mock.patch.object(linux.process, "pids_naming_path", return_value=[]),
            ):
                linux.uninstall(ctx)
            invoked.assert_not_called()

            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    return_value=_completed(stdout="@reboot /keep-me\n"),
                ) as invoked,
                mock.patch.object(linux.process, "pids_naming_path", return_value=[]),
            ):
                linux.uninstall(ctx)
            invoked.assert_called_once()

            for systemd, executable, output, expected in (
                (True, "crontab", "active\n", "running"),
                (True, "crontab", "inactive\n", "installed"),
                (False, "crontab", f"@reboot x # {runtime_context.SERVICE_ID}\n", "installed"),
                (False, "crontab", "@reboot /other\n", "absent"),
                (False, None, "", "absent"),
            ):
                _set_file(unit, "unit" if systemd else None)
                with (
                    mock.patch.object(linux.shutil, "which", return_value=executable),
                    mock.patch.object(
                        linux.subprocess,
                        "run",
                        return_value=_completed(stdout=output),
                    ),
                ):
                    self.assertEqual(linux.status(ctx), expected)

    def test_uninstall_fails_closed_until_systemd_and_cron_are_proven_absent(self):
        with _temporary_context("home") as ctx:
            unit = _set_file(linux._unit_path(ctx), "unit")
            with (
                mock.patch.object(linux.shutil, "which", return_value=None),
                self.assertRaisesRegex(errors.InstallError, "systemctl is unavailable"),
            ):
                linux.uninstall(ctx)
            self.assertTrue(unit.exists())

            owned = f"@reboot /owned # {runtime_context.SERVICE_ID}\n"
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[
                        _completed(returncode=1, stderr="denied"),
                    ],
                ),
                self.assertRaisesRegex(errors.InstallError, "systemctl disable failed"),
            ):
                linux.uninstall(ctx)
            self.assertTrue(unit.exists())

            _set_file(unit, "unit")
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(returncode=1)],
                ),
                self.assertRaisesRegex(errors.InstallError, "daemon-reload failed"),
            ):
                linux.uninstall(ctx)

            _set_file(unit, "unit")
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[_completed(), _completed()],
                ),
                mock.patch.object(linux, "status", return_value="installed"),
                self.assertRaisesRegex(errors.InstallError, "remains registered"),
            ):
                linux.uninstall(ctx)

            _set_file(unit, None)
            with (
                mock.patch.object(linux.shutil, "which", return_value="crontab"),
                mock.patch.object(
                    linux.subprocess,
                    "run",
                    side_effect=[
                        _completed(stdout=owned),
                        _completed(returncode=1, stderr="denied"),
                    ],
                ),
                self.assertRaisesRegex(errors.InstallError, "crontab removal failed"),
            ):
                linux.uninstall(ctx)

    def test_uninstall_terminates_each_verified_linux_watchdog(self):
        ctx = platform_context()
        with (
            mock.patch.object(linux.os.path, "exists", return_value=False),
            mock.patch.object(linux.shutil, "which", return_value=None),
            mock.patch.object(
                linux.process,
                "pids_naming_path",
                side_effect=[[17], []],
            ),
            mock.patch.object(linux.process, "terminate_pid", return_value=True) as terminate,
        ):
            linux.uninstall(ctx)
        terminate.assert_called_once_with(17, expected_path=ctx.watchdog_script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
