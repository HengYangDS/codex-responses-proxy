"""Read status or reload the installed Codex Responses Proxy payload."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import command, projection
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.lifecycle.supervision.native_service import adapter
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import identity


def read_runtime(ctx: runtime_context.RuntimeContext) -> dict[str, object] | None:
    """Read the proxy's secret-free health snapshot from loopback only."""

    request = urllib.request.Request(
        runtime_config.loopback_url(ctx.port, "/healthz"),
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def status(ctx: runtime_context.RuntimeContext) -> dict:
    """Return non-secret runtime and transaction evidence without mutation."""

    installed_error: str | None = None
    try:
        installed = payload_state.read_installed(ctx)
    except errors.InstallError as exc:
        installed = None
        installed_error = str(exc)
    try:
        integrity_ok, integrity_detail = projection.verify_payload_manifest(ctx)
    except errors.InstallError as exc:
        integrity_ok, integrity_detail = False, str(exc)
    try:
        service = adapter().status(ctx)
    except (OSError, errors.InstallError, errors.UnsupportedPlatformError):
        service = "unknown"
    listeners = process.verified_proxy_listener_pids(ctx)
    runtime = read_runtime(ctx)
    pid = runtime.get("pid") if isinstance(runtime, dict) else None
    committed = identity.committed_payload(Path(ctx.executable)) if integrity_ok else None
    runtime_matches_payload = (
        isinstance(runtime, dict)
        and committed is not None
        and identity.runtime_payload_matches(runtime, committed.handoff())
        and runtime.get("accepting") is True
        and runtime.get("draining") is False
    )
    if type(pid) is not int or listeners != [pid] or not runtime_matches_payload:
        runtime = None
    installed_command = (
        Path(payload_state.require_command(installed))
        if installed is not None
        else Path(ctx.command)
    )
    command_state = command.status(installed_command, Path(ctx.executable))
    payload_transaction = payload_state.status(ctx)
    install_root = Path(ctx.install_dir)
    absent = (
        installed is None
        and not install_root.exists()
        and not install_root.is_symlink()
        and service == "absent"
        and not listeners
        and runtime is None
        and payload_transaction is None
        and command_state.get("state") == "absent"
    )
    transaction_invalid = (
        isinstance(payload_transaction, dict) and payload_transaction.get("state") == "invalid"
    )
    if installed_error is not None:
        lifecycle_state = "invalid"
        detail = installed_error
    elif transaction_invalid:
        assert isinstance(payload_transaction, dict)
        lifecycle_state = "invalid"
        detail = str(payload_transaction["detail"])
    elif absent:
        lifecycle_state = "not_installed"
        integrity_detail = "not installed"
        detail = "not installed"
    elif (
        integrity_ok
        and installed is not None
        and service == "running"
        and runtime is not None
        and command_state.get("state") == "owned"
        and payload_transaction is None
    ):
        lifecycle_state = "running"
        detail = "healthy"
    elif isinstance(payload_transaction, dict) and payload_transaction.get("state") in {
        "prepared",
        "committed",
        "recovery_required",
    }:
        lifecycle_state = "recovery_required"
        detail = "payload recovery is required"
    else:
        lifecycle_state = "degraded"
        if not integrity_ok:
            detail = integrity_detail
        elif service != "running":
            detail = f"native service is {service}"
        elif runtime is None:
            detail = "listener runtime identity is unavailable"
        elif command_state.get("state") != "owned":
            detail = "native command ownership is unavailable"
        else:
            detail = "installation is degraded"
    return {
        "state": lifecycle_state,
        "detail": detail,
        "release": payload_state.require_version(installed) if installed is not None else None,
        "command": command_state,
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "service": service,
        "listener_pids": listeners,
        "runtime": runtime,
        "payload_transaction": payload_transaction,
    }


def reload(ctx: runtime_context.RuntimeContext, timeout_seconds: float = 30.0) -> dict[str, object]:
    """Reload the same installed protocol-v2 payload through live handoff."""

    installed = payload_state.read_installed(ctx)
    install_root = Path(ctx.install_dir)
    if installed is None and not install_root.exists() and not install_root.is_symlink():
        raise errors.NotInstalledError
    transaction_state = payload_state.status(ctx)
    if transaction_state is not None:
        if transaction_state.get("state") == "invalid":
            raise errors.RecoveryStateError(
                "payload transaction evidence is invalid; preserve it for diagnosis"
            )
        raise errors.RecoveryRequiredError("complete payload recovery before reloading")
    runtime = read_runtime(ctx)
    if not handoff.runtime_supports_handoff(runtime):
        raise errors.InstallError("installed runtime is not healthy enough to reload")
    assert runtime is not None
    integrity_ok, integrity_detail = projection.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise errors.InstallError(
            f"payload integrity check failed before handoff reload: {integrity_detail}"
        )
    expected = handoff.expected_metadata(ctx.install_dir)
    lease_seconds = max(1.0, timeout_seconds)
    try:
        result = handoff.request(
            ctx,
            expected,
            runtime_reader=read_runtime,
            timeout_seconds=timeout_seconds,
            lease_seconds=lease_seconds,
        )
    except BaseException as handoff_exc:
        try:
            resolution, resolved_runtime = handoff.resolve_after_controller_failure(
                ctx,
                runtime,
                expected,
                runtime_reader=read_runtime,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
        except (OSError, RuntimeError):
            resolution, resolved_runtime = "unknown", None
        if resolution == "finalized" and isinstance(resolved_runtime, dict):
            return {
                "state": "reloaded",
                "old_pid": runtime["pid"],
                "new_pid": resolved_runtime["pid"],
                "transaction_id": expected["transaction_id"],
                "recovered_after_controller_failure": True,
            }
        if resolution == "unknown":
            raise errors.InstallError(
                "reload handoff outcome is unconfirmed; inspect transaction-bound listener health"
            ) from handoff_exc
        raise
    return {
        "state": "reloaded",
        "old_pid": result["old_pid"],
        "new_pid": result["child_pid"],
    }
