#!/usr/bin/env python3
"""Cross-platform service-definition, interpreter, and watchdog contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import common, linux, macos, windows  # noqa: E402
from tests.support.repository_fixtures import (  # noqa: E402
    assert_private_log_mode,
    platform_context,
)


class TestPythonResolution(unittest.TestCase):
    def test_resolves_absolute_existing(self):
        p = common.resolve_python()
        self.assertTrue(os.path.isabs(p))
        self.assertTrue(os.path.exists(p))

    def test_store_stub_detection_noop_off_windows(self):
        # Off Windows this is always False regardless of path.
        if os.name != "nt":
            self.assertFalse(common._is_windows_store_stub(r"C:\x\WindowsApps\python.exe"))


class TestMacosPlist(unittest.TestCase):
    def test_plist_has_keepalive_and_absolute_python(self):
        xml = macos.render_plist(platform_context())
        self.assertIn("<key>KeepAlive</key>", xml)
        self.assertIn("<true/>", xml)
        self.assertIn("/usr/bin/python3.12", xml)
        self.assertIn("com.user.codex-dmx-watchdog", xml)
        self.assertIn("DMX_PROXY_PORT", xml)
        self.assertIn("8791", xml)
        self.assertIn("DMX_PROXY_LOG_MAX_BYTES", xml)
        self.assertIn(str(common.DEFAULT_PROXY_LOG_MAX_BYTES), xml)
        self.assertIn("DMX_WATCHDOG_LOG_BACKUP_COUNT", xml)
        self.assertIn("<string>/dev/null</string>", xml)
        self.assertNotIn("dmx-watchdog.out.log", xml)
        self.assertNotIn("dmx-watchdog.err.log", xml)

    def test_plist_is_wellformed_xml(self):
        import xml.dom.minidom as minidom

        minidom.parseString(macos.render_plist(platform_context()))  # raises if malformed


class TestLinuxUnit(unittest.TestCase):
    def test_unit_restart_always_and_absolute_paths(self):
        unit = linux.render_unit(platform_context())
        self.assertIn("Restart=always", unit)
        self.assertIn("RestartSec=3", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn("ExecStart=/usr/bin/python3.12", unit)
        self.assertIn("Environment=DMX_PROXY_PORT=8791", unit)
        self.assertIn(
            f"Environment=DMX_PROXY_LOG_MAX_BYTES={common.DEFAULT_PROXY_LOG_MAX_BYTES}",
            unit,
        )
        self.assertIn(
            f"Environment=DMX_WATCHDOG_LOG_BACKUP_COUNT={common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}",
            unit,
        )

    def test_unit_no_multiuser_target(self):
        # user units must target default.target, not multi-user.target
        self.assertNotIn("multi-user.target", linux.render_unit(platform_context()))

    def test_manual_start_required_is_distinct_persistence_failure(self):
        # A minimal host (no systemd bus, no crontab) cannot satisfy durable
        # installation and must fail without being confused with input errors.
        self.assertTrue(issubclass(common.ManualStartRequired, Exception))
        self.assertFalse(issubclass(common.ManualStartRequired, common.InstallError))


class TestWindowsTask(unittest.TestCase):
    def test_task_xml_wellformed_and_key_settings(self):
        import xml.dom.minidom as minidom

        xml = windows.render_task_xml(platform_context())
        minidom.parseString(xml)  # raises if malformed
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", xml)  # no 72h kill
        self.assertIn("<LogonTrigger>", xml)
        self.assertIn("<RestartOnFailure>", xml)
        self.assertIn("<LogonType>InteractiveToken</LogonType>", xml)  # no admin
        self.assertIn("<RunLevel>LeastPrivilege</RunLevel>", xml)

    def test_time_trigger_repeats_so_a_dead_watchdog_is_relaunched(self):
        # RestartOnFailure only reacts to a failed task *launch*, not to the
        # launched watchdog being killed later (confirmed absent after 3x the
        # interval on a real host). A LogonTrigger <Repetition> is not enough
        # either: its repetition only arms at an actual logon, so a mid-session
        # death is not healed (also confirmed on a real host). A repeating
        # TimeTrigger with a past StartBoundary fires regardless of logon; paired
        # with IgnoreNew it re-launches the watchdog when the process itself dies.
        xml = windows.render_task_xml(platform_context())
        self.assertIn("<TimeTrigger>", xml)
        self.assertIn(f"<StartBoundary>{windows._SELF_HEAL_START_BOUNDARY}</StartBoundary>", xml)
        self.assertIn("<Repetition>", xml)
        self.assertIn("<Interval>PT1M</Interval>", xml)
        self.assertIn("<StopAtDurationEnd>false</StopAtDurationEnd>", xml)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", xml)

    def test_task_launches_windowless_pythonw_without_a_console_wrapper(self):
        # A cmd.exe /c wrapper keeps a visible console for the whole watchdog
        # lifetime; run the .pyw bootstrap directly with the windowless
        # interpreter (pythonw.exe when present) instead.
        ctx = platform_context()
        xml = windows.render_task_xml(ctx)
        expected_command = windows.common.windows_pythonw(ctx.python)
        self.assertIn(f"<Command>{expected_command}</Command>", xml)
        self.assertNotIn("cmd.exe", xml.lower())
        self.assertNotIn("comspec", xml.lower())
        self.assertNotIn("run-watchdog.cmd", xml)

    def test_task_references_generated_launcher(self):
        self.assertIn("run-watchdog.pyw", windows.render_task_xml(platform_context()))

    def test_task_runs_generated_launcher_with_proxy_environment(self):
        ctx = platform_context(port=8801, upstream="https://alternate.example")
        xml = windows.render_task_xml(ctx)
        launcher = windows.render_launcher(ctx)
        self.assertIn("run-watchdog.pyw", xml)
        self.assertNotIn('Arguments>"/home/tester/.codex/dmx-proxy/watchdog/watchdog.py"', xml)
        self.assertIn("'DMX_PROXY_PORT'] = '8801'", launcher)
        self.assertIn("'DMX_UPSTREAM'] = 'https://alternate.example'", launcher)
        self.assertIn("'DMX_PROXY_PYTHON'] = '/usr/bin/python3.12'", launcher)
        self.assertIn(
            "'DMX_PROXY_SCRIPT'] = '/home/tester/.codex/dmx-proxy/proxy/dmx_responses_proxy.py'",
            launcher,
        )
        self.assertIn(
            f"'DMX_PROXY_LOG_MAX_BYTES'] = '{common.DEFAULT_PROXY_LOG_MAX_BYTES}'",
            launcher,
        )
        self.assertIn(
            f"'DMX_WATCHDOG_LOG_BACKUP_COUNT'] = '{common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}'",
            launcher,
        )
        # The bootstrap runs the installed watchdog as __main__.
        self.assertIn(
            "runpy.run_path('/home/tester/.codex/dmx-proxy/watchdog/watchdog.py', run_name='__main__')",
            launcher,
        )

    def test_uninstall_terminates_only_this_installs_watchdog(self):
        # schtasks /delete removes the task definition but not a running instance;
        # uninstall must end this install's watchdog (matched by its own paths) so
        # it cannot immediately respawn the proxy after the caller stops it.
        ctx = platform_context()
        seen = {}

        def fake_run(cmd, *args, **kwargs):
            if cmd[:2] == ["schtasks", "/delete"]:
                seen["deleted"] = True
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:1] == ["powershell"]:
                launcher = os.path.abspath(windows._launcher_path(ctx))
                unrelated = "/usr/bin/python3.12 /some/other/script.py"
                out = f"4242\t{windows.common.windows_pythonw(ctx.python)} {launcher}\n9\t{unrelated}\n"
                return subprocess.CompletedProcess(cmd, 0, out, "")
            raise AssertionError(f"unexpected subprocess call: {cmd}")

        terminated = []
        with (
            mock.patch.object(windows.subprocess, "run", side_effect=fake_run),
            mock.patch.object(windows.common, "terminate_pid", side_effect=terminated.append),
        ):
            windows.uninstall(ctx)
        self.assertTrue(seen.get("deleted"))
        self.assertEqual(terminated, [4242])  # only the matched watchdog, not pid 9


class TestWatchdogLogging(unittest.TestCase):
    def _watchdog_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dmx_watchdog_for_test",
            Path(ROOT, "watchdog", "watchdog.py"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load watchdog/watchdog.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_watchdog_log_is_bounded_and_redacts_secret_shaped_values(self):
        watchdog = self._watchdog_module()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "watchdog.log"
            old_path = watchdog.LOG_PATH
            old_max = watchdog.LOG_MAX_BYTES
            old_backups = watchdog.LOG_BACKUP_COUNT
            watchdog.LOG_PATH = str(log_path)
            watchdog.LOG_MAX_BYTES = 4096
            watchdog.LOG_BACKUP_COUNT = 0
            try:
                watchdog._log(
                    "authorization: Bearer super-secret-token encrypted=gAAAA_replay_secret"
                )
                log_path.write_bytes(b"x" * 8192)
                watchdog._log("event=rotation_probe")
            finally:
                watchdog.LOG_PATH = old_path
                watchdog.LOG_MAX_BYTES = old_max
                watchdog.LOG_BACKUP_COUNT = old_backups

            text = log_path.read_text(encoding="utf-8")
            size = log_path.stat().st_size
            mode = log_path.stat().st_mode & 0o777
        self.assertNotIn("super-secret-token", text)
        self.assertNotIn("gAAAA_replay_secret", text)
        self.assertIn("log_retention_discarded_oversized_bytes=8192", text)
        self.assertLessEqual(size, 4096)
        assert_private_log_mode(self, mode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
