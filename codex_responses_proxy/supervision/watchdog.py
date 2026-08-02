#!/usr/bin/env python3
"""Keep one installed proxy listener available without restart storms.

The native user service owns watchdog persistence. This process probes the
configured loopback port, starts only the absolute installed entrypoint when it
is unavailable, and backs off after repeated failures. Logs are bounded and
secret-safe; request payloads never cross this boundary.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry) != _HERE]
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import re
import stat
import time
import socket
import subprocess
import threading
from contextlib import suppress
from pathlib import Path

from codex_responses_proxy.runtime import config as runtime_config

SETTINGS = runtime_config.load()
HOST, PORT = SETTINGS.listener
PYTHON = os.environ.get(runtime_config.PROXY_PYTHON_ENV, sys.executable)
SCRIPT = os.environ.get(
    runtime_config.PROXY_SCRIPT_ENV,
    os.path.join(os.path.dirname(_HERE), "listener", "entrypoint.py"),
)
CHECK_INTERVAL = SETTINGS.watchdog_interval
MAX_BACKOFF = SETTINGS.watchdog_max_backoff
LOG_PATH = SETTINGS.watchdog_log.path
_WINDOWS_DETACH_FLAGS = 0x00000008 | 0x00000200


LOG_MAX_BYTES = SETTINGS.watchdog_log.max_bytes
LOG_BACKUP_COUNT = SETTINGS.watchdog_log.backup_count
_LOG_LINE_MAX_BYTES = 1024
_LOG_LOCK = threading.Lock()
_LOG_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|bearer)\s*[:=]?\s*(?:bearer\s+)?[^\s,;]+"),
    re.compile(r"\bgAAAA[A-Za-z0-9_-]+"),
)


def _redact_log_message(msg: str) -> str:
    """Bound watchdog diagnostics without retaining secret-shaped values."""
    value = str(msg).replace("\r", " ").replace("\n", " ")
    value = _LOG_SECRET_PATTERNS[1].sub(
        "[redacted]", _LOG_SECRET_PATTERNS[0].sub("[redacted]", value)
    )
    encoded = value.encode("utf-8", "replace")
    if len(encoded) > _LOG_LINE_MAX_BYTES:
        value = encoded[:_LOG_LINE_MAX_BYTES].decode("utf-8", "ignore") + " [truncated]"
    return value


def _rotate_log_if_needed(path: Path, incoming_bytes: int) -> int:
    """Keep the watchdog log within its configured local retention window."""
    try:
        metadata = path.lstat()
    except OSError:
        return 0
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("watchdog log path is not a regular file")
    current_size = metadata.st_size
    if current_size + incoming_bytes <= LOG_MAX_BYTES:
        return 0

    if current_size > LOG_MAX_BYTES:
        path.unlink(missing_ok=True)
        return current_size
    elif LOG_BACKUP_COUNT <= 0:
        path.unlink(missing_ok=True)
    else:
        path.with_name(f"{path.name}.{LOG_BACKUP_COUNT}").unlink(missing_ok=True)
        for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
    return 0


def _log(msg: str) -> None:
    message = _redact_log_message(msg)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n"
    try:
        path = Path(LOG_PATH)
        with _LOG_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            discarded = _rotate_log_if_needed(path, len(line.encode("utf-8", "replace")))
            if discarded:
                line = (
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"log_retention_discarded_oversized_bytes={discarded} {message}\n"
                )
            with path.open("a", encoding="utf-8") as handle:
                with suppress(OSError):
                    os.chmod(path, 0o600)
                handle.write(line)
    except OSError:
        pass


def is_proxy_up(host: str = HOST, port: int = PORT, timeout: float = 2.0) -> bool:
    """True if something is listening on host:port (a cheap TCP connect probe)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def spawn_proxy() -> "subprocess.Popen | None":
    """Start the proxy detached from this watchdog so it outlives us.

    Uses the absolute interpreter path (never a bare ``python3`` — a service
    context has no shell PATH). Detaches via ``start_new_session`` on POSIX and
    ``DETACHED_PROCESS`` on Windows so a watchdog restart never signals the proxy.
    """
    if not os.path.exists(SCRIPT):
        _log(f"ERROR proxy script not found: {SCRIPT}")
        return None
    try:
        command = [PYTHON, SCRIPT]
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
        _log(f"spawned proxy pid={proc.pid} ({PYTHON} {SCRIPT})")
        return proc
    except Exception as exc:
        _log(f"ERROR failed to spawn proxy: {exc.__class__.__name__}")
        return None


def run(max_iterations: "int | None" = None) -> None:
    """Resident supervise loop. ``max_iterations`` bounds the loop for testing."""
    _log(
        f"watchdog starting: guard {HOST}:{PORT} every {CHECK_INTERVAL}s "
        f"(python={PYTHON}, script={SCRIPT})"
    )
    consecutive_failures = 0
    iterations = 0
    while True:
        up = is_proxy_up()
        sleep_for = CHECK_INTERVAL
        if not up:
            _log(f"proxy down on {HOST}:{PORT} — starting it")
            spawn_proxy()
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


if __name__ == "__main__":
    run()
