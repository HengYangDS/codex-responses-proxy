#!/usr/bin/env python3
"""Executable composition root for the local DMX Responses compatibility proxy.

Pure request policies, SSE framing, upstream orchestration, lifecycle HTTP
controls, and server routing live in dedicated modules.  This file owns only
release identity, process bindings, and startup.
"""

from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

import control_surface
import handoff
import http_surface
import payload_identity
import responses_transport
import runtime_state
import sse_transport
import empty_response
import input_compatibility
import response_failed
import responses_rewrite

HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
_SERVER_INSTANCE: ThreadingHTTPServer | None = None


_LOADED_PAYLOAD = payload_identity.freeze_loaded_payload(
    Path(__file__),
    {
        "proxy/control_surface.py": control_surface,
        "proxy/empty_response.py": empty_response,
        "proxy/handoff.py": handoff,
        "proxy/http_surface.py": http_surface,
        "proxy/input_compatibility.py": input_compatibility,
        "proxy/payload_identity.py": payload_identity,
        "proxy/response_failed.py": response_failed,
        "proxy/responses_rewrite.py": responses_rewrite,
        "proxy/responses_transport.py": responses_transport,
        "proxy/runtime_state.py": runtime_state,
        "proxy/sse_transport.py": sse_transport,
    },
)
_LOADED_RELEASE = payload_identity.freeze_release(Path(__file__))


def serving_payload_sha256() -> str | None:
    """Return the aggregate serving identity frozen before listener startup."""
    return None if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.serving_payload_sha256


def release_receipt_sha256() -> str | None:
    """Return the released-source receipt identity frozen before startup."""
    return None if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.release_receipt_sha256


def release_version() -> str:
    """Return the packaged release identity frozen before listener startup."""
    return _LOADED_RELEASE


def _set_server_instance(server: ThreadingHTTPServer) -> None:
    global _SERVER_INSTANCE
    _SERVER_INSTANCE = server


def _handoff_context() -> handoff.Context:
    """Bind the rolling-handoff state machine to process-owned primitives."""
    return handoff.Context(
        proxy_script=Path(__file__).resolve(),
        release_version=release_version,
        serving_payload_sha256=serving_payload_sha256,
        release_receipt_sha256=release_receipt_sha256,
        response_gate_lock=runtime_state.response_gate_lock(),
        draining=runtime_state.is_draining,
        active_responses=runtime_state.active_responses,
        active_handlers=runtime_state.active_handlers,
        bounded_lease_seconds=runtime_state.bounded_drain_lease_seconds,
        set_draining=runtime_state.set_draining,
        log=runtime_state.log,
        server_factory=http_surface.server_from_listener,
        set_server_instance=_set_server_instance,
    )


def runtime_status() -> dict[str, object]:
    """Compose process-local state with rolling-handoff runtime identity."""
    return runtime_state.status(
        release=release_version(),
        serving_payload_sha256=serving_payload_sha256(),
        release_receipt_sha256=release_receipt_sha256(),
        runtime_identity=handoff.runtime_identity(_handoff_context()),
    )


def configure_http_surface() -> None:
    """Install immutable process bindings into the HTTP route owner."""
    http_surface.configure(
        http_surface.Bindings(
            control=control_surface.Bindings(
                runtime_status=runtime_status,
                handoff_context=_handoff_context,
            ),
            server_version=f"dmx-responses-proxy/{release_version()}",
        )
    )


def create_server(address: tuple[str, int] | None = None) -> http_surface.ResilientProxyServer:
    """Create one configured loopback server for startup and integration tests."""
    configure_http_surface()
    return http_surface.ResilientProxyServer(address or (HOST, PORT), http_surface.Handler)


def main() -> None:
    """Run the normal listener or a protocol-v2 handoff child."""
    configure_http_surface()
    if os.environ.get("DMX_HANDOFF_CHILD") == "1" or "--handoff-child" in sys.argv[1:]:
        raise SystemExit(handoff.run_child(_handoff_context()))
    runtime_state.log(
        f"starting dmx-responses-proxy listener={HOST}:{PORT} "
        f"responses_max_concurrency={runtime_state.RESPONSES_MAX_CONCURRENCY} "
        f"upstream_timeout={responses_transport.UPSTREAM_TIMEOUT} "
        f"read_timeout={sse_transport.UPSTREAM_READ_TIMEOUT} "
        f"log_max_bytes={runtime_state.LOG_MAX_BYTES} "
        f"log_backup_count={runtime_state.LOG_BACKUP_COUNT}"
    )
    global _SERVER_INSTANCE
    server = create_server()
    _SERVER_INSTANCE = server
    try:
        handoff.serve_with_resume(server, _handoff_context())
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
