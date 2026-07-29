"""Loopback HTTP server and route dispatch for the DMX Responses proxy.

The handler owns only method/path routing.  Upstream request orchestration and
lifecycle controls are delegated to their semantic owners through immutable
process bindings supplied by the executable entrypoint.
"""

from __future__ import annotations

import socket
from typing import Any
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

import control_surface
import responses_transport
import runtime_state


@dataclass(frozen=True)
class Bindings:
    """Process-owned control functions used by every handler instance."""

    control: control_surface.Bindings
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
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def get_request(self) -> tuple[socket.socket, object]:
        request, address = super().get_request()
        try:
            request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        return request, address

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        runtime_state.begin_handler()
        try:
            super().process_request_thread(request, client_address)
        finally:
            runtime_state.end_handler()

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys

        error = sys.exception()
        if isinstance(error, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            runtime_state.log(
                f"client_closed_mid_request exception={runtime_state.safe_exception_label(error)}"
            )
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    """Route loopback HTTP methods to transport and lifecycle owners."""

    protocol_version = "HTTP/1.1"
    server_version = "dmx-responses-proxy/0+unconfigured"

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base server's unstructured stderr access log."""
        del format, args

    def do_POST(self) -> None:
        if self.path == "/control/drain":
            control_surface.set_drain(self, True)
        elif self.path == "/control/handoff":
            control_surface.prepare_handoff(self, _bindings().control)
        else:
            responses_transport.relay(self, "POST")

    def do_GET(self) -> None:
        if self.path == "/healthz":
            control_surface.send_status(self, _bindings().control)
        else:
            responses_transport.relay(self, "GET")

    def do_DELETE(self) -> None:
        if self.path == "/control/drain":
            control_surface.set_drain(self, False)
        else:
            responses_transport.relay(self, "DELETE")

    def do_PATCH(self) -> None:
        responses_transport.relay(self, "PATCH")

    def do_PUT(self) -> None:
        responses_transport.relay(self, "PUT")


def server_from_listener(listener: socket.socket) -> ResilientProxyServer:
    """Create a configured server around one already-bound handoff listener."""
    address = listener.getsockname()
    server = ResilientProxyServer(address, Handler, bind_and_activate=False)
    try:
        server.socket.close()
    except OSError:
        pass
    server.socket = listener
    server.server_address = address
    return server
