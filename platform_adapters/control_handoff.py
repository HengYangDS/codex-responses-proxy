"""Controller-side transport and proof for protocol-v2 rolling handoff.

This module owns the loopback handoff request, successor identity checks, and
bounded convergence or rollback observations. Installed :mod:`control` invokes
it only for same-payload reload. Source-side :mod:`platform_adapters.deployment`
invokes it after a released transaction commits a different admitted payload.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable

from . import common
from . import payload

HANDOFF_PROTOCOL_VERSION = 2
_MAX_BODY_BYTES = 64 * 1024

RuntimeReader = Callable[[common.InstallContext], dict | None]


def runtime_supports_handoff(runtime: dict | None) -> bool:
    """Return whether a live health snapshot proves protocol-v2 readiness."""

    if not isinstance(runtime, dict):
        return False
    pid = runtime.get("pid")
    serving_payload = runtime.get("serving_payload_sha256")
    release_receipt = runtime.get("release_receipt_sha256")
    manifest = runtime.get("payload_manifest_sha256")
    release = runtime.get("release")
    handoff_state = runtime.get("handoff_state")
    transaction_id = runtime.get("handoff_transaction_id")
    transaction_state_ok = (handoff_state == "idle" and transaction_id is None) or (
        handoff_state == "finalized" and isinstance(transaction_id, str) and bool(transaction_id)
    )
    return (
        runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
        and isinstance(pid, int)
        and not isinstance(pid, bool)
        and pid > 0
        and isinstance(release, str)
        and bool(release)
        and _valid_sha256(serving_payload)
        and _valid_sha256(release_receipt)
        and _valid_sha256(manifest)
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
        and transaction_state_ok
    )


def expected_metadata(root: str) -> dict:
    """Read release, aggregate payload, receipt, and manifest identity."""

    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as handle:
            release = handle.read().strip()
    except OSError as exc:
        raise common.InstallError(f"payload VERSION is unavailable: {exc}") from exc
    if not release:
        raise common.InstallError("payload has no release version")
    try:
        manifest_path = os.path.join(root, payload.PAYLOAD_MANIFEST_FILENAME)
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        serving_payload_sha256 = manifest["serving_payload_sha256"]
        release_receipt_sha256 = manifest["release_receipt_sha256"]
        manifest_sha256 = _sha256_file(manifest_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise common.InstallError(
            f"payload files are unavailable for a handoff transaction: {exc}"
        ) from exc
    if not _valid_sha256(serving_payload_sha256):
        raise common.InstallError("payload manifest has no valid serving identity")
    if not _valid_sha256(release_receipt_sha256):
        raise common.InstallError("payload manifest has no valid release receipt identity")
    return {
        "transaction_id": uuid.uuid4().hex,
        "release": release,
        "serving_payload_sha256": serving_payload_sha256,
        "release_receipt_sha256": release_receipt_sha256,
        "manifest_sha256": manifest_sha256,
    }


def post_ready(
    ctx: common.InstallContext,
    expected: dict,
    *,
    lease_seconds: float | None = None,
    timeout_seconds: float = 5.0,
) -> dict:
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
        raise common.InstallError("handoff request payload is too large")
    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/control/handoff",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 202:
                raise common.InstallError(f"handoff control returned HTTP {response.status}")
            raw = response.read(_MAX_BODY_BYTES + 1)
            if len(raw) > _MAX_BODY_BYTES:
                raise common.InstallError("handoff control response is too large")
            response_payload = json.loads(raw)
    except common.InstallError:
        raise
    except urllib.error.HTTPError as exc:
        raise common.InstallError(f"handoff control returned HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        raise common.InstallError("handoff control is unavailable") from exc
    if not isinstance(response_payload, dict):
        raise common.InstallError("handoff control returned an invalid response")
    if (
        response_payload.get("ok") is not True
        or response_payload.get("state") != "ready"
        or response_payload.get("protocol_version") != HANDOFF_PROTOCOL_VERSION
    ):
        raise common.InstallError(
            "handoff control did not return a protocol-v2 READY acknowledgement"
        )
    if response_payload.get("transaction_id") != expected["transaction_id"]:
        raise common.InstallError("handoff control acknowledged an unexpected transaction")
    child_pid = response_payload.get("child_pid")
    if not isinstance(child_pid, int) or isinstance(child_pid, bool) or child_pid <= 0:
        raise common.InstallError("handoff control response is missing a valid child pid")
    return response_payload


def request(
    ctx: common.InstallContext,
    expected: dict,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
    lease_seconds: float = 30.0,
) -> dict:
    """Ask one verified listener to hand off and prove the exact successor.

    ``expected`` must bind the transaction identifier, release, aggregate
    serving-payload digest, release-receipt digest, and manifest digest.
    """

    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    ready = post_ready(
        ctx,
        expected,
        lease_seconds=lease_seconds,
        timeout_seconds=min(timeout_seconds, 10.0),
    )
    child_pid = ready["child_pid"]
    convergence_seconds = timeout_seconds * 3 + max(1.0, lease_seconds) + 5.0
    deadline = time.monotonic() + convergence_seconds
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) == [child_pid]:
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
            raise common.InstallError(
                f"handoff child {child_pid} health snapshot did not match the expected transaction"
            )
        time.sleep(0.1)
    raise common.InstallError(
        f"handoff did not converge on verified listener {child_pid} within {convergence_seconds:g}s"
    )


def wait_for_rollback(
    ctx: common.InstallContext,
    old_runtime: dict,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict:
    """Confirm the exact old process resumed normal admission after ABORT."""

    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) == [old_pid]:
            runtime = runtime_reader(ctx)
            if _old_runtime_resumed(runtime, old_runtime):
                assert runtime is not None
                return runtime
        time.sleep(0.1)
    raise common.InstallError(
        f"old proxy listener {old_pid} did not resume after handoff rollback within {timeout_seconds:g}s"
    )


def resolve_after_controller_failure(
    ctx: common.InstallContext,
    old_runtime: dict,
    expected: dict,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    lease_seconds: float,
) -> tuple[str, dict | None]:
    """Resolve caller failure without racing listener-owned finalization."""

    old_pid = old_runtime["pid"]
    deadline = time.monotonic() + timeout_seconds + max(1.0, lease_seconds) + 5.0
    while time.monotonic() < deadline:
        listeners = common.verified_proxy_listener_pids(ctx)
        runtime = runtime_reader(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            if (
                isinstance(pid, int)
                and pid != old_pid
                and listeners == [pid]
                and _runtime_matches(runtime, expected, pid)
            ):
                return "finalized", runtime
            if listeners == [old_pid] and _old_runtime_resumed(runtime, old_runtime):
                return "rolled_back", runtime
        time.sleep(0.1)
    return "unknown", None


def _runtime_matches(runtime: dict | None, expected: dict, child_pid: int) -> bool:
    if not isinstance(runtime, dict):
        return False
    return (
        runtime.get("pid") == child_pid
        and runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
        and runtime.get("handoff_transaction_id") == expected["transaction_id"]
        and runtime.get("release") == expected["release"]
        and runtime.get("serving_payload_sha256") == expected["serving_payload_sha256"]
        and runtime.get("release_receipt_sha256") == expected["release_receipt_sha256"]
        and runtime.get("payload_manifest_sha256") == expected["manifest_sha256"]
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
        and runtime.get("handoff_state") in {"serving", "finalized"}
    )


def _old_runtime_resumed(runtime: dict | None, old_runtime: dict) -> bool:
    if not isinstance(runtime, dict):
        return False
    return (
        runtime.get("pid") == old_runtime["pid"]
        and runtime.get("serving_payload_sha256") == old_runtime.get("serving_payload_sha256")
        and runtime.get("release_receipt_sha256") == old_runtime.get("release_receipt_sha256")
        and runtime.get("payload_manifest_sha256") == old_runtime.get("payload_manifest_sha256")
        and runtime.get("handoff_protocol_version") == HANDOFF_PROTOCOL_VERSION
        and runtime.get("handoff_state") == "idle"
        and runtime.get("handoff_transaction_id") is None
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
    )


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
