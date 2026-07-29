#!/usr/bin/env python3
"""Shared rolling-handoff test fixtures and loopback subprocess helpers."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import unittest
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
PROXY_ROOT = ROOT / "proxy"
for import_root in (str(ROOT), str(PROXY_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

from platform_adapters import common, payload  # noqa: E402
import dmx_responses_proxy as proxy_module  # noqa: E402
import handoff as handoff_module  # noqa: E402
import runtime_state as runtime_state_module  # noqa: E402


def free_port() -> int:
    """Return an unused loopback TCP port for an owned test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until(predicate: Callable[[], object], timeout: float, interval: float = 0.05) -> bool:
    """Poll a predicate until it becomes truthy or the bounded timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def proxy_is_up(port: int) -> bool:
    """Return whether a loopback TCP listener currently accepts connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def http_json(port: int, path: str, *, method: str = "GET", body=None, timeout: float = 3.0):
    """Issue an unproxied loopback request and decode its JSON response."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.status, json.loads(response.read())


def terminate_process(process: subprocess.Popen, timeout: float = 5) -> None:
    """Terminate an owned subprocess and bound the kill fallback."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def terminate_pid_best_effort(pid: int | None) -> None:
    """Best-effort cleanup for an owned handoff child identified by PID."""
    if pid is None:
        return
    try:
        common.terminate_pid(pid)
    except Exception:
        pass


def pid_alive(pid: int | None) -> bool:
    """Return whether an owned handoff child still has a process command."""
    if pid is None:
        return False
    try:
        return bool(common.process_command(pid))
    except Exception:
        return False


type UpstreamBehavior = tuple[int, bytes] | Callable[[BaseHTTPRequestHandler], None]


class ScriptedUpstream:
    """Run a real loopback HTTP upstream with a deterministic response queue."""

    def __init__(self):
        self.received: list[bytes] = []
        received = self.received
        outer = self
        self._lock = threading.Lock()
        self._queue: list[UpstreamBehavior] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                del format, args

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received.append(self.rfile.read(length))
                with outer._lock:
                    behavior: UpstreamBehavior = (
                        outer._queue.pop(0) if outer._queue else (200, b'{"id":"ok"}')
                    )
                if not isinstance(behavior, tuple):
                    callback = cast("Callable[[BaseHTTPRequestHandler], None]", behavior)
                    callback(self)
                    return
                status, response_payload = cast("tuple[int, bytes]", behavior)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_payload)))
                self.end_headers()
                self.wfile.write(response_payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def push(self, behavior: UpstreamBehavior) -> None:
        """Append one deterministic response behavior."""
        with self._lock:
            self._queue.append(behavior)

    def base_url(self) -> str:
        """Return the loopback base URL for this owned server."""
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        """Stop the server and join its owned thread."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def write_installed_payload(root: Path, *, release: str, port: int) -> common.InstallContext:
    """Build an installed-like temporary payload without touching the source tree."""
    install_dir = root / ".codex" / "dmx-proxy"
    for relative in payload.RUNTIME_PAYLOAD_FILES:
        source = ROOT / relative
        target = install_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (install_dir / "VERSION").write_text(release + "\n", encoding="utf-8")
    ctx = common.InstallContext(
        home=str(root),
        install_dir=str(install_dir),
        proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
        watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
        python=sys.executable,
        codex_config=str(root / ".codex" / "config.toml"),
        log_dir=str(root / ".codex" / "log"),
        port=port,
    )
    receipt = install_dir / payload.RELEASE_RECEIPT_FILENAME
    receipt.write_bytes(b'{"fixture":"handoff-subprocess"}\n')
    payload._write_payload_manifest_for_fixture(
        ctx,
        release_receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
    )
    return ctx


def installed_expected_metadata(ctx: common.InstallContext, transaction_id: str) -> dict:
    """Read the exact identity expected from a prepared child runtime."""
    manifest_path = Path(payload.payload_manifest_path(ctx))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "transaction_id": transaction_id,
        "release": manifest["release"],
        "serving_payload_sha256": manifest["serving_payload_sha256"],
        "release_receipt_sha256": manifest.get("release_receipt_sha256", "e" * 64),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "timeout_seconds": 10,
    }


def start_real_proxy(
    ctx: common.InstallContext, *, upstream_url: str, log_path: Path, extra_env: dict | None = None
) -> subprocess.Popen:
    """Start an installed-like proxy and prove its listener became reachable."""
    env = dict(os.environ)
    env["DMX_PROXY_HOST"] = "127.0.0.1"
    env["DMX_PROXY_PORT"] = str(ctx.port)
    env["DMX_UPSTREAM"] = upstream_url
    env["DMX_PROXY_LOG"] = str(log_path)
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [ctx.python, ctx.proxy_script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_until(lambda: proxy_is_up(ctx.port), timeout=10):
        terminate_process(process)
        raise RuntimeError("real proxy subprocess did not bind its listening socket in time")
    return process


def handoff_outcome_ready() -> threading.Event:
    """Return the current handoff session's typed completion event."""
    event = handoff_module._HANDOFF_SESSION["outcome_ready"]
    assert isinstance(event, threading.Event)
    return event


class HandoffTestCase(unittest.TestCase):
    """Reset handoff and runtime state for parent-side unit tests."""

    def setUp(self):
        self.p = handoff_module
        runtime_state_module.reset_for_test()
        self.p.reset_session_to_idle()
        self.context = proxy_module._handoff_context()
