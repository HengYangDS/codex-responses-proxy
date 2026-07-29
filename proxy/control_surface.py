"""Loopback lifecycle HTTP projections for the DMX Responses proxy.

This module owns only the HTTP representation of runtime status, drain control,
and protocol-v2 handoff preparation.  The handoff state machine remains owned by
``handoff`` and process composition remains owned by the executable entrypoint.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Callable
from typing import Mapping
from typing import cast

import handoff
import runtime_state


@dataclass(frozen=True)
class Bindings:
    """Process-owned functions needed by the loopback control surface."""

    runtime_status: Callable[[], Mapping[str, object]]
    handoff_context: Callable[[], handoff.Context]


def _write_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: Mapping[str, object],
) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def send_status(handler: BaseHTTPRequestHandler, bindings: Bindings) -> None:
    """Write the process-local, secret-free runtime status response."""
    _write_json(handler, 200, bindings.runtime_status())


def set_drain(handler: BaseHTTPRequestHandler, enabled: bool) -> None:
    """Toggle Responses admission for an authorized loopback controller."""
    if not runtime_state.is_loopback_client(handler.client_address[0]):
        handler.send_error(403, "drain control is available only from loopback")
        return
    lease = handler.headers.get("X-DMX-Drain-Lease-Seconds") if enabled else None
    payload = runtime_state.set_draining(enabled, lease_seconds=lease)
    _write_json(handler, 200, payload)


def prepare_handoff(handler: BaseHTTPRequestHandler, bindings: Bindings) -> None:
    """Prepare one replacement and acknowledge READY before crossing COMMIT."""
    if not runtime_state.is_loopback_client(handler.client_address[0]):
        handler.send_error(403, "handoff control is available only from loopback")
        return
    try:
        content_length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        handler.send_error(400, "invalid handoff content length")
        return
    if content_length <= 0 or content_length > handoff.HANDOFF_CONTROL_MAX_BYTES:
        handler.send_error(413, "handoff request exceeds the control limit")
        return
    raw = handler.rfile.read(content_length)
    if len(raw) != content_length:
        handler.send_error(400, "incomplete handoff request")
        return
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        handler.send_error(400, "invalid handoff JSON")
        return
    if not isinstance(request, dict):
        handler.send_error(400, "handoff request must be an object")
        return
    allowed = {
        "transaction_id",
        "release",
        "serving_payload_sha256",
        "release_receipt_sha256",
        "manifest_sha256",
        "timeout_seconds",
        "lease_seconds",
    }
    if set(request) - allowed:
        handler.send_error(400, "handoff request contains unknown fields")
        return
    expected = {
        key: request.get(key)
        for key in (
            "transaction_id",
            "release",
            "serving_payload_sha256",
            "release_receipt_sha256",
            "manifest_sha256",
        )
    }
    context = bindings.handoff_context()
    if not handoff.disk_payload_matches_expected(expected, context):
        handler.send_error(409, "handoff request does not match the current disk payload")
        return
    try:
        timeout_seconds = min(120.0, max(0.1, float(request.get("timeout_seconds", 30.0))))
        lease_seconds = runtime_state.bounded_drain_lease_seconds(request.get("lease_seconds"))
        server = cast(ThreadingHTTPServer, handler.server)
        prepared = handoff.prepare(
            server,
            expected,
            context,
            timeout_seconds=timeout_seconds,
            lease_seconds=lease_seconds,
        )
    except handoff.HandoffError as exc:
        status = 409 if isinstance(exc, handoff.HandoffConflict) else 503
        _write_json(
            handler,
            status,
            {
                "ok": False,
                "error": "handoff_in_progress" if status == 409 else "handoff_prepare_failed",
            },
        )
        return
    _write_json(
        handler,
        202,
        {
            "ok": True,
            "state": "ready",
            "protocol_version": handoff.HANDOFF_PROTOCOL_VERSION,
            "child_pid": prepared["child"].process.pid,
            "transaction_id": expected["transaction_id"],
        },
    )
    handler.wfile.flush()
    threading.Thread(
        target=handoff.commit,
        args=(server, prepared, context),
        daemon=True,
        name="dmx-handoff-commit",
    ).start()
