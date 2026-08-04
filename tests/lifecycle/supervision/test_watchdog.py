"""Watchdog availability, spawn, retention, and loop contracts."""

from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

from codex_responses_proxy.lifecycle.supervision import watchdog
from tests.lifecycle.fixtures import assert_private_log_mode
import pytest


def load_watchdog():
    """Load a fresh watchdog module so tests cannot share mutable globals."""

    return importlib.reload(watchdog)


class TestWatchdogEntrypoint:
    def test_installed_watchdog_module_imports_without_checkout_context(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import codex_responses_proxy.lifecycle.supervision.watchdog",
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )
        assert completed.returncode == 0, completed.stderr


class TestWatchdogLogging:
    def test_watchdog_log_is_bounded_and_redacts_secrets(self, *, mocker):
        watchdog = load_watchdog()
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "watchdog.log"
            mocker.patch.object(watchdog, "LOG_PATH", str(log_path))
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 4096)
            mocker.patch.object(watchdog, "LOG_BACKUP_COUNT", 0)
            watchdog._log("authorization: Bearer super-secret-token encrypted=gAAAA_replay_secret")
            log_path.write_bytes(b"x" * 8192)
            watchdog._log("event=rotation_probe")
            text = log_path.read_text(encoding="utf-8")
            size = log_path.stat().st_size
            mode = log_path.stat().st_mode & 0o777
        assert "super-secret-token" not in text
        assert "gAAAA_replay_secret" not in text
        assert "log_retention_discarded_oversized_bytes=8192" in text
        assert size <= 4096
        assert_private_log_mode(self, mode)

    def test_watchdog_probe_and_spawn(self, *, mocker):
        watchdog = load_watchdog()
        connect = mocker.patch.object(watchdog.socket, "create_connection")
        connect.return_value.__enter__.return_value = None
        assert watchdog.is_proxy_up()
        connect.side_effect = OSError("offline")
        assert not watchdog.is_proxy_up()

        assert "[truncated]" in watchdog._redact_log_message("x" * 2048)

        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex-responses-proxy"
            executable.write_text("native fixture\n", encoding="utf-8")
            mocker.patch.object(watchdog, "EXECUTABLE", str(executable))
            mocker.patch.object(watchdog.os, "name", "posix")
            popen = mocker.patch.object(watchdog.subprocess, "Popen")
            mocker.patch.object(watchdog, "_log")
            popen.return_value.pid = 42
            assert watchdog.spawn_proxy() is popen.return_value
            assert popen.call_args.args[0] == [str(executable), watchdog.LISTENER_MODE]
            assert popen.call_args.kwargs["start_new_session"]
            mocker.patch.object(
                watchdog,
                "EXECUTABLE",
                str(executable.with_name("missing-native-executable")),
            )
            mocker.patch.object(watchdog, "_log")
            assert watchdog.spawn_proxy() is None
            mocker.patch.object(watchdog, "EXECUTABLE", str(executable))
            mocker.patch.object(watchdog.os, "name", "nt")
            popen = mocker.patch.object(watchdog.subprocess, "Popen")
            mocker.patch.object(watchdog, "_log")
            popen.return_value.pid = 43
            watchdog.spawn_proxy()
            assert popen.call_args.kwargs["creationflags"] == watchdog._WINDOWS_DETACH_FLAGS
            mocker.patch.object(watchdog, "EXECUTABLE", str(executable))
            mocker.patch.object(watchdog.subprocess, "Popen", side_effect=OSError("denied"))
            logged = mocker.patch.object(watchdog, "_log")
            assert watchdog.spawn_proxy() is None
            assert "OSError" in logged.call_args.args[0]

    def test_watchdog_rotation_boundaries(self, *, mocker):
        watchdog = load_watchdog()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "watchdog.log"
            log.write_text("active", encoding="utf-8")
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 6)
            mocker.patch.object(watchdog, "LOG_BACKUP_COUNT", 2)
            watchdog._rotate_log_if_needed(log, 1)
            assert log.with_name("watchdog.log.1").is_file()
            assert watchdog._rotate_log_if_needed(log.with_name("absent"), 1) == 0

            directory_path = Path(directory) / "not-a-log"
            directory_path.mkdir()
            with pytest.raises(OSError, match="regular file"):
                watchdog._rotate_log_if_needed(directory_path, 1)

            small = Path(directory) / "small.log"
            small.write_text("x", encoding="utf-8")
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 100)
            assert watchdog._rotate_log_if_needed(small, 1) == 0

            no_backup = Path(directory) / "no-backup.log"
            no_backup.write_text("xx", encoding="utf-8")
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 2)
            mocker.patch.object(watchdog, "LOG_BACKUP_COUNT", 0)
            watchdog._rotate_log_if_needed(no_backup, 1)
            assert not no_backup.exists()

            rotating = Path(directory) / "rotating.log"
            rotating.write_text("xx", encoding="utf-8")
            rotating.with_name("rotating.log.1").write_text("old", encoding="utf-8")
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 2)
            mocker.patch.object(watchdog, "LOG_BACKUP_COUNT", 2)
            watchdog._rotate_log_if_needed(rotating, 1)
            assert rotating.with_name("rotating.log.2").read_text(encoding="utf-8") == "old"
            mocker.patch.object(watchdog, "LOG_PATH", str(directory_path))
            mocker.patch.object(watchdog, "LOG_MAX_BYTES", 1)
            watchdog._log("ignored write failure")

    def test_watchdog_loop_is_bounded(self, *, mocker):
        watchdog = load_watchdog()
        mocker.patch.object(watchdog, "is_proxy_up", side_effect=[False, False])
        spawn = mocker.patch.object(watchdog, "spawn_proxy")
        sleep = mocker.patch.object(watchdog.time, "sleep")
        mocker.patch.object(watchdog, "_log")
        watchdog.run(max_iterations=1)
        spawn.assert_called_once_with()
        sleep.assert_called_once()
        mocker.patch.object(watchdog, "is_proxy_up", side_effect=[False, True])
        mocker.patch.object(watchdog, "spawn_proxy")
        sleep = mocker.patch.object(watchdog.time, "sleep")
        mocker.patch.object(watchdog, "_log")
        watchdog.run(max_iterations=1)
        sleep.assert_called_once()
        mocker.patch.object(watchdog, "is_proxy_up", return_value=True)
        sleep = mocker.patch.object(watchdog.time, "sleep")
        mocker.patch.object(watchdog, "_log")
        watchdog.run(max_iterations=2)
        sleep.assert_called_once_with(watchdog.CHECK_INTERVAL)
