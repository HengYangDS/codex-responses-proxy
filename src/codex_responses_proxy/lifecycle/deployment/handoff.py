"""Controller-side transport and proof for protocol-v2 rolling handoff.

This module owns the loopback handoff request, successor identity checks, and
bounded convergence or rollback observations. Installed :mod:`control` invokes
it only for same-payload reload. Source-side
:mod:`codex_responses_proxy.lifecycle.deployment.apply` invokes it after a released
transaction commits a different admitted transaction.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeGuard

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import digest
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory

HANDOFF_PROTOCOL_VERSION = 2
_MAX_BODY_BYTES = 64 * 1024
_TRANSPORT_MARGIN_SECONDS = 1.0
_RUNTIME_DIGEST_FIELDS = [
    "serving_payload_sha256",
    "release_receipt_sha256",
    "payload_manifest_sha256",
]

RuntimeSnapshot = dict[str, object]
RuntimeReader = Callable[[runtime_context.RuntimeContext], RuntimeSnapshot | None]


def _fields_match(actual: RuntimeSnapshot, expected: dict[str, object]) -> bool:
    return all(actual.get(field) == value for field, value in expected.items())


def _positive_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _available_transaction(state: object, transaction_id: object) -> bool:
    if state == "idle":
        return transaction_id is None
    if state != "finalized":
        return False
    return isinstance(transaction_id, str) and bool(transaction_id)


def runtime_supports_handoff(runtime: RuntimeSnapshot | None) -> bool:
    """Return whether a live health snapshot proves protocol-v2 readiness."""
    if not isinstance(runtime, dict):
        return False
    digests_valid = all(digest.is_sha256(runtime.get(field)) for field in _RUNTIME_DIGEST_FIELDS)
    pid = runtime.get("pid")
    release = runtime.get("release")
    return all(
        (
            _positive_int(pid),
            isinstance(release, str) and bool(release),
            digests_valid,
            _available_transaction(
                runtime.get("handoff_state"), runtime.get("handoff_transaction_id")
            ),
            _fields_match(
                runtime,
                {
                    "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
                    "accepting": True,
                    "draining": False,
                },
            ),
        )
    )


def expected_metadata(root: str) -> RuntimeSnapshot:
    """Read release, aggregate payload, receipt, and manifest identity."""
    try:
        manifest_path = os.path.join(root, inventory.MANIFEST_FILENAME)
        with open(manifest_path, encoding="utf-8") as handle:
            loaded: object = json.load(handle)
        if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
            raise TypeError("payload manifest must be an object with string keys")
        manifest = {key: value for key, value in loaded.items() if isinstance(key, str)}
        release = manifest["release"]
        serving_payload_sha256 = manifest["serving_payload_sha256"]
        release_receipt_sha256 = manifest["release_receipt_sha256"]
        manifest_sha256 = digest.sha256_file(Path(manifest_path))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise errors.InstallError(
            f"payload files are unavailable for a handoff transaction: {exc}"
        ) from exc
    if not isinstance(release, str) or not release:
        raise errors.InstallError("payload manifest has no release version")
    if not digest.is_sha256(serving_payload_sha256):
        raise errors.InstallError("payload manifest has no valid serving identity")
    if not digest.is_sha256(release_receipt_sha256):
        raise errors.InstallError("payload manifest has no valid release receipt identity")
    return {
        "transaction_id": uuid.uuid4().hex,
        "release": release,
        "serving_payload_sha256": serving_payload_sha256,
        "release_receipt_sha256": release_receipt_sha256,
        "manifest_sha256": manifest_sha256,
    }


def post_ready(
    ctx: runtime_context.RuntimeContext,
    expected: RuntimeSnapshot,
    *,
    lease_seconds: float | None = None,
    timeout_seconds: float = 5.0,
) -> RuntimeSnapshot:
    """POST the loopback handoff endpoint and require a protocol-v2 READY ack."""
    body = {
        "transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "serving_payload_sha256": expected["serving_payload_sha256"],
        "release_receipt_sha256": expected["release_receipt_sha256"],
        "manifest_sha256": expected["manifest_sha256"],
    }
    if lease_seconds is not None:
        body["lease_seconds"] = max(1, int(lease_seconds))
    body["timeout_seconds"] = max(1, min(120, int(timeout_seconds)))
    data = json.dumps(body).encode("utf-8")
    if len(data) > _MAX_BODY_BYTES:
        raise errors.InstallError("handoff request payload is too large")
    request = urllib.request.Request(
        runtime_config.loopback_url(ctx.port, "/control/handoff"),
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds + _TRANSPORT_MARGIN_SECONDS) as response:
            if response.status != 202:
                raise errors.InstallError(f"handoff control returned HTTP {response.status}")
            raw = response.read(_MAX_BODY_BYTES + 1)
            if len(raw) > _MAX_BODY_BYTES:
                raise errors.InstallError("handoff control response is too large")
            loaded_response: object = json.loads(raw)
    except errors.InstallError:
        raise
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise errors.InstallError(f"handoff control returned HTTP {code}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        raise errors.InstallError("handoff control is unavailable") from exc
    if not isinstance(loaded_response, dict) or not all(
        isinstance(key, str) for key in loaded_response
    ):
        raise errors.InstallError("handoff control returned an invalid response")
    response_payload: RuntimeSnapshot = {}
    for key, value in loaded_response.items():
        assert isinstance(key, str)
        response_payload[key] = value
    if not _fields_match(
        response_payload,
        {"ok": True, "state": "ready", "protocol_version": HANDOFF_PROTOCOL_VERSION},
    ):
        raise errors.InstallError(
            "handoff control did not return a protocol-v2 READY acknowledgement"
        )
    if response_payload.get("transaction_id") != expected["transaction_id"]:
        raise errors.InstallError("handoff control acknowledged an unexpected transaction")
    child_pid = response_payload.get("child_pid")
    if not _positive_int(child_pid):
        raise errors.InstallError("handoff control response is missing a valid child pid")
    return response_payload


def request(
    ctx: runtime_context.RuntimeContext,
    expected: RuntimeSnapshot,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
    lease_seconds: float = 30.0,
    source_listener: process.OwnedProcess | None = None,
) -> RuntimeSnapshot:
    """Ask one verified listener to hand off and prove the finalized successor.

    ``expected`` must bind the transaction identifier, release, aggregate
    serving-payload digest, release-receipt digest, and manifest digest.
    """
    listeners = _listener_pids(ctx, source_listener)
    if len(listeners) != 1:
        raise errors.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    ready = post_ready(
        ctx,
        expected,
        lease_seconds=lease_seconds,
        timeout_seconds=timeout_seconds,
    )
    child_pid = ready["child_pid"]
    if not _positive_int(child_pid):
        raise errors.InstallError("handoff control response lost its verified child pid")
    convergence_seconds = timeout_seconds * 3 + max(1.0, lease_seconds) + 5.0
    deadline = time.monotonic() + convergence_seconds
    while time.monotonic() < deadline:
        if process.verified_proxy_listener_pids(ctx) == [child_pid]:
            runtime = runtime_reader(ctx)
            if _runtime_matches(runtime, expected, child_pid):
                return {
                    "old_pid": old_pid,
                    "new_pid": child_pid,
                    "child_pid": child_pid,
                    "transaction_id": expected["transaction_id"],
                    "release": expected["release"],
                    "runtime": runtime,
                }
        time.sleep(0.1)
    raise errors.InstallError(
        f"handoff did not converge on finalized listener {child_pid} "
        f"within {convergence_seconds:g}s"
    )


def wait_for_rollback(
    ctx: runtime_context.RuntimeContext,
    old_runtime: RuntimeSnapshot,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> RuntimeSnapshot:
    """Confirm the exact old process resumed normal admission after ABORT."""
    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.verified_proxy_listener_pids(ctx) == [old_pid]:
            runtime = runtime_reader(ctx)
            if _old_runtime_resumed(runtime, old_runtime):
                assert runtime is not None
                return runtime
        time.sleep(0.1)
    raise errors.InstallError(
        f"old proxy listener {old_pid} did not resume after handoff rollback within {timeout_seconds:g}s"
    )


def resolve_after_controller_failure(
    ctx: runtime_context.RuntimeContext,
    old_runtime: RuntimeSnapshot,
    expected: RuntimeSnapshot,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    lease_seconds: float,
    source_listener: process.OwnedProcess | None = None,
) -> tuple[str, RuntimeSnapshot | None]:
    """Resolve caller failure without racing listener-owned finalization."""
    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds + max(1.0, lease_seconds) + 5.0
    while time.monotonic() < deadline:
        listeners = process.verified_proxy_listener_pids(ctx)
        source_listeners = (
            listeners if source_listener is None else _listener_pids(ctx, source_listener)
        )
        runtime = runtime_reader(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            if (
                _positive_int(pid)
                and pid != old_pid
                and listeners == [pid]
                and _runtime_matches(runtime, expected, pid)
            ):
                return "finalized", runtime
            if source_listeners == [old_pid] and _old_runtime_resumed(runtime, old_runtime):
                return "rolled_back", runtime
        time.sleep(0.1)
    return "unknown", None


def _listener_pids(
    ctx: runtime_context.RuntimeContext,
    source_listener: process.OwnedProcess | None,
) -> list[int]:
    if source_listener is None:
        return process.verified_proxy_listener_pids(ctx)
    if process.owned_process_alive(source_listener) and process.listener_pids(ctx.port) == [
        source_listener.pid
    ]:
        return [source_listener.pid]
    return []


def _runtime_matches(
    runtime: RuntimeSnapshot | None,
    expected: RuntimeSnapshot,
    child_pid: int,
) -> bool:
    """Require the transaction-complete successor identity."""
    if not isinstance(runtime, dict):
        return False
    return identity.runtime_payload_matches(runtime, expected) and _fields_match(
        runtime,
        {
            "pid": child_pid,
            "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
            "handoff_transaction_id": expected["transaction_id"],
            "handoff_state": "finalized",
            "accepting": True,
            "draining": False,
        },
    )


def _old_runtime_resumed(
    runtime: RuntimeSnapshot | None,
    old_runtime: RuntimeSnapshot,
) -> bool:
    if not isinstance(runtime, dict):
        return False
    return _fields_match(
        runtime,
        {
            "pid": old_runtime["pid"],
            "serving_payload_sha256": old_runtime.get("serving_payload_sha256"),
            "release_receipt_sha256": old_runtime.get("release_receipt_sha256"),
            "payload_manifest_sha256": old_runtime.get("payload_manifest_sha256"),
            "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "accepting": True,
            "draining": False,
        },
    )
