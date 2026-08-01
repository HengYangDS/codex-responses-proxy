"""Loopback HTTP fixtures shared by proxy transport contract tests."""

from __future__ import annotations

import contextlib
import tempfile
import threading
import urllib.request
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from codex_responses_proxy.runtime import logging
from codex_responses_proxy.transport import responses as response_transport
from codex_responses_proxy.listener import entrypoint as proxy
from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.providers.policies import dmxapi as dmxapi_policy

ScriptedResponse = tuple[int, bytes] | dict[str, Any]


def serve_proxy(
    responses: Sequence[ScriptedResponse], log_dir: str | Path
) -> tuple[int, list[bytes], Callable[[], None]]:
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
    old_registry = response_transport.PROVIDERS
    test_upstream = f"http://127.0.0.1:{upstream.server_address[1]}"
    response_transport.PROVIDERS = provider_registry.Registry(
        profiles={
            "dmxapi": provider_registry.Profile(
                "dmxapi",
                test_upstream,
                cast(provider_registry.EmptyResponsePolicy, dmxapi_policy),
            ),
            "ucloud": provider_registry.Profile("ucloud", test_upstream),
            "aihubmix": provider_registry.Profile("aihubmix", test_upstream),
        },
    )
    old_log_path = logging.LOG_PATH
    logging.LOG_PATH = str(Path(log_dir) / "proxy.log")
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
        response_transport.PROVIDERS = old_registry
        logging.LOG_PATH = old_log_path

    return server.server_address[1], received, cleanup


@contextlib.contextmanager
def running_proxy(responses: Sequence[ScriptedResponse]):
    """Yield a scripted loopback proxy and always release both servers."""
    with tempfile.TemporaryDirectory() as log_dir:
        port, received, cleanup = serve_proxy(responses, log_dir)
        try:
            yield port, received
        finally:
            cleanup()


def request(proxy_port: int, body: bytes, *, path: str = "/dmxapi/v1/responses"):
    """Post one Responses body to the loopback proxy without host proxies."""
    outbound = urllib.request.Request(
        f"http://127.0.0.1:{proxy_port}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(outbound)
