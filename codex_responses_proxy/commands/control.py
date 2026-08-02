#!/usr/bin/env python3
"""Read status or reload the installed Codex Responses Proxy payload."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import urllib.error
import urllib.request

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

from codex_responses_proxy import errors
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.supervision import process  # noqa: E402
from codex_responses_proxy.deployment import handoff  # noqa: E402
from codex_responses_proxy.payload import projection, state as payload_state  # noqa: E402
from codex_responses_proxy.supervision.native_service import adapter  # noqa: E402


def _context(port: int = runtime_config.DEFAULT_PORT) -> runtime_context.RuntimeContext:
    """Project the installed product without consulting client configuration."""

    return runtime_context.create(python=sys.executable, port=port)


def _installed_release(ctx: runtime_context.RuntimeContext) -> str | None:
    try:
        with open(os.path.join(ctx.install_dir, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _runtime_metrics(ctx: runtime_context.RuntimeContext) -> dict | None:
    """Read the proxy's secret-free health snapshot from loopback only."""

    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/healthz",
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

    integrity_ok, integrity_detail = projection.verify_payload_manifest(ctx)
    try:
        service = adapter().status(ctx)
    except Exception:
        service = "unknown"
    return {
        "release": _installed_release(ctx),
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "service": service,
        "listener_pids": process.verified_proxy_listener_pids(ctx),
        "runtime": _runtime_metrics(ctx),
        "payload_transaction": payload_state.status(ctx),
    }


def reload(ctx: runtime_context.RuntimeContext, timeout_seconds: float = 30.0) -> dict[str, object]:
    """Reload the same installed protocol-v2 payload through live handoff."""

    runtime = _runtime_metrics(ctx)
    if not handoff.runtime_supports_handoff(runtime):
        raise errors.InstallError(
            "installed listener does not support protocol-v2 handoff; use the source-side "
            "installer during an explicitly authorized legacy bootstrap"
        )
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


def _print_status(evidence: dict) -> None:
    integrity = evidence["payload_integrity"]
    print(f"release: {evidence['release'] or 'unavailable'}")
    print(f"payload integrity: {'ok' if integrity['ok'] else 'FAILED'} ({integrity['detail']})")
    print(f"service: {evidence['service']}")
    print(f"verified listener pids: {', '.join(map(str, evidence['listener_pids'])) or 'none'}")
    runtime = evidence["runtime"]
    if runtime is None:
        print("runtime metrics: unavailable")
    else:
        print(
            f"runtime metrics: {runtime['uptime_seconds']}s uptime; "
            f"{runtime['active_responses']} active Responses request(s)"
        )
    payload_transaction = evidence["payload_transaction"]
    print(
        "payload transaction: none"
        if payload_transaction is None
        else f"payload transaction: {payload_transaction['state']}"
    )


def main() -> None:
    """Parse one bounded product lifecycle command."""

    parser = argparse.ArgumentParser(description="Control the installed Codex Responses Proxy.")
    parser.add_argument("command", choices=("status", "reload"))
    parser.add_argument("--port", type=int, default=runtime_config.DEFAULT_PORT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    try:
        ctx = _context(args.port)
        evidence = (
            status(ctx)
            if args.command == "status"
            else reload(ctx, timeout_seconds=args.timeout_seconds)
        )
    except errors.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.as_json:
        print(json.dumps(evidence, sort_keys=True))
    elif args.command == "status":
        _print_status(evidence)
    else:
        print(f"reloaded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']}")


if __name__ == "__main__":
    main()
