"""Read status or reload the installed Codex Responses Proxy payload."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import projection, state as payload_state
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.lifecycle.supervision.native_service import adapter
from codex_responses_proxy.runtime import config as runtime_config


def _context(port: int = runtime_config.DEFAULT_PORT) -> runtime_context.RuntimeContext:
    """Project the installed product without consulting client configuration."""

    return runtime_context.create(port=port)


def _installed_release(ctx: runtime_context.RuntimeContext) -> str | None:
    try:
        with open(os.path.join(ctx.install_dir, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _runtime_metrics(ctx: runtime_context.RuntimeContext) -> dict | None:
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

    try:
        integrity_ok, integrity_detail = projection.verify_payload_manifest(ctx)
    except errors.InstallError as exc:
        integrity_ok, integrity_detail = False, str(exc)
    try:
        service = adapter().status(ctx)
    except (OSError, errors.InstallError, errors.UnsupportedPlatform):
        service = "unknown"
    listeners = process.verified_proxy_listener_pids(ctx)
    return {
        "release": _installed_release(ctx),
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "service": service,
        "listener_pids": listeners,
        "runtime": _runtime_metrics(ctx),
        "payload_transaction": payload_state.status(ctx),
    }


def reload(ctx: runtime_context.RuntimeContext, timeout_seconds: float = 30.0) -> dict[str, object]:
    """Reload the same installed protocol-v2 payload through live handoff."""

    runtime = _runtime_metrics(ctx)
    if not handoff.runtime_supports_handoff(runtime):
        raise errors.InstallError("installed runtime does not support transactional reload")
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
            runtime_reader=_runtime_metrics,
            timeout_seconds=timeout_seconds,
            lease_seconds=lease_seconds,
        )
    except BaseException as handoff_exc:
        try:
            resolution, resolved_runtime = handoff.resolve_after_controller_failure(
                ctx,
                runtime,
                expected,
                runtime_reader=_runtime_metrics,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
        except BaseException:
            resolution, resolved_runtime = "unknown", None
        if resolution == "finalized" and isinstance(resolved_runtime, dict):
            return {
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
    return {"old_pid": result["old_pid"], "new_pid": result["child_pid"]}
