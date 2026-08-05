"""Exact process identity and termination contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from codex_responses_proxy.lifecycle.supervision import process
from tests.lifecycle.fixtures import platform_context


class TestProcessIdentity:
    def test_psutil_process_inventory_and_listener_discovery_are_host_command_free(self, *, mocker):
        first = mocker.Mock(pid=7)
        first.cmdline.return_value = ["python", "/installed/proxy.py"]
        first.info = {
            "net_connections": [
                mocker.Mock(status=process.psutil.CONN_LISTEN, laddr=mocker.Mock(port=8791))
            ]
        }
        second = mocker.Mock(pid=8)
        second.cmdline.side_effect = process.psutil.AccessDenied(8)
        second.info = {"net_connections": []}
        process_iter = mocker.patch.object(
            process.psutil,
            "process_iter",
            side_effect=([first, second], [first, second]),
        )

        assert process._process_inventory() == [(7, ["python", "/installed/proxy.py"])]
        assert process.listener_pids(8791) == [7]
        assert process_iter.call_args_list[1].args == (["pid", "net_connections"],)

    def test_process_discovery_fails_closed(self, *, mocker):
        mocker.patch.object(
            process.psutil,
            "process_iter",
            side_effect=process.psutil.AccessDenied(),
        )
        assert process.listener_pids(8791) == []
        mocker.patch.object(
            process.psutil,
            "Process",
            side_effect=process.psutil.NoSuchProcess(123),
        )
        assert process.process_argv(123) == []
        assert process.process_command(123) == ""

    def test_process_inventory_and_path_discovery_fail_closed(self, *, mocker):
        mocker.patch.object(
            process.psutil,
            "process_iter",
            side_effect=process.psutil.AccessDenied(),
        )
        assert process._process_inventory() == []
        mocker.patch.object(
            process,
            "_process_inventory",
            return_value=[
                (7, ["python", "/installed/watchdog.py.backup"]),
                (8, ["python", "/installed/watchdog.py"]),
                (9, ["python", "-c", "print", "/installed/watchdog.py"]),
            ],
        )
        mocker.patch.object(
            process,
            "process_argv",
            side_effect=[
                ["python", "/installed/watchdog.py.backup"],
                ["python", "/installed/watchdog.py"],
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
            side_effect=[[executable, "--internal-watchdog"], [executable, listener]],
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

    def test_identity_helpers_cover_empty_roles_and_python_suffixes(self, subtests, *, mocker):
        executable = os.path.abspath("/installed/codex-responses-proxy")
        for argv, roles, expected in (
            ([], None, False),
            ([executable], None, True),
            ([executable, "--watchdog"], {"--listener"}, False),
        ):
            with subtests.test(argv=argv, roles=roles):
                assert process.argv_names_executable(argv, executable, roles=roles) is expected

        for argv, expected in (
            (["python3.12", "/installed/proxy.py"], True),
            (["pythonw.exe", "/installed/proxy.py"], True),
            (["ruby", "/installed/proxy.py"], False),
            (["python"], False),
        ):
            with subtests.test(argv=argv):
                mocker.patch.object(process, "process_argv", return_value=argv)
                assert process.pid_names_path(17, "/installed/proxy.py") is expected
                mocker.stopall()

        mocker.patch.object(process, "_process_inventory", return_value=[(17, [executable])])
        mocker.patch.object(process, "pid_names_executable", return_value=True)
        assert process.pids_naming_executable(executable) == [17]

    def test_process_command_quotes_native_argv(self, *, mocker):
        mocker.patch.object(
            process,
            "process_argv",
            return_value=["/usr/bin/python3", "/installed/proxy with spaces.py"],
        )
        assert process.process_command(17) == ("/usr/bin/python3 '/installed/proxy with spaces.py'")

    @pytest.mark.skipif(sys.platform != "darwin", reason="real Darwin argv integration")
    def test_real_process_argv_preserves_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="responses proxy argv ") as directory:
            fixture = Path(directory, "listener entrypoint.py")
            fixture.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            child = subprocess.Popen([sys.executable, str(fixture)])
            try:
                assert process.process_argv(child.pid) == [sys.executable, str(fixture)]
                assert process.pid_names_path(child.pid, str(fixture))
                assert child.pid in process.pids_naming_path(str(fixture))
            finally:
                child.terminate()
                child.wait(timeout=5)


class TestTermination:
    def test_script_termination_rechecks_identity_and_waits(self, *, mocker):
        mocker.patch.object(process, "pid_names_path", side_effect=[True, True])
        candidate = mocker.Mock()
        mocker.patch.object(process.psutil, "Process", return_value=candidate)

        assert process.terminate_pid(123, expected_path="/proxy.py", timeout_seconds=1.0)
        candidate.terminate.assert_called_once_with()
        candidate.wait.assert_called_once_with(timeout=1.0)

    def test_script_termination_fails_closed(self, subtests, *, mocker):
        cases = (
            ("identity", [False], None),
            ("identity changed", [True, False], None),
            ("wait", [True, True], process.psutil.TimeoutExpired(123, 1)),
        )
        for case, identities, failure in cases:
            with subtests.test(case=case):
                mocker.patch.object(process, "pid_names_path", side_effect=identities)
                candidate = mocker.Mock()
                if failure is not None:
                    candidate.wait.side_effect = failure
                constructor = mocker.patch.object(process.psutil, "Process", return_value=candidate)
                assert not process.terminate_pid(
                    123, expected_path="/proxy.py", timeout_seconds=1.0
                )
                constructor_calls = 0 if case == "identity" else 1
                assert constructor.call_count == constructor_calls
                mocker.stopall()

    def test_native_termination_rechecks_identity_and_waits(self, *, mocker):
        roles = {"--internal-listener"}
        mocker.patch.object(
            process,
            "pid_names_executable",
            side_effect=[True, True],
        )
        candidate = mocker.Mock()
        mocker.patch.object(process.psutil, "Process", return_value=candidate)

        assert process.terminate_executable(
            123,
            "/installed/codex-responses-proxy",
            roles=roles,
            timeout_seconds=1.0,
        )
        candidate.terminate.assert_called_once_with()
        candidate.wait.assert_called_once_with(timeout=1.0)

    def test_native_termination_accepts_already_exited_identity(self, *, mocker):
        mocker.patch.object(
            process,
            "pid_names_executable",
            side_effect=[True, True],
        )
        candidate = mocker.Mock()
        candidate.wait.side_effect = process.psutil.NoSuchProcess(123)
        mocker.patch.object(process.psutil, "Process", return_value=candidate)

        assert process.terminate_executable(123, "/installed/codex-responses-proxy")

    def test_native_termination_fails_closed(self, subtests, *, mocker):
        for case, identities, constructor_failure, wait_failure in (
            ("initial identity", [False], None, None),
            ("reused pid", [True, False], None, None),
            ("constructor", [True], process.psutil.AccessDenied(123), None),
            ("wait", [True, True], None, process.psutil.TimeoutExpired(123, 1)),
        ):
            with subtests.test(case=case):
                mocker.patch.object(
                    process,
                    "pid_names_executable",
                    side_effect=identities,
                )
                candidate = mocker.Mock()
                candidate.wait.side_effect = wait_failure
                constructor = mocker.patch.object(
                    process.psutil,
                    "Process",
                    side_effect=constructor_failure or [candidate],
                )
                assert not process.terminate_executable(
                    123,
                    "/installed/codex-responses-proxy",
                    timeout_seconds=1.0,
                )
                if case == "initial identity":
                    constructor.assert_not_called()
                mocker.stopall()

    def test_script_termination_accepts_already_exited_identity(self, *, mocker):
        mocker.patch.object(process, "pid_names_path", side_effect=[True, True])
        candidate = mocker.Mock()
        candidate.wait.side_effect = process.psutil.NoSuchProcess(123)
        mocker.patch.object(process.psutil, "Process", return_value=candidate)

        assert process.terminate_pid(123, expected_path="/installed/proxy.py")
