"""Loopback HTTP fixtures shared by proxy transport contract tests."""

from __future__ import annotations

import threading
import urllib.request
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import dmx_responses_proxy as proxy
import responses_transport
import runtime_state

ScriptedResponse = tuple[int, bytes] | dict[str, Any]


def serve_proxy(
    responses: Sequence[ScriptedResponse], log_dir: str | Path
) -> tuple[int, list[bytes], object]:
    """Start scripted loopback servers and return port, bodies, and cleanup."""
    scripted = list(responses)
    received: list[bytes] = []
    scripted_lock = threading.Lock()

    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            received.append(self.rfile.read(length))
            with scripted_lock:
                response = scripted.pop(0)
            if isinstance(response, dict):
                status = int(response.get("status", 200))
                chunks = response.get("chunks", [])
                started = response.get("started_event")
                if started is not None:
                    started.set()
                release = response.get("release_event")
                if release is not None:
                    release.wait(timeout=5)
                self.send_response(status)
                self.send_header("Content-Type", response.get("content_type", "text/event-stream"))
                self.send_header("Connection", "close")
                self.end_headers()
                for chunk in chunks:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                self.close_connection = True
                return
            status, payload = response
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    old_upstream = responses_transport.UPSTREAM
    old_log_path = runtime_state.LOG_PATH
    responses_transport.UPSTREAM = f"http://127.0.0.1:{upstream.server_address[1]}"
    runtime_state.LOG_PATH = str(Path(log_dir) / "proxy.log")
    server = proxy.create_server(("127.0.0.1", 0))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    def cleanup() -> None:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=2)
        responses_transport.UPSTREAM = old_upstream
        runtime_state.LOG_PATH = old_log_path

    return server.server_address[1], received, cleanup


def request(proxy_port: int, body: bytes):
    """Post one Responses body to the loopback proxy without host proxies."""
    outbound = urllib.request.Request(
        f"http://127.0.0.1:{proxy_port}/v1/responses",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(outbound)
