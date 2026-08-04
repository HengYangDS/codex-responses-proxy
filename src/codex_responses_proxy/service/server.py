"""Loopback HTTP server and route dispatch for Codex Responses Proxy.

The handler owns only method/path routing.  Upstream request orchestration and
lifecycle controls are delegated to their semantic owners through immutable
process bindings supplied by the executable entrypoint.
"""

from __future__ import annotations

import socket
import socketserver
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any, cast

from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.relay import admission, operational_log
from codex_responses_proxy.relay import responses
from codex_responses_proxy.service import control


@dataclass(frozen=True)
class Bindings:
    """Immutable process dependencies owned by one HTTP server instance."""

    control: control.Bindings
    providers: provider_registry.Registry
    server_version: str


class ResilientProxyServer(ThreadingHTTPServer):
    """Threading HTTP server hardened for concurrent local Responses streams."""

    request_queue_size = 256
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        bindings: Bindings,
        bind_and_activate: bool = True,
    ) -> None:
        self.bindings = bindings
        super().__init__(server_address, request_handler_class, bind_and_activate)

    def server_bind(self) -> None:
        # This product is loopback-only.  HTTPServer.server_bind() performs a
        # reverse/FQDN lookup solely to populate presentation attributes; that
        # lookup can block listener admission on hosts with degraded DNS.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = cast(str, host)
        self.server_port = port
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
            operational_log.log(
                f"client_closed_mid_request exception={operational_log.safe_exception_label(error)}"
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

    def version_string(self) -> str:
        """Return the immutable release identity bound to this server."""

        return cast(ResilientProxyServer, self.server).bindings.server_version

    def _bindings(self) -> Bindings:
        return cast(ResilientProxyServer, self.server).bindings

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base server's unstructured stderr access log."""
        del format, args

    def do_POST(self) -> None:
        if self.path == "/control/drain":
            control.set_drain(self, True)
        elif self.path == "/control/handoff":
            control.prepare_handoff(self, self._bindings().control)
        else:
            responses.relay(self, "POST", self._bindings().providers)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            control.send_status(self, self._bindings().control)
        else:
            responses.relay(self, "GET", self._bindings().providers)

    def do_DELETE(self) -> None:
        if self.path == "/control/drain":
            control.set_drain(self, False)
        else:
            responses.relay(self, "DELETE", self._bindings().providers)

    def do_PATCH(self) -> None:
        responses.relay(self, "PATCH", self._bindings().providers)

    def do_PUT(self) -> None:
        responses.relay(self, "PUT", self._bindings().providers)


def server_from_listener(listener: socket.socket, bindings: Bindings) -> ResilientProxyServer:
    """Create a configured server around one already-bound handoff listener."""
    address = listener.getsockname()
    server = ResilientProxyServer(address, Handler, bindings, bind_and_activate=False)
    server.socket.close()
    server.socket = listener
    server.server_address = address
    server.server_name = cast(str, address[0])
    server.server_port = address[1]
    return server
