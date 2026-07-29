#!/usr/bin/env python3
"""Cross-platform service, interpreter, process, and watchdog contracts."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import xml.dom.minidom as minidom
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy import errors, installation, process, python_runtime  # noqa: E402
from codex_dmx_proxy.supervision import linux, macos, windows  # noqa: E402
from tests.support.repository_fixtures import (  # noqa: E402
    assert_private_log_mode,
    platform_context,
)

MACOS_CONTAINS = """<key>KeepAlive</key>
<true/>
/usr/bin/python3.12
com.user.codex-dmx-watchdog
DMX_PROXY_PORT
8791
DMX_PROXY_LOG_MAX_BYTES
4194304
DMX_WATCHDOG_LOG_BACKUP_COUNT
<string>/dev/null</string>""".splitlines()
LINUX_CONTAINS = f"""Restart=always
RestartSec=3
WantedBy=default.target
ExecStart=/usr/bin/python3.12
Environment=DMX_PROXY_PORT=8791
Environment=DMX_PROXY_LOG_MAX_BYTES={installation.DEFAULT_PROXY_LOG_MAX_BYTES}
Environment=DMX_WATCHDOG_LOG_BACKUP_COUNT={installation.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}""".splitlines()
WINDOWS_TASK_CONTAINS = f"""<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
<LogonTrigger>
<RestartOnFailure>
<LogonType>InteractiveToken</LogonType>
<RunLevel>LeastPrivilege</RunLevel>
<TimeTrigger>
<StartBoundary>{windows._SELF_HEAL_START_BOUNDARY}</StartBoundary>
<Repetition>
<Interval>PT1M</Interval>
<StopAtDurationEnd>false</StopAtDurationEnd>
<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
<Command>/usr/bin/python3.12</Command>
run-watchdog.pyw""".splitlines()
WINDOWS_LAUNCHER_CONTAINS = f"""'DMX_PROXY_PORT'] = '8801'
'DMX_UPSTREAM'] = 'https://alternate.example'
'DMX_PROXY_PYTHON'] = '/usr/bin/python3.12'
'DMX_PROXY_SCRIPT'] = '/home/tester/.codex/dmx-proxy/codex_dmx_proxy/listener/entrypoint.py'
'DMX_PROXY_LOG_MAX_BYTES'] = '{installation.DEFAULT_PROXY_LOG_MAX_BYTES}'
'DMX_WATCHDOG_LOG_BACKUP_COUNT'] = '{installation.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}'
runpy.run_path('/home/tester/.codex/dmx-proxy/watchdog/watchdog.py', run_name='__main__')""".splitlines()


def _completed(cmd=(), returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


@contextmanager
def _temporary_context(attribute):
    with tempfile.TemporaryDirectory() as directory:
        ctx = platform_context()
        setattr(ctx, attribute, directory)
        yield ctx


def _set_file(path, text=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _assert_fragments(test, text, include=(), exclude=()):
    for fragment in include:
        with test.subTest(fragment=fragment):
            test.assertIn(fragment, text)
    for fragment in exclude:
        with test.subTest(fragment=fragment):
            test.assertNotIn(fragment, text)


def _assert_executable_mode(test, mode):
    """Assert POSIX execution or the strongest Windows mode projection."""

    if os.name == "nt":
        test.assertEqual(mode & 0o600, 0o600)
    else:
        test.assertEqual(mode, 0o755)


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

        with mock.patch.object(
            process,
            "_process_inventory",
            return_value=[
                (7, "python /installed/watchdog.py.backup"),
                (8, 'python "/installed/watchdog.py"'),
                (9, "powershell -Command 'Write-Output /installed/watchdog.py'"),
                (10, "powershell -Command Write-Output /installed/watchdog.py"),
                (11, "python -c print /installed/watchdog.py"),
            ],
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
                "process_command",
                side_effect=[f"python {script}.backup", f'python "{script}"'],
            ),
        ):
            self.assertEqual(process.verified_proxy_listener_pids(ctx), [8])
        legacy = "/home/tester/.codex/dmx-proxy/proxy/dmx_responses_proxy.py"
        with (
            mock.patch.object(process, "listener_pids", return_value=[7, 8]),
            mock.patch.object(
                process,
                "process_command",
                side_effect=[f'python "{legacy}"', f'python "{script}"'],
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


class TestServiceDefinitions(unittest.TestCase):
    def test_macos_plist(self):
        xml = macos.render_plist(platform_context())
        minidom.parseString(xml)
        _assert_fragments(
            self, xml, MACOS_CONTAINS, ("dmx-watchdog.out.log", "dmx-watchdog.err.log")
        )

    def test_linux_unit(self):
        unit = linux.render_unit(platform_context())
        _assert_fragments(self, unit, LINUX_CONTAINS)
        self.assertNotIn("multi-user.target", unit)

    def test_windows_task(self):
        ctx = platform_context()
        xml = windows.render_task_xml(ctx)
        minidom.parseString(xml)
        _assert_fragments(self, xml, WINDOWS_TASK_CONTAINS)
        _assert_fragments(self, xml.lower(), exclude=("cmd.exe", "comspec", "run-watchdog.cmd"))

    def test_windows_launcher(self):
        ctx = platform_context(port=8801, upstream="https://alternate.example")
        launcher = windows.render_launcher(ctx)
        self.assertNotIn(
            'Arguments>"/home/tester/.codex/dmx-proxy/watchdog/watchdog.py"',
            windows.render_task_xml(ctx),
        )
        _assert_fragments(self, launcher, WINDOWS_LAUNCHER_CONTAINS)


class TestWatchdogLogging(unittest.TestCase):
    def test_watchdog_log_is_bounded_and_redacts_secrets(self):
        spec = importlib.util.spec_from_file_location(
            "dmx_watchdog_for_test", ROOT / "watchdog" / "watchdog.py"
        )
        assert spec is not None and spec.loader is not None
        watchdog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watchdog)
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
            existing = f"@reboot {wrapper} # {installation.LABEL}\n@reboot /keep-me\n"
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
            self.assertIn('export DMX_PROXY_PORT="8791"', text)
            _assert_executable_mode(self, Path(wrapper).stat().st_mode & 0o777)
            installed = invoked.call_args_list[1].kwargs["input"]
            self.assertEqual(installed.count(installation.LABEL), 1)
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
            owned = f"@reboot /owned # {installation.LABEL}\n@reboot /keep-me\n"
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
                (False, "crontab", f"@reboot x # {installation.LABEL}\n", "installed"),
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

            owned = f"@reboot /owned # {installation.LABEL}\n"
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


class TestMacosLifecycle(unittest.TestCase):
    def test_install(self):
        with _temporary_context("home") as ctx:
            plist = macos._plist_path(ctx)
            with mock.patch.object(
                macos.subprocess,
                "run",
                side_effect=[_completed(), _completed(), _completed()],
            ) as invoked:
                macos.install(ctx)
            self.assertEqual(Path(plist).read_text(encoding="utf-8"), macos.render_plist(ctx))
            self.assertEqual(invoked.call_args_list[0].args[0], ["plutil", "-lint", plist])
            with (
                mock.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[
                        _completed(),
                        _completed(),
                        _completed(returncode=1, stderr=" denied "),
                    ],
                ),
                self.assertRaisesRegex(errors.InstallError, "launchctl load failed: denied"),
            ):
                macos.install(ctx)

    def test_status_and_uninstall(self):
        with _temporary_context("home") as ctx:
            plist = Path(macos._plist_path(ctx))
            for exists, listing, expected in (
                (False, "", "absent"),
                (True, "other", "installed"),
                (True, installation.LABEL, "running"),
            ):
                _set_file(plist, "plist" if exists else None)
                with mock.patch.object(
                    macos.subprocess, "run", return_value=_completed(stdout=listing)
                ):
                    self.assertEqual(macos.status(ctx), expected)
            for exists in (False, True):
                _set_file(plist, "plist" if exists else None)
                with mock.patch.object(
                    macos.subprocess,
                    "run",
                    side_effect=[_completed(), _completed(stdout="other")],
                ) as invoked:
                    macos.uninstall(ctx)
                self.assertFalse(plist.exists())
                self.assertEqual(invoked.call_count, 2 * int(exists))

    def test_uninstall_keeps_plist_when_launchd_removal_is_unproven(self):
        with _temporary_context("home") as ctx:
            plist = _set_file(macos._plist_path(ctx), "plist")
            with (
                mock.patch.object(
                    macos.subprocess,
                    "run",
                    return_value=_completed(returncode=1, stderr="denied"),
                ),
                self.assertRaisesRegex(errors.InstallError, "launchctl unload failed"),
            ):
                macos.uninstall(ctx)
            self.assertTrue(plist.exists())


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
                ["schtasks", "/run", "/tn", windows.TASK_NAME],
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
