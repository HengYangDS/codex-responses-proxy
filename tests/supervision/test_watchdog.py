#!/usr/bin/env python3
"""Watchdog availability, spawn, retention, and loop contracts."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.deployment.fixtures import assert_private_log_mode


def load_watchdog(name):
    """Load a fresh watchdog module so tests cannot share mutable globals."""

    spec = importlib.util.spec_from_file_location(
        name,
        ROOT / "codex_responses_proxy" / "supervision" / "watchdog.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWatchdogEntrypoint(unittest.TestCase):
    def test_direct_script_load_bootstraps_package_root(self):
        watchdog_path = ROOT / "codex_responses_proxy" / "supervision" / "watchdog.py"
        probe = (
            "import runpy, sys; "
            f"sys.path.insert(0, {str(watchdog_path.parent)!r}); "
            f"runpy.run_path({str(watchdog_path)!r}, run_name='_watchdog_import_probe_')"
        )
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", probe],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class TestWatchdogLogging(unittest.TestCase):
    def test_watchdog_log_is_bounded_and_redacts_secrets(self):
        watchdog = load_watchdog("responses_proxy_watchdog_for_test")
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "watchdog.log"
            with (
                mock.patch.object(watchdog, "LOG_PATH", str(log_path)),
                mock.patch.object(watchdog, "LOG_MAX_BYTES", 4096),
                mock.patch.object(watchdog, "LOG_BACKUP_COUNT", 0),
            ):
                watchdog._log(
                    "authorization: Bearer super-secret-token encrypted=gAAAA_replay_secret"
                )
                log_path.write_bytes(b"x" * 8192)
                watchdog._log("event=rotation_probe")
            text = log_path.read_text(encoding="utf-8")
            size = log_path.stat().st_size
            mode = log_path.stat().st_mode & 0o777
        self.assertNotIn("super-secret-token", text)
        self.assertNotIn("gAAAA_replay_secret", text)
        self.assertIn("log_retention_discarded_oversized_bytes=8192", text)
        self.assertLessEqual(size, 4096)
        assert_private_log_mode(self, mode)

    def test_watchdog_probe_and_spawn(self):
        watchdog = load_watchdog("responses_proxy_watchdog_behavior")

        with mock.patch.object(watchdog.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = None
            self.assertTrue(watchdog.is_proxy_up())
            connect.side_effect = OSError("offline")
            self.assertFalse(watchdog.is_proxy_up())

        self.assertIn("[truncated]", watchdog._redact_log_message("x" * 2048))

        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "entrypoint.py"
            script.write_text("pass\n", encoding="utf-8")
            with (
                mock.patch.object(watchdog, "SCRIPT", str(script)),
                mock.patch.object(watchdog, "PYTHON", "/portable/python"),
                mock.patch.object(watchdog.os, "name", "posix"),
                mock.patch.object(watchdog.subprocess, "Popen") as popen,
                mock.patch.object(watchdog, "_log"),
            ):
                popen.return_value.pid = 42
                self.assertIs(watchdog.spawn_proxy(), popen.return_value)
                self.assertTrue(popen.call_args.kwargs["start_new_session"])

            with (
                mock.patch.object(watchdog, "SCRIPT", str(script.with_name("missing.py"))),
                mock.patch.object(watchdog, "_log"),
            ):
                self.assertIsNone(watchdog.spawn_proxy())
            with (
                mock.patch.object(watchdog, "SCRIPT", str(script)),
                mock.patch.object(watchdog.os, "name", "nt"),
                mock.patch.object(watchdog.subprocess, "Popen") as popen,
                mock.patch.object(watchdog, "_log"),
            ):
                popen.return_value.pid = 43
                watchdog.spawn_proxy()
                self.assertEqual(
                    popen.call_args.kwargs["creationflags"], watchdog._WINDOWS_DETACH_FLAGS
                )
            with (
                mock.patch.object(watchdog, "SCRIPT", str(script)),
                mock.patch.object(watchdog.subprocess, "Popen", side_effect=OSError("denied")),
                mock.patch.object(watchdog, "_log") as logged,
            ):
                self.assertIsNone(watchdog.spawn_proxy())
                self.assertIn("OSError", logged.call_args.args[0])

    def test_watchdog_rotation_boundaries(self):
        watchdog = load_watchdog("responses_proxy_watchdog_rotation")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "watchdog.log"
            log.write_text("active", encoding="utf-8")
            with (
                mock.patch.object(watchdog, "LOG_MAX_BYTES", 6),
                mock.patch.object(watchdog, "LOG_BACKUP_COUNT", 2),
            ):
                watchdog._rotate_log_if_needed(log, 1)
            self.assertTrue(log.with_name("watchdog.log.1").is_file())
            self.assertEqual(watchdog._rotate_log_if_needed(log.with_name("absent"), 1), 0)

            directory_path = Path(directory) / "not-a-log"
            directory_path.mkdir()
            with self.assertRaisesRegex(OSError, "regular file"):
                watchdog._rotate_log_if_needed(directory_path, 1)

            small = Path(directory) / "small.log"
            small.write_text("x", encoding="utf-8")
            with mock.patch.object(watchdog, "LOG_MAX_BYTES", 100):
                self.assertEqual(watchdog._rotate_log_if_needed(small, 1), 0)

            no_backup = Path(directory) / "no-backup.log"
            no_backup.write_text("xx", encoding="utf-8")
            with (
                mock.patch.object(watchdog, "LOG_MAX_BYTES", 2),
                mock.patch.object(watchdog, "LOG_BACKUP_COUNT", 0),
            ):
                watchdog._rotate_log_if_needed(no_backup, 1)
            self.assertFalse(no_backup.exists())

            rotating = Path(directory) / "rotating.log"
            rotating.write_text("xx", encoding="utf-8")
            rotating.with_name("rotating.log.1").write_text("old", encoding="utf-8")
            with (
                mock.patch.object(watchdog, "LOG_MAX_BYTES", 2),
                mock.patch.object(watchdog, "LOG_BACKUP_COUNT", 2),
            ):
                watchdog._rotate_log_if_needed(rotating, 1)
            self.assertEqual(
                rotating.with_name("rotating.log.2").read_text(encoding="utf-8"), "old"
            )

            with (
                mock.patch.object(watchdog, "LOG_PATH", str(directory_path)),
                mock.patch.object(watchdog, "LOG_MAX_BYTES", 1),
            ):
                watchdog._log("ignored write failure")

    def test_watchdog_loop_is_bounded(self):
        watchdog = load_watchdog("responses_proxy_watchdog_loop")
        with (
            mock.patch.object(watchdog, "is_proxy_up", side_effect=[False, False]),
            mock.patch.object(watchdog, "spawn_proxy") as spawn,
            mock.patch.object(watchdog.time, "sleep") as sleep,
            mock.patch.object(watchdog, "_log"),
        ):
            watchdog.run(max_iterations=1)
        spawn.assert_called_once_with()
        sleep.assert_called_once()

        with (
            mock.patch.object(watchdog, "is_proxy_up", side_effect=[False, True]),
            mock.patch.object(watchdog, "spawn_proxy"),
            mock.patch.object(watchdog.time, "sleep") as sleep,
            mock.patch.object(watchdog, "_log"),
        ):
            watchdog.run(max_iterations=1)
        sleep.assert_called_once()

        with (
            mock.patch.object(watchdog, "is_proxy_up", return_value=True),
            mock.patch.object(watchdog.time, "sleep") as sleep,
            mock.patch.object(watchdog, "_log"),
        ):
            watchdog.run(max_iterations=2)
        sleep.assert_called_once_with(watchdog.CHECK_INTERVAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
