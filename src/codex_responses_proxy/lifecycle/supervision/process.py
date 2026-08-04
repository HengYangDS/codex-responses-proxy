"""Discover and terminate only process identities owned by this installation."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import shlex
import struct
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

from codex_responses_proxy.lifecycle.context import RuntimeContext
from codex_responses_proxy.service import runtime as service_runtime


@dataclass(frozen=True)
class OwnedProcess:
    """A PID bound to the exact process entry path proven to own it."""

    pid: int
    script: str


def listener_pids(port: int) -> list[int]:
    """Return PIDs listening on ``port``; identity verification is separate."""

    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False
            ).stdout
            return [
                int(fields[-1])
                for line in output.splitlines()
                if len(fields := line.split()) >= 5
                and fields[1].endswith(f":{port}")
                and fields[3].upper() == "LISTENING"
                and fields[-1].isdigit()
            ]
        output = subprocess.run(
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return [int(value) for value in output.split() if value.isdigit()]
    except (OSError, ValueError):
        return []


def process_command(pid: int) -> str:
    """Return a process command line for identity proof, or an empty string."""

    try:
        if os.name == "nt":
            command = (
                '$p=Get-CimInstance Win32_Process -Filter "ProcessId=' + str(pid) + '";'
                "if ($p) {$p.CommandLine}"
            )
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        return ""


def process_argv(pid: int) -> list[str]:
    """Return the native argv for one process without guessing shell quoting."""

    if sys.platform == "darwin":
        return _darwin_process_argv(pid)
    return command_argv(process_command(pid))


def _darwin_process_argv(pid: int) -> list[str]:
    """Read ``kern.procargs2`` so paths containing spaces retain argv identity."""

    try:
        library = ctypes.util.find_library("c")
        if not library:
            return []
        libc = ctypes.CDLL(library, use_errno=True)
        mib = (ctypes.c_int * 3)(1, 49, pid)
        size = ctypes.c_size_t()
        if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 5:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
            return []
        count = struct.unpack("=i", buffer.raw[:4])[0]
        if count <= 0:
            return []
        fields = buffer.raw[4 : size.value].split(b"\0")
        index = 1
        while index < len(fields) and not fields[index]:
            index += 1
        arguments = fields[index : index + count]
        if len(arguments) != count or any(not value for value in arguments):
            return []
        return [value.decode(sys.getfilesystemencoding()) for value in arguments]
    except (OSError, UnicodeError, ValueError, struct.error):
        return []


def _process_inventory() -> list[tuple[int, str]]:
    """Return one fail-closed host process inventory as PID and command line."""

    try:
        if os.name == "nt":
            command = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine } | "
                'ForEach-Object { "$($_.ProcessId)`t$($_.CommandLine)" }'
            )
            output = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        else:
            output = subprocess.run(
                ["ps", "-axo", "pid=,command="],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
    except OSError:
        return []
    inventory: list[tuple[int, str]] = []
    for line in output.splitlines():
        fields = line.split("\t", 1) if os.name == "nt" else line.lstrip().split(None, 1)
        if len(fields) != 2 or not (command := fields[1].strip()):
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        inventory.append((pid, command))
    return inventory


def _windows_argv(command: str) -> list[str]:
    """Parse one native Windows command line with the operating-system grammar."""

    windll = getattr(ctypes, "windll", None)
    if not command or windll is None:
        return []
    command_line_to_argv = windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    command_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
    local_free = windll.kernel32.LocalFree
    local_free.argtypes = [wintypes.HLOCAL]
    local_free.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    argv = command_line_to_argv(command, ctypes.byref(count))
    if not argv:
        return []
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        local_free(argv)


def command_argv(command: str) -> list[str]:
    """Parse a process command line without executing or shell-expanding it."""

    try:
        return _windows_argv(command) if os.name == "nt" else shlex.split(command, posix=True)
    except (OSError, ValueError):
        return []


def command_names_path(command: str, expected_path: str) -> bool:
    """Return whether a Python process executes exactly ``expected_path``."""

    argv = command_argv(command)
    executable = os.path.basename(argv[0]).lower() if argv else ""
    if executable.endswith(".exe"):
        executable = executable[:-4]
    if len(argv) < 2 or re.fullmatch(r"python(?:w|3(?:\.\d+)?)?", executable) is None:
        return False
    expected = os.path.normcase(os.path.realpath(os.path.abspath(expected_path)))
    argument = os.path.normcase(os.path.realpath(os.path.abspath(argv[1])))
    return argument == expected


def argv_names_executable(
    argv: list[str], expected_path: str, *, roles: set[str] | frozenset[str] | None = None
) -> bool:
    """Bind a native process to one exact executable and optional private role."""

    if not argv:
        return False
    expected = os.path.normcase(os.path.realpath(os.path.abspath(expected_path)))
    actual = os.path.normcase(os.path.realpath(os.path.abspath(argv[0])))
    if actual != expected:
        return False
    return roles is None or bool(roles.intersection(argv[1:]))


def command_names_executable(
    command: str,
    expected_path: str,
    *,
    roles: set[str] | frozenset[str] | None = None,
) -> bool:
    """Parse a command and apply native executable identity semantics."""

    return argv_names_executable(command_argv(command), expected_path, roles=roles)


def pid_names_path(pid: int, expected_path: str) -> bool:
    """Re-read ``pid`` and prove that one argument is the exact expected path."""

    argv = process_argv(pid)
    executable = os.path.basename(argv[0]).lower() if argv else ""
    if executable.endswith(".exe"):
        executable = executable[:-4]
    if len(argv) < 2 or re.fullmatch(r"python(?:w|3(?:\.\d+)?)?", executable) is None:
        return False
    expected = os.path.normcase(os.path.realpath(os.path.abspath(expected_path)))
    argument = os.path.normcase(os.path.realpath(os.path.abspath(argv[1])))
    return argument == expected


def pids_naming_path(expected_path: str) -> list[int]:
    """Return process IDs whose argv exactly names ``expected_path``."""

    return [pid for pid, _command in _process_inventory() if pid_names_path(pid, expected_path)]


def pid_names_executable(
    pid: int,
    expected_path: str,
    *,
    roles: set[str] | frozenset[str] | None = None,
) -> bool:
    """Re-read one PID and prove its exact native executable and private role."""

    return argv_names_executable(process_argv(pid), expected_path, roles=roles)


def pids_naming_executable(
    expected_path: str, *, roles: set[str] | frozenset[str] | None = None
) -> list[int]:
    """Return PIDs bound to one native executable and optional private role."""

    return [
        pid
        for pid, _command in _process_inventory()
        if pid_names_executable(pid, expected_path, roles=roles)
    ]


def verified_listener_pids(port: int, expected_path: str) -> list[int]:
    """Return listeners whose argv exactly names ``expected_path``."""

    return [pid for pid in listener_pids(port) if pid_names_path(pid, expected_path)]


def verified_proxy_listener_pids(context: RuntimeContext) -> list[int]:
    """Return listeners owned by the installed native product executable."""

    return [
        pid
        for pid in listener_pids(context.port)
        if pid_names_executable(
            pid,
            context.executable,
            roles={service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE},
        )
    ]


def terminate_executable(
    pid: int,
    expected_path: str,
    *,
    roles: set[str] | frozenset[str] | None = None,
    timeout_seconds: float = 5.0,
) -> bool:
    """Signal and prove exit of one exact native executable identity."""

    if not pid_names_executable(pid, expected_path, roles=roles):
        return False
    command = (
        ["taskkill", "/pid", str(pid), "/f"] if os.name == "nt" else ["kill", "-TERM", str(pid)]
    )
    result = subprocess.run(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    if result.returncode != 0:
        return False
    deadline = time.monotonic() + timeout_seconds
    while pid_names_executable(pid, expected_path, roles=roles):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def terminate_pid(pid: int, *, expected_path: str, timeout_seconds: float = 5.0) -> bool:
    """Signal an exact process identity and prove that identity is gone.

    The command line is re-read immediately before the signal. Afterwards, PID
    disappearance or a different occupant proves that the original process
    exited; the new occupant is never signalled.
    """

    if not pid_names_path(pid, expected_path):
        return False
    command = (
        ["taskkill", "/pid", str(pid), "/f"] if os.name == "nt" else ["kill", "-TERM", str(pid)]
    )
    result = subprocess.run(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    if result.returncode != 0:
        return False
    deadline = time.monotonic() + timeout_seconds
    while pid_names_path(pid, expected_path):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True
