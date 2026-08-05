"""Discover and terminate only process identities owned by this installation."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

import psutil

from codex_responses_proxy.lifecycle.context import RuntimeContext
from codex_responses_proxy.service import runtime as service_runtime


@dataclass(frozen=True)
class OwnedProcess:
    """A PID bound to the exact process entry path proven to own it."""

    pid: int
    script: str


def listener_pids(port: int) -> list[int]:
    """Return PIDs listening on ``port``; identity verification is separate."""

    listeners: set[int] = set()
    try:
        processes = psutil.process_iter(["pid", "net_connections"])
        for candidate in processes:
            try:
                connections = candidate.info["net_connections"]
            except (KeyError, OSError, psutil.Error):
                continue
            if any(
                connection.status == psutil.CONN_LISTEN
                and getattr(connection.laddr, "port", None) == port
                for connection in connections or ()
            ):
                listeners.add(candidate.pid)
    except (OSError, psutil.Error):
        pass
    return sorted(listeners)


def process_command(pid: int) -> str:
    """Return a process command line for identity proof, or an empty string."""

    return shlex.join(process_argv(pid))


def process_argv(pid: int) -> list[str]:
    """Return the native argv for one process without guessing shell quoting."""

    try:
        return psutil.Process(pid).cmdline()
    except (OSError, psutil.Error):
        return []


def _process_inventory() -> list[tuple[int, list[str]]]:
    """Return one fail-closed host process inventory as PID and native argv."""

    inventory: list[tuple[int, list[str]]] = []
    try:
        processes = psutil.process_iter(["pid"])
        for candidate in processes:
            try:
                argv = candidate.cmdline()
            except (OSError, psutil.Error):
                continue
            if argv:
                inventory.append((candidate.pid, argv))
    except (OSError, psutil.Error):
        return []
    return inventory


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

    return [pid for pid, _argv in _process_inventory() if pid_names_path(pid, expected_path)]


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
        for pid, _argv in _process_inventory()
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
    try:
        candidate = psutil.Process(pid)
        if not pid_names_executable(pid, expected_path, roles=roles):
            return False
        candidate.terminate()
        candidate.wait(timeout=timeout_seconds)
    except psutil.NoSuchProcess:
        return True
    except (OSError, psutil.Error):
        return False
    return True


def terminate_pid(pid: int, *, expected_path: str, timeout_seconds: float = 5.0) -> bool:
    """Signal an exact process identity and prove that identity is gone.

    The command line is re-read immediately before the signal. Afterwards, PID
    disappearance or a different occupant proves that the original process
    exited; the new occupant is never signalled.
    """

    if not pid_names_path(pid, expected_path):
        return False
    try:
        candidate = psutil.Process(pid)
        if not pid_names_path(pid, expected_path):
            return False
        candidate.terminate()
        candidate.wait(timeout=timeout_seconds)
    except psutil.NoSuchProcess:
        return True
    except (OSError, psutil.Error):
        return False
    return True
