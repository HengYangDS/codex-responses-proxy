"""Discover and terminate only process identities owned by this installation."""

from __future__ import annotations

import ctypes
import os
import re
import shlex
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass

from codex_responses_proxy.runtime.context import RuntimeContext


@dataclass(frozen=True)
class OwnedProcess:
    """A PID bound to the exact installed script proven to own it."""

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


def pid_names_path(pid: int, expected_path: str) -> bool:
    """Re-read ``pid`` and prove that one argument is the exact expected path."""

    return command_names_path(process_command(pid), expected_path)


def pids_naming_path(expected_path: str) -> list[int]:
    """Return process IDs whose argv exactly names ``expected_path``."""

    return [
        pid for pid, command in _process_inventory() if command_names_path(command, expected_path)
    ]


def verified_listener_pids(port: int, expected_path: str) -> list[int]:
    """Return listeners whose argv exactly names ``expected_path``."""

    return [pid for pid in listener_pids(port) if pid_names_path(pid, expected_path)]


def verified_proxy_listener_pids(context: RuntimeContext) -> list[int]:
    """Return listeners whose argv exactly names the current proxy entrypoint."""

    return verified_listener_pids(context.port, context.proxy_script)


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
