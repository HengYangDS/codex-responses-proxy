#!/usr/bin/env python3
"""Interpreter resolution and exact process-identity contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.supervision import process
from codex_responses_proxy.supervision import python as python_runtime
from tests.deployment.fixtures import platform_context
from tests.supervision.fixtures import completed as _completed


class TestPythonResolution(unittest.TestCase):
    def test_resolution_and_rejection_boundaries(self):
        resolved = python_runtime.resolve_python()
        self.assertTrue(os.path.isabs(resolved))
        self.assertTrue(os.path.exists(resolved))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "python"
            regular.write_text("#!/bin/sh\n", encoding="utf-8")
            regular.chmod(0o600)
            for executable in ("relative-python", str(root / "missing"), str(root), str(regular)):
                with (
                    mock.patch.object(python_runtime.sys, "executable", executable),
                    mock.patch.object(python_runtime.shutil, "which", return_value=None),
                    mock.patch.object(
                        python_runtime,
                        "is_windows_store_stub",
                        return_value=False,
                    ),
                    self.assertRaises(errors.InstallError),
                ):
                    python_runtime.resolve_python()

        stub = r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe"
        with (
            mock.patch.object(python_runtime.sys, "executable", stub),
            mock.patch.object(python_runtime.os, "name", "nt"),
            mock.patch.object(python_runtime, "is_windows_store_stub", return_value=True),
            mock.patch.object(python_runtime.shutil, "which", return_value=None),
            self.assertRaises(errors.InstallError),
        ):
            python_runtime.resolve_python()

    def test_interpreter_fallbacks(self):
        safe = "/absolute/python"
        for name, which_values, launcher_values in (
            ("nt", ["launcher", "launcher2"], [OSError(), safe]),
            ("nt", ["launcher", "launcher2"], ["unsafe", safe]),
            ("nt", [None, None, safe], None),
            ("posix", [None, safe], None),
        ):
            with (
                mock.patch.object(python_runtime.sys, "executable", ""),
                mock.patch.object(python_runtime.os, "name", name),
                mock.patch.object(python_runtime.shutil, "which", side_effect=which_values),
                mock.patch.object(
                    python_runtime.subprocess,
                    "check_output",
                    side_effect=launcher_values,
                ),
                mock.patch.object(
                    python_runtime, "_service_safe", side_effect=lambda path: path == safe
                ),
            ):
                self.assertEqual(python_runtime.resolve_python(), safe)

    def test_store_stub_and_pythonw_boundaries(self):
        self.assertFalse(
            os.name != "nt" and python_runtime.is_windows_store_stub(r"C:\WindowsApps\python.exe")
        )
        with (
            mock.patch.object(python_runtime.os, "name", "nt"),
            mock.patch.object(python_runtime.os.path, "getsize", side_effect=(512, OSError())),
        ):
            self.assertTrue(python_runtime.is_windows_store_stub(r"C:\WindowsApps\python.exe"))
            self.assertTrue(python_runtime.is_windows_store_stub(r"C:\WindowsApps\python.exe"))
        python = r"C:\Python\python.exe"
        for exists, expected in (
            (True, os.path.join(os.path.dirname(python), "pythonw.exe")),
            (False, python),
        ):
            with (
                mock.patch.object(python_runtime.os, "name", "nt"),
                mock.patch.object(python_runtime.os.path, "exists", return_value=exists),
            ):
                self.assertEqual(python_runtime.windows_pythonw(python), expected)
        self.assertEqual(python_runtime.windows_pythonw("/usr/bin/python3"), "/usr/bin/python3")


class TestProcessIdentity(unittest.TestCase):
    def test_process_discovery_is_platform_specific_and_fail_closed(self):
        for name, output, expected in (
            (
                "nt",
                "TCP 127.0.0.1:8791 0.0.0.0:0 LISTENING 123\n"
                "TCP 127.0.0.1:8792 0.0.0.0:0 LISTENING 456\n",
                [123],
            ),
            ("posix", "123\ninvalid\n456\n", [123, 456]),
        ):
            with (
                mock.patch.object(process.os, "name", name),
                mock.patch.object(process.subprocess, "run", return_value=mock.Mock(stdout=output)),
            ):
                self.assertEqual(process.listener_pids(8791), expected)
        with mock.patch.object(process.subprocess, "run", side_effect=OSError):
            self.assertEqual(process.listener_pids(8791), [])
            self.assertEqual(process.process_command(123), "")

    def test_process_inventory_parses_each_platform_and_fails_closed(self):
        for name, output, expected in (
            (
                "posix",
                "  7 python /proxy.py\ninvalid\n8\n 9 python /other.py\n",
                [(7, "python /proxy.py"), (9, "python /other.py")],
            ),
            (
                "nt",
                "7\tpython C:\\proxy.py\ninvalid\n8\t\n9\tpython C:\\other.py\n",
                [(7, r"python C:\proxy.py"), (9, r"python C:\other.py")],
            ),
        ):
            with (
                mock.patch.object(process.os, "name", name),
                mock.patch.object(
                    process.subprocess, "run", return_value=_completed(stdout=output)
                ),
            ):
                self.assertEqual(process._process_inventory(), expected)
        with mock.patch.object(process.subprocess, "run", side_effect=OSError):
            self.assertEqual(process._process_inventory(), [])

        with (
            mock.patch.object(
                process,
                "_process_inventory",
                return_value=[
                    (7, "python /installed/watchdog.py.backup"),
                    (8, 'python "/installed/watchdog.py"'),
                    (9, "powershell -Command 'Write-Output /installed/watchdog.py'"),
                    (10, "powershell -Command Write-Output /installed/watchdog.py"),
                    (11, "python -c print /installed/watchdog.py"),
                ],
            ),
            mock.patch.object(
                process,
                "process_argv",
                side_effect=[
                    ["python", "/installed/watchdog.py.backup"],
                    ["python", "/installed/watchdog.py"],
                    ["powershell", "-Command", "Write-Output /installed/watchdog.py"],
                    ["powershell", "-Command", "Write-Output", "/installed/watchdog.py"],
                    ["python", "-c", "print", "/installed/watchdog.py"],
                ],
            ),
        ):
            self.assertEqual(process.pids_naming_path("/installed/watchdog.py"), [8])

    def test_exact_resolved_argument_identity(self):
        ctx = platform_context()
        script = os.path.abspath(ctx.proxy_script)
        parent = os.path.dirname(script)
        equivalent = os.path.join(parent, "..", "listener", "entrypoint.py")
        cases = (
            (f"python {script}", True),
            (f'python "{script}" --handoff-child', True),
            (f"python {equivalent}", True),
            (f"python {script}.backup", False),
            (f"python --note={script}", False),
            (f"python {script}-suffix", False),
            (f"powershell -Command 'Write-Output {script}'", False),
            (f"powershell -Command Write-Output {script}", False),
            (f"python -c print {script}", False),
            (f"python /other.py {script}", False),
            (f"bash {script}", False),
            (f"notpython {script}", False),
            (f"python-wrapper {script}", False),
            (f"python123 {script}", False),
            (f"python.3 {script}", False),
            (f"python3. {script}", False),
            (script, False),
            ('python "unterminated', False),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(process.command_names_path(command, script), expected)

        with (
            mock.patch.object(process, "listener_pids", return_value=[7, 8]),
            mock.patch.object(
                process,
                "process_argv",
                side_effect=[["python", f"{script}.backup"], ["python", script]],
            ),
        ):
            self.assertEqual(process.verified_proxy_listener_pids(ctx), [8])
        legacy = "/home/tester/.codex/responses-proxy/proxy/dmx_responses_proxy.py"
        with (
            mock.patch.object(process, "listener_pids", return_value=[7, 8]),
            mock.patch.object(
                process,
                "process_argv",
                side_effect=[["python", legacy], ["python", script]],
            ),
        ):
            self.assertEqual(process.verified_listener_pids(ctx.port, legacy), [7])
        with (
            mock.patch.object(process.os, "name", "nt"),
            mock.patch.object(process.ctypes, "windll", None, create=True),
        ):
            self.assertEqual(process.command_argv("native command"), [])

    def test_windows_argv_uses_native_parser(self):
        expected = [r"C:\Python\pythonw.exe", r"C:\DMX Proxy\run-watchdog.pyw"]

        class NativeParser:
            argtypes = None
            restype = None

            def __call__(self, command, count):
                self.command = command
                count._obj.value = len(expected)
                return expected

        class LocalFree:
            argtypes = None
            restype = None

            def __call__(self, value):
                self.value = value

        parser = NativeParser()
        local_free = LocalFree()
        windll = mock.Mock(
            shell32=mock.Mock(CommandLineToArgvW=parser),
            kernel32=mock.Mock(LocalFree=local_free),
        )
        with (
            mock.patch.object(process.os, "name", "nt"),
            mock.patch.object(process.ctypes, "windll", windll, create=True),
        ):
            self.assertEqual(process.command_argv("native command"), expected)
        self.assertEqual(parser.command, "native command")
        self.assertIs(local_free.value, expected)

        failing_parser = mock.Mock(return_value=None)
        failing_parser.argtypes = None
        failing_parser.restype = None
        failing_windll = mock.Mock(
            shell32=mock.Mock(CommandLineToArgvW=failing_parser),
            kernel32=mock.Mock(LocalFree=local_free),
        )
        with (
            mock.patch.object(process.os, "name", "nt"),
            mock.patch.object(process.ctypes, "windll", failing_windll, create=True),
        ):
            self.assertEqual(process.command_argv("native command"), [])

    def test_process_command_and_windows_executable_suffix(self):
        with (
            mock.patch.object(process.sys, "platform", "darwin"),
            mock.patch.object(
                process,
                "_darwin_process_argv",
                return_value=[
                    "/usr/bin/python3",
                    "/Users/tester/Library/Application Support/proxy.py",
                ],
            ) as invoked,
        ):
            self.assertEqual(
                process.process_argv(17),
                [
                    "/usr/bin/python3",
                    "/Users/tester/Library/Application Support/proxy.py",
                ],
            )
        invoked.assert_called_once_with(17)

        with tempfile.TemporaryDirectory(prefix="responses proxy argv ") as directory:
            script = Path(directory, "listener entrypoint.py")
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            child = subprocess.Popen([sys.executable, str(script)])
            try:
                with mock.patch.object(process.sys, "platform", "darwin"):
                    argv = process.process_argv(child.pid)
                self.assertEqual(argv, [sys.executable, str(script)])
                self.assertTrue(process.pid_names_path(child.pid, str(script)))
                self.assertIn(child.pid, process.pids_naming_path(str(script)))
            finally:
                child.terminate()
                child.wait(timeout=5)

        script = "/Users/tester/Library/Application Support/proxy.py"
        with (
            mock.patch.object(process, "listener_pids", return_value=[17]),
            mock.patch.object(
                process,
                "process_argv",
                return_value=["/usr/bin/python3", script],
            ),
        ):
            self.assertEqual(process.verified_listener_pids(8792, script), [17])

        with (
            mock.patch.object(process.os, "name", "nt"),
            mock.patch.object(
                process.subprocess,
                "run",
                return_value=_completed(stdout="pythonw.exe C:\\installed\\proxy.py\n"),
            ) as invoked,
        ):
            self.assertEqual(process.process_command(17), "pythonw.exe C:\\installed\\proxy.py")
        self.assertEqual(invoked.call_args.args[0][:2], ["powershell", "-NoProfile"])

        with (
            mock.patch.object(process.os, "name", "nt"),
            mock.patch.object(
                process,
                "command_argv",
                return_value=["pythonw.exe", r"C:\installed\proxy.py"],
            ),
        ):
            self.assertTrue(
                process.command_names_path(
                    r"pythonw.exe C:\installed\proxy.py", r"C:\installed\proxy.py"
                )
            )

    def test_termination_rechecks_identity_and_proves_exit(self):
        for name, command in (
            ("nt", ["taskkill", "/pid", "123", "/f"]),
            ("posix", ["kill", "-TERM", "123"]),
        ):
            with self.subTest(platform=name):
                with (
                    mock.patch.object(process.os, "name", name),
                    mock.patch.object(process, "pid_names_path", return_value=False),
                    mock.patch.object(process.subprocess, "run") as invoked,
                ):
                    self.assertFalse(process.terminate_pid(123, expected_path="/proxy.py"))
                invoked.assert_not_called()

                with (
                    mock.patch.object(process.os, "name", name),
                    mock.patch.object(process, "pid_names_path", side_effect=[True, True, False]),
                    mock.patch.object(
                        process.subprocess,
                        "run",
                        return_value=_completed(returncode=0),
                    ) as invoked,
                    mock.patch.object(process.time, "monotonic", side_effect=[0.0, 0.1]),
                    mock.patch.object(process.time, "sleep") as sleep,
                ):
                    self.assertTrue(
                        process.terminate_pid(123, expected_path="/proxy.py", timeout_seconds=1.0)
                    )
                invoked.assert_called_once_with(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                sleep.assert_called_once_with(0.05)

    def test_termination_fails_on_signal_error_or_post_kill_timeout(self):
        with (
            mock.patch.object(process, "pid_names_path", return_value=True),
            mock.patch.object(
                process.subprocess,
                "run",
                return_value=_completed(returncode=1),
            ),
        ):
            self.assertFalse(process.terminate_pid(123, expected_path="/proxy.py"))

        with (
            mock.patch.object(process, "pid_names_path", return_value=True),
            mock.patch.object(
                process.subprocess,
                "run",
                return_value=_completed(returncode=0),
            ),
            mock.patch.object(process.time, "monotonic", side_effect=[0.0, 0.1, 1.1]),
            mock.patch.object(process.time, "sleep") as sleep,
        ):
            self.assertFalse(
                process.terminate_pid(123, expected_path="/proxy.py", timeout_seconds=1.0)
            )
        sleep.assert_called_once_with(0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
