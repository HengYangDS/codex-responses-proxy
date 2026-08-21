"""Keep one installed proxy listener available without restart storms.

The native user service owns watchdog persistence. This process probes the
configured loopback port, starts only the absolute installed entrypoint when it
is unavailable, and backs off after repeated failures. Logs are bounded and
secret-safe; request payloads never cross this boundary.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from codex_responses_proxy.runtime import bounded_log
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import runtime as service_runtime

SETTINGS = runtime_config.load()
HOST, PORT = SETTINGS.listener
EXECUTABLE = str(Path(sys.executable).resolve())
LISTENER_MODE = service_runtime.LISTENER_MODE
CHECK_INTERVAL = SETTINGS.watchdog_interval
MAX_BACKOFF = SETTINGS.watchdog_max_backoff
LOG_PATH = SETTINGS.watchdog_log.path
_WINDOWS_DETACH_FLAGS = 0x00000008 | 0x00000200


LOG_MAX_BYTES = SETTINGS.watchdog_log.max_bytes
LOG_BACKUP_COUNT = SETTINGS.watchdog_log.backup_count


def _reap_children(children: list[subprocess.Popen[bytes]]) -> None:
    """Reap exited listener children so the watchdog never leaves zombies."""

    children[:] = [child for child in children if child.poll() is None]


def _log(msg: str) -> None:
    bounded_log.append(Path(LOG_PATH), msg, max_bytes=LOG_MAX_BYTES, backup_count=LOG_BACKUP_COUNT)


def is_proxy_up(host: str = HOST, port: int = PORT, timeout: float = 2.0) -> bool:
    """True if something is listening on host:port (a cheap TCP connect probe)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def spawn_proxy() -> subprocess.Popen | None:
    """Start the proxy detached from this watchdog so it outlives us.

    Uses the exact installed executable path. Detaches via ``start_new_session``
    on POSIX and ``DETACHED_PROCESS`` on Windows so a watchdog restart never
    signals the proxy.
    """
    if not os.path.exists(EXECUTABLE):
        _log("ERROR installed proxy executable is unavailable")
        return None
    try:
        command = [EXECUTABLE, LISTENER_MODE]
        if os.name == "nt":
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                creationflags=_WINDOWS_DETACH_FLAGS,
            )
        else:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        _log(f"spawned proxy pid={proc.pid}")
        return proc
    except Exception as exc:
        _log(f"ERROR failed to spawn proxy: {exc.__class__.__name__}")
        return None


def run(max_iterations: int | None = None) -> None:
    """Resident supervise loop. ``max_iterations`` bounds the loop for testing."""
    _log(
        f"watchdog starting: guard {HOST}:{PORT} every {CHECK_INTERVAL}s "
        f"executable={Path(EXECUTABLE).name}"
    )
    consecutive_failures = 0
    iterations = 0
    children: list[subprocess.Popen[bytes]] = []
    while True:
        _reap_children(children)
        up = is_proxy_up()
        sleep_for = CHECK_INTERVAL
        if not up:
            _log(f"proxy down on {HOST}:{PORT} — starting it")
            if child := spawn_proxy():
                children.append(child)
            consecutive_failures += 1
            settle = min(MAX_BACKOFF, CHECK_INTERVAL * consecutive_failures)
            time.sleep(min(3.0, settle))
            up = is_proxy_up()
            if not up:
                sleep_for = settle
                _log(
                    f"proxy still down after start attempt "
                    f"#{consecutive_failures}; backing off {sleep_for:.0f}s"
                )
        if up:
            consecutive_failures = 0

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
        time.sleep(sleep_for)
