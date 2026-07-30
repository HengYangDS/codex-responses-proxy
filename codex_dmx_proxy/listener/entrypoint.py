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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import (
    control,
    handoff,
    identity,
    responses,
    server,
    sse,
    state,
)

HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
_SERVER_INSTANCE: ThreadingHTTPServer | None = None


_LOADED_PAYLOAD = identity.freeze_loaded_payload(Path(__file__))


def serving_payload_sha256() -> str | None:
    """Return the aggregate serving identity frozen before listener startup."""
    return None if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.serving_payload_sha256


def release_receipt_sha256() -> str | None:
    """Return the released-source receipt identity frozen before startup."""
    return None if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.release_receipt_sha256


def payload_manifest_sha256() -> str | None:
    """Return the manifest identity frozen before listener startup."""

    return None if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.manifest_sha256


def release_version() -> str:
    """Return the release identity frozen with the serving payload."""

    return "0+unknown" if _LOADED_PAYLOAD is None else _LOADED_PAYLOAD.release


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
        payload_manifest_sha256=payload_manifest_sha256,
        committed_payload=lambda: identity.committed_payload(Path(__file__)),
        response_gate_lock=state.response_gate_lock(),
        draining=state.is_draining,
        active_responses=state.active_responses,
        active_handlers=state.active_handlers,
        bounded_lease_seconds=state.bounded_drain_lease_seconds,
        set_draining=state.set_draining,
        log=state.log,
        server_factory=server.server_from_listener,
        set_server_instance=_set_server_instance,
    )


def runtime_status() -> dict[str, object]:
    """Compose process-local state with rolling-handoff runtime identity."""
    return state.status(
        release=release_version(),
        serving_payload_sha256=serving_payload_sha256(),
        release_receipt_sha256=release_receipt_sha256(),
        runtime_identity=handoff.runtime_identity(_handoff_context()),
    )


def configure_http_surface() -> None:
    """Install immutable process bindings into the HTTP route owner."""
    server.configure(
        server.Bindings(
            control=control.Bindings(
                runtime_status=runtime_status,
                handoff_context=_handoff_context,
            ),
            server_version=f"dmx-responses-proxy/{release_version()}",
        )
    )


def create_server(address: tuple[str, int] | None = None) -> server.ResilientProxyServer:
    """Create one configured loopback server for startup and integration tests."""
    configure_http_surface()
    return server.ResilientProxyServer(address or (HOST, PORT), server.Handler)


def main() -> None:
    """Run the normal listener or a protocol-v2 handoff child."""
    configure_http_surface()
    if os.environ.get("DMX_HANDOFF_CHILD") == "1" or "--handoff-child" in sys.argv[1:]:
        raise SystemExit(handoff.run_child(_handoff_context()))
    state.log(
        f"starting dmx-responses-proxy listener={HOST}:{PORT} "
        f"responses_max_concurrency={state.RESPONSES_MAX_CONCURRENCY} "
        f"upstream_timeout={responses.UPSTREAM_TIMEOUT} "
        f"read_timeout={sse.UPSTREAM_READ_TIMEOUT} "
        f"log_max_bytes={state.LOG_MAX_BYTES} "
        f"log_backup_count={state.LOG_BACKUP_COUNT}"
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
