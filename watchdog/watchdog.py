#!/usr/bin/env python3
"""watchdog — keep the dmx-responses-proxy alive, cross-platform.

Why this exists
---------------
The proxy is a plain HTTP server; if it dies (crash, an ``Address already in use``
on a bad restart, an OOM kill) nothing brings it back, and Codex silently falls
back to failing with ``encrypted content could not be verified``. The original
macOS deployment relied on a launchd ``KeepAlive`` for this — but that mechanism is
per-OS (launchd / systemd / Task Scheduler) and, as we learned the hard way, easy
to mis-wire (a missing plist, a ``disabled`` label) so it never actually guards.

This watchdog moves the self-heal logic into ONE piece of portable, testable code.
The platform service layer only has to do the simplest possible thing — start this
watchdog once at login and restart *it* if *it* dies. The harder job (is the proxy
up? if not, start it, but don't storm) lives here and behaves identically on macOS,
Linux, and Windows.

What it does
------------
A resident loop. Every ``CHECK_INTERVAL`` seconds:
  * TCP-probe 127.0.0.1:<port> (cheap; no HTTP request).
  * If reachable  -> the proxy is up, do nothing.
  * If unreachable -> spawn the proxy as a detached child using the ABSOLUTE python
    path recorded at install time, then back off before probing again.

Single-instance safety: because "is the proxy up?" is answered by whether the port
is bound, two watchdogs (or a watchdog racing a manual proxy) never double-spawn —
whoever loses the bind race just sees the port occupied and moves on. This is the
direct prevention of the ``Address already in use`` crash that motivated the tool.

Restart throttling: consecutive failed starts widen the backoff (CHECK_INTERVAL up
to MAX_BACKOFF) so a proxy that dies instantly on a bad config can't be fork-bombed.

Config (env, with install-time defaults baked into the service definition):
  DMX_PROXY_HOST            (default 127.0.0.1)
  DMX_PROXY_PORT            (default 8791)
  DMX_PROXY_PYTHON          absolute interpreter path (default: sys.executable)
  DMX_PROXY_SCRIPT          absolute path to dmx_responses_proxy.py
                            (default: sibling ../proxy/dmx_responses_proxy.py)
  DMX_WATCHDOG_INTERVAL     healthy-probe interval seconds (default 15)
  DMX_WATCHDOG_MAX_BACKOFF  max backoff after repeated failures (default 120)
  DMX_WATCHDOG_LOG          log file (default ~/.codex/log/dmx-watchdog.log)

Stdlib only. Runs on any Python 3.8+.
"""

from __future__ import annotations

import os
import sys
import time
import socket
import subprocess

HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
PYTHON = os.environ.get("DMX_PROXY_PYTHON", sys.executable)
_HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get(
    "DMX_PROXY_SCRIPT",
    os.path.join(os.path.dirname(_HERE), "proxy", "dmx_responses_proxy.py"),
)
CHECK_INTERVAL = float(os.environ.get("DMX_WATCHDOG_INTERVAL", "15"))
MAX_BACKOFF = float(os.environ.get("DMX_WATCHDOG_MAX_BACKOFF", "120"))
LOG_PATH = os.environ.get(
    "DMX_WATCHDOG_LOG", os.path.expanduser("~/.codex/log/dmx-watchdog.log")
)


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass
    try:
        sys.stderr.write(line)
    except Exception:
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
    kwargs = {}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            [PYTHON, SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            **kwargs,
        )
        _log(f"spawned proxy pid={proc.pid} ({PYTHON} {SCRIPT})")
        return proc
    except Exception as exc:
        _log(f"ERROR failed to spawn proxy: {exc}")
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
        if is_proxy_up():
            consecutive_failures = 0
            sleep_for = CHECK_INTERVAL
        else:
            _log(f"proxy down on {HOST}:{PORT} — starting it")
            spawn_proxy()
            # Give the proxy a moment to bind before the next probe, and widen the
            # window if it keeps failing to come up (bad config crash-loop guard).
            consecutive_failures += 1
            settle = min(MAX_BACKOFF, CHECK_INTERVAL * consecutive_failures)
            # Verify it actually bound; if not, the widened backoff applies.
            time.sleep(min(3.0, settle))
            if is_proxy_up():
                consecutive_failures = 0
                sleep_for = CHECK_INTERVAL
            else:
                sleep_for = settle
                _log(
                    f"proxy still down after start attempt "
                    f"#{consecutive_failures}; backing off {sleep_for:.0f}s"
                )

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
        time.sleep(sleep_for)


if __name__ == "__main__":
    run()
