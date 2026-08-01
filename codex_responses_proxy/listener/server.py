"""Loopback HTTP server and route dispatch for Codex Responses Proxy.

The handler owns only method/path routing.  Upstream request orchestration and
lifecycle controls are delegated to their semantic owners through immutable
process bindings supplied by the executable entrypoint.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any

from codex_responses_proxy.listener import control
from codex_responses_proxy.runtime import admission, logging
from codex_responses_proxy.transport import responses


@dataclass(frozen=True)
class Bindings:
    """Process-owned control functions used by every handler instance."""

    control: control.Bindings
    server_version: str


_BINDINGS: Bindings | None = None


def configure(bindings: Bindings) -> None:
    """Install the immutable process bindings before constructing a server."""
    global _BINDINGS
    if _BINDINGS is not None and _BINDINGS != bindings:
        raise RuntimeError("HTTP surface is already configured")
    _BINDINGS = bindings
    Handler.server_version = bindings.server_version


def _bindings() -> Bindings:
    if _BINDINGS is None:
        raise RuntimeError("HTTP surface is not configured")
    return _BINDINGS


class ResilientProxyServer(ThreadingHTTPServer):
    """Threading HTTP server hardened for concurrent local Responses streams."""

    request_queue_size = 256
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self) -> None:
        super().server_bind()
        _disable_nagle(self.socket)

    def get_request(self) -> tuple[socket.socket, object]:
        request, address = super().get_request()
        _disable_nagle(request)
        return request, address

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        admission.begin_handler()
        try:
            super().process_request_thread(request, client_address)
        finally:
            admission.end_handler()

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys

        error = sys.exception()
        if isinstance(error, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            logging.log(
                f"client_closed_mid_request exception={logging.safe_exception_label(error)}"
            )
            return
        super().handle_error(request, client_address)


def _disable_nagle(connection: socket.socket) -> None:
    try:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    """Route loopback HTTP methods to transport and lifecycle owners."""

    protocol_version = "HTTP/1.1"
    server_version = "codex-responses-proxy/0+unconfigured"

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base server's unstructured stderr access log."""
        del format, args

    def do_POST(self) -> None:
        if self.path == "/control/drain":
            control.set_drain(self, True)
        elif self.path == "/control/handoff":
            control.prepare_handoff(self, _bindings().control)
        else:
            responses.relay(self, "POST")

    def do_GET(self) -> None:
        if self.path == "/healthz":
            control.send_status(self, _bindings().control)
        else:
            responses.relay(self, "GET")

    def do_DELETE(self) -> None:
        if self.path == "/control/drain":
            control.set_drain(self, False)
        else:
            responses.relay(self, "DELETE")

    def do_PATCH(self) -> None:
        responses.relay(self, "PATCH")

    def do_PUT(self) -> None:
        responses.relay(self, "PUT")


def server_from_listener(listener: socket.socket) -> ResilientProxyServer:
    """Create a configured server around one already-bound handoff listener."""
    address = listener.getsockname()
    server = ResilientProxyServer(address, Handler, bind_and_activate=False)
    server.socket.close()
    server.socket = listener
    server.server_address = address
    return server
