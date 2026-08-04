"""Interpreter resolution and exact process-identity contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from codex_responses_proxy.lifecycle.supervision import process
from tests.lifecycle.fixtures import platform_context
from tests.lifecycle.supervision.fixtures import completed as _completed

ROOT = Path(__file__).resolve().parents[3]


class TestProcessIdentity:
    def test_process_discovery_is_platform_specific_and_fail_closed(self, *, mocker):
        loopback = ".".join(("127", "0", "0", "1"))
        wildcard = ".".join(("0", "0", "0", "0"))
        for name, output, expected in (
            (
                "nt",
                f"TCP {loopback}:8791 {wildcard}:0 LISTENING 123\n"
                f"TCP {loopback}:8792 {wildcard}:0 LISTENING 456\n",
                [123],
            ),
            ("posix", "123\ninvalid\n456\n", [123, 456]),
        ):
            mocker.patch.object(process.os, "name", name)
            mocker.patch.object(process.subprocess, "run", return_value=mocker.Mock(stdout=output))
            assert process.listener_pids(8791) == expected
        mocker.patch.object(process.subprocess, "run", side_effect=OSError)
        assert process.listener_pids(8791) == []
        assert process.process_command(123) == ""

    def test_process_inventory_parses_each_platform_and_fails_closed(self, *, mocker):
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
            mocker.patch.object(process.os, "name", name)
            mocker.patch.object(process.subprocess, "run", return_value=_completed(stdout=output))
            assert process._process_inventory() == expected
        mocker.patch.object(process.subprocess, "run", side_effect=OSError)
        assert process._process_inventory() == []
        mocker.patch.object(
            process,
            "_process_inventory",
            return_value=[
                (7, "python /installed/watchdog.py.backup"),
                (8, 'python "/installed/watchdog.py"'),
                (9, "powershell -Command 'Write-Output /installed/watchdog.py'"),
                (10, "powershell -Command Write-Output /installed/watchdog.py"),
                (11, "python -c print /installed/watchdog.py"),
            ],
        )
        mocker.patch.object(
            process,
            "process_argv",
            side_effect=[
                ["python", "/installed/watchdog.py.backup"],
                ["python", "/installed/watchdog.py"],
                ["powershell", "-Command", "Write-Output /installed/watchdog.py"],
                ["powershell", "-Command", "Write-Output", "/installed/watchdog.py"],
                ["python", "-c", "print", "/installed/watchdog.py"],
            ],
        )
        assert process.pids_naming_path("/installed/watchdog.py") == [8]

    def test_native_and_retired_script_identity_are_distinct(self, subtests, *, mocker):
        ctx = platform_context()
        executable = os.path.abspath(ctx.executable)
        listener = "--internal-listener"
        handoff_child = "--internal-handoff-child"
        cases = (
            ([executable, listener], True),
            ([executable, handoff_child], True),
            ([executable, "--internal-watchdog"], False),
            ([f"{executable}.backup", listener], False),
            ([executable], False),
            ([], False),
        )
        for argv, expected in cases:
            with subtests.test(argv=argv):
                assert (
                    process.argv_names_executable(argv, executable, roles={listener, handoff_child})
                    == expected
                )
        mocker.patch.object(process, "listener_pids", return_value=[7, 8])
        mocker.patch.object(
            process,
            "process_argv",
            side_effect=[
                [executable, "--internal-watchdog"],
                [executable, listener],
            ],
        )
        assert process.verified_proxy_listener_pids(ctx) == [8]
        legacy = str(Path("/") / "fixture-home" / "retired" / "listener.py")
        mocker.patch.object(process, "listener_pids", return_value=[7, 8])
        mocker.patch.object(
            process,
            "process_argv",
            side_effect=[["python", legacy], [executable, listener]],
        )
        assert process.verified_listener_pids(ctx.port, legacy) == [7]
        mocker.patch.object(process.os, "name", "nt")
        mocker.patch.object(process.ctypes, "windll", None, create=True)
        assert process.command_argv("native command") == []

    def test_windows_argv_uses_native_parser(self, *, mocker):
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
        windll = mocker.Mock(
            shell32=mocker.Mock(CommandLineToArgvW=parser),
            kernel32=mocker.Mock(LocalFree=local_free),
        )
        mocker.patch.object(process.os, "name", "nt")
        mocker.patch.object(process.ctypes, "windll", windll, create=True)
        assert process.command_argv("native command") == expected
        assert parser.command == "native command"
        assert local_free.value is expected

        failing_parser = mocker.Mock(return_value=None)
        failing_parser.argtypes = None
        failing_parser.restype = None
        failing_windll = mocker.Mock(
            shell32=mocker.Mock(CommandLineToArgvW=failing_parser),
            kernel32=mocker.Mock(LocalFree=local_free),
        )
        mocker.patch.object(process.os, "name", "nt")
        mocker.patch.object(process.ctypes, "windll", failing_windll, create=True)
        assert process.command_argv("native command") == []

    def test_process_command_and_windows_executable_suffix(self, *, mocker):
        script = str(Path("/") / "fixture-home" / "Library" / "proxy.py")
        mocker.patch.object(process.sys, "platform", "darwin")
        invoked = mocker.patch.object(
            process,
            "_darwin_process_argv",
            return_value=[
                "/usr/bin/python3",
                script,
            ],
        )
        assert process.process_argv(17) == [
            "/usr/bin/python3",
            script,
        ]
        invoked.assert_called_once_with(17)
        mocker.stopall()

        if sys.platform == "darwin":
            with tempfile.TemporaryDirectory(prefix="responses proxy argv ") as directory:
                fixture = Path(directory, "listener entrypoint.py")
                fixture.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
                child = subprocess.Popen([sys.executable, str(fixture)])
                try:
                    argv = process.process_argv(child.pid)
                    assert argv == [sys.executable, str(fixture)]
                    assert process.pid_names_path(child.pid, str(fixture))
                    assert child.pid in process.pids_naming_path(str(fixture))
                finally:
                    child.terminate()
                    child.wait(timeout=5)

        mocker.patch.object(process, "listener_pids", return_value=[17])
        mocker.patch.object(
            process,
            "process_argv",
            return_value=["/usr/bin/python3", script],
        )
        assert process.verified_listener_pids(8792, script) == [17]
        mocker.patch.object(process.os, "name", "nt")
        invoked = mocker.patch.object(
            process.subprocess,
            "run",
            return_value=_completed(stdout="pythonw.exe C:\\installed\\proxy.py\n"),
        )
        assert process.process_command(17) == "pythonw.exe C:\\installed\\proxy.py"
        assert invoked.call_args.args[0][:2] == ["powershell", "-NoProfile"]
        mocker.patch.object(process.os, "name", "nt")
        mocker.patch.object(
            process,
            "command_argv",
            return_value=["pythonw.exe", r"C:\installed\proxy.py"],
        )
        assert process.command_names_path(
            r"pythonw.exe C:\installed\proxy.py", r"C:\installed\proxy.py"
        )

    def test_termination_rechecks_identity_and_proves_exit(self, subtests, *, mocker):
        for name, command in (
            ("nt", ["taskkill", "/pid", "123", "/f"]),
            ("posix", ["kill", "-TERM", "123"]),
        ):
            with subtests.test(platform=name):
                mocker.patch.object(process.os, "name", name)
                mocker.patch.object(process, "pid_names_path", return_value=False)
                invoked = mocker.patch.object(process.subprocess, "run")
                assert not process.terminate_pid(123, expected_path="/proxy.py")
                invoked.assert_not_called()
                mocker.patch.object(process.os, "name", name)
                mocker.patch.object(process, "pid_names_path", side_effect=[True, True, False])
                invoked = mocker.patch.object(
                    process.subprocess,
                    "run",
                    return_value=_completed(returncode=0),
                )
                mocker.patch.object(process.time, "monotonic", side_effect=[0.0, 0.1])
                sleep = mocker.patch.object(process.time, "sleep")
                assert process.terminate_pid(123, expected_path="/proxy.py", timeout_seconds=1.0)
                invoked.assert_called_once_with(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                sleep.assert_called_once_with(0.05)

    def test_termination_fails_on_signal_error_or_post_kill_timeout(self, *, mocker):
        mocker.patch.object(process, "pid_names_path", return_value=True)
        mocker.patch.object(
            process.subprocess,
            "run",
            return_value=_completed(returncode=1),
        )
        assert not process.terminate_pid(123, expected_path="/proxy.py")
        mocker.patch.object(process, "pid_names_path", return_value=True)
        mocker.patch.object(
            process.subprocess,
            "run",
            return_value=_completed(returncode=0),
        )
        mocker.patch.object(process.time, "monotonic", side_effect=[0.0, 0.1, 1.1])
        sleep = mocker.patch.object(process.time, "sleep")
        assert not process.terminate_pid(123, expected_path="/proxy.py", timeout_seconds=1.0)
        sleep.assert_called_once_with(0.05)

    def test_native_termination_rechecks_identity_and_proves_exit(self, subtests, *, mocker):
        executable = "/installed/codex-responses-proxy"
        roles = {"--internal-listener", "--internal-handoff-child"}
        for name, command in (
            ("nt", ["taskkill", "/pid", "123", "/f"]),
            ("posix", ["kill", "-TERM", "123"]),
        ):
            with subtests.test(platform=name):
                mocker.patch.object(process.os, "name", name)
                owns = mocker.patch.object(
                    process,
                    "pid_names_executable",
                    side_effect=[True, True, False],
                )
                invoked = mocker.patch.object(
                    process.subprocess,
                    "run",
                    return_value=_completed(returncode=0),
                )
                mocker.patch.object(process.time, "monotonic", side_effect=[0.0, 0.1])
                sleep = mocker.patch.object(process.time, "sleep")

                assert process.terminate_executable(
                    123,
                    executable,
                    roles=roles,
                    timeout_seconds=1.0,
                )
                assert owns.call_count == 3
                invoked.assert_called_once_with(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                sleep.assert_called_once_with(0.05)
                mocker.stopall()

    def test_native_termination_fails_closed_before_and_after_signal(self, subtests, *, mocker):
        executable = "/installed/codex-responses-proxy"
        cases = (
            ("identity", [False], None, [0.0], 0),
            ("signal", [True], 1, [0.0], 1),
            ("timeout", [True, True], 0, [0.0, 1.0], 1),
        )
        for case, identities, returncode, clocks, expected_calls in cases:
            with subtests.test(case=case):
                mocker.patch.object(process.os, "name", "posix")
                mocker.patch.object(
                    process,
                    "pid_names_executable",
                    side_effect=identities,
                )
                invoked = mocker.patch.object(
                    process.subprocess,
                    "run",
                    return_value=_completed(returncode=returncode or 0),
                )
                mocker.patch.object(process.time, "monotonic", side_effect=clocks)
                sleep = mocker.patch.object(process.time, "sleep")

                assert not process.terminate_executable(
                    123,
                    executable,
                    timeout_seconds=1.0,
                )
                assert invoked.call_count == expected_calls
                sleep.assert_not_called()
                mocker.stopall()
