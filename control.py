#!/usr/bin/env python3
"""control.py — non-secret route evidence and lifecycle control for the installed proxy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import common, control_handoff, payload, pick_adapter, route_state  # noqa: E402


QUIESCENCE_SECONDS = 5.0


def _context() -> common.InstallContext:
    codex_home = common.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    state_path = os.path.join(install_dir, route_state.STATE_FILENAME)
    port = common.DEFAULT_PORT
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            value = json.load(fh).get("proxy_url", "")
        if value.startswith("http://127.0.0.1:") and value.endswith("/v1"):
            port = int(value.rsplit(":", 1)[1].removesuffix("/v1"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return common.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=sys.executable,
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=port,
    )


def _aigw_config_path() -> str:
    result = subprocess.run(
        ["aigw", "config", "path"],
        capture_output=True,
        text=True,
        check=False,
    )
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        raise common.InstallError("could not resolve the canonical AIGW config path")
    return path


def _set_aigw_account_endpoint(account: str, endpoint: str) -> None:
    """Request an endpoint change through AIGW; never edit its config directly."""
    result = subprocess.run(
        ["aigw", "account", "edit", account, "--openai-url", endpoint],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise common.InstallError(f"AIGW endpoint update failed: {detail or 'unknown error'}")


def adopt_aigw_route(ctx: common.InstallContext, *, account: str, direct_url: str) -> dict:
    """Record an opt-in AIGW endpoint route without parsing or writing its config.

    The only control-plane mutation later performed by this mode is a call to the
    public AIGW command.  AIGW remains the writer of its canonical config and its
    multi-target Codex projections.
    """
    config_path = _aigw_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            endpoint = route_state.aigw_endpoint(fh.read(), account)
    except OSError as exc:
        raise common.InstallError("could not read canonical AIGW config") from exc
    direct_url = route_state.normalize_upstream_url(direct_url)
    proxy_url = route_state.proxy_base_url(ctx.port)
    if endpoint not in (direct_url, proxy_url):
        raise common.InstallError(
            "AIGW endpoint differs from requested direct/proxy route; refusing adoption"
        )
    state = route_state.make_aigw_install_state(
        ctx,
        aigw_config_path=config_path,
        account=account,
        direct_url=direct_url,
    )
    route_state.write_install_state(ctx, state)
    return state


def set_aigw_route(ctx: common.InstallContext, state: dict | None, *, enabled: bool) -> None:
    """Ask AIGW to toggle an adopted canonical endpoint without editing its config."""
    if state is None or state.get("route_mode") != "aigw_endpoint":
        raise common.InstallError("AIGW route is unmanaged; run control.py adopt-aigw first")
    status = route_state.aigw_route_status(ctx, state, state["aigw_config_path"])
    if status == "drifted":
        raise common.InstallError(
            "canonical AIGW endpoint has changed outside proxy control; refusing to overwrite it"
        )
    target = state["proxy_url"] if enabled else state["direct_url"]
    if status != ("enabled" if enabled else "disabled"):
        _set_aigw_account_endpoint(state["aigw_account"], target)
        status = route_state.aigw_route_status(ctx, state, state["aigw_config_path"])
        expected = "enabled" if enabled else "disabled"
        if status != expected:
            raise common.InstallError(
                "AIGW endpoint update did not reach the expected canonical state"
            )


def _installed_release(ctx: common.InstallContext) -> str | None:
    try:
        with open(os.path.join(ctx.install_dir, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _runtime_metrics(ctx: common.InstallContext) -> dict | None:
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


def _drain_request(
    ctx: common.InstallContext, *, enabled: bool, lease_seconds: float | None = None
) -> dict:
    """Set the listener's local admission latch through its loopback control API."""
    method = "POST" if enabled else "DELETE"
    headers = {"Accept": "application/json"}
    if enabled and lease_seconds is not None:
        headers["X-DMX-Drain-Lease-Seconds"] = str(max(1, int(lease_seconds)))
    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/control/drain",
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                raise common.InstallError(f"listener drain control returned HTTP {response.status}")
            payload = json.loads(response.read())
    except common.InstallError:
        raise
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        raise common.InstallError("listener drain control is unavailable") from exc
    if not isinstance(payload, dict):
        raise common.InstallError("listener drain control returned an invalid response")
    return payload


def _set_listener_drain(
    ctx: common.InstallContext,
    *,
    enabled: bool,
    lease_seconds: float | None = None,
) -> dict:
    """Require the current verified listener to acknowledge an admission change."""
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    payload = _drain_request(ctx, enabled=enabled, lease_seconds=lease_seconds)
    observed = payload.get("draining")
    if observed is not enabled:
        raise common.InstallError("listener drain control did not reach the requested state")
    return {"listener": listeners[0], "runtime": payload}


def _wait_for_quiescent_listener(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    quiet_seconds: float = QUIESCENCE_SECONDS,
) -> dict:
    """Wait for a stable idle window without closing Responses admission.

    This is deliberately a *preflight*, not a weak substitute for atomic drain.
    Waiting until the listener is quiet keeps normal user traffic fully serving.
    Only after the quiet window is proven do we close admission atomically; that
    reduces maintenance-visible 503s from a busy listener to the unavoidable
    final handoff race.
    """
    if timeout_seconds <= 0:
        raise common.InstallError("drain timeout must be positive")
    if quiet_seconds <= 0:
        raise common.InstallError("quiescence window must be positive")
    integrity_ok, integrity_detail = payload.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    deadline = time.monotonic() + timeout_seconds
    quiet_started_at: float | None = None
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) != [old_pid]:
            raise common.InstallError(
                "verified listener changed during quiescence preflight; refusing lifecycle mutation"
            )
        runtime = _runtime_metrics(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        draining = runtime.get("draining") if isinstance(runtime, dict) else None
        if (
            draining is False
            and isinstance(active, int)
            and not isinstance(active, bool)
            and active == 0
        ):
            now = time.monotonic()
            if quiet_started_at is None:
                quiet_started_at = now
            elif now - quiet_started_at >= quiet_seconds:
                return {"listener": old_pid, "runtime": runtime}
        else:
            quiet_started_at = None
        time.sleep(0.1)
    raise common.InstallError(
        f"listener did not remain quiescent for {quiet_seconds:g}s within {timeout_seconds:g}s; "
        "no drain was started"
    )


def _drain_listener(ctx: common.InstallContext, timeout_seconds: float) -> dict:
    """Quiesce first, then close admission and prove the same listener drained.

    The listener owns the latch and counter under one lock.  Thus an acknowledged
    snapshot with ``draining=true`` and ``active_responses=0`` proves that no new
    Responses request can enter before the listener is terminated.
    """
    quiescent = _wait_for_quiescent_listener(ctx, timeout_seconds)
    old_pid = quiescent["listener"]
    baseline = _set_listener_drain(ctx, enabled=True, lease_seconds=timeout_seconds + 5)
    if baseline["listener"] != old_pid:
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise common.InstallError(
            "verified listener changed while admission was closing; service restored to admission"
        )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        listeners = common.verified_proxy_listener_pids(ctx)
        if listeners != [old_pid]:
            raise common.InstallError(
                "verified listener changed during drain; refusing lifecycle mutation"
            )
        runtime = _runtime_metrics(ctx)
        if not isinstance(runtime, dict):
            time.sleep(0.1)
            continue
        active = runtime.get("active_responses")
        if (
            runtime.get("draining") is True
            and isinstance(active, int)
            and not isinstance(active, bool)
            and active == 0
        ):
            return {"listener": old_pid, "runtime": runtime}
        time.sleep(0.1)
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"listener did not drain active Responses within {timeout_seconds:g}s; service restored to admission"
    )


def _legacy_drain_listener(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    required_idle_seconds: float = 1.0,
) -> dict:
    """Quiesce a pre-drain listener with two consecutive zero snapshots.

    This compatibility path is intentionally narrower than the current atomic
    drain protocol.  It exists only to replace an older installed listener that
    predates ``/control/drain``.  Two zero samples separated by a short quiet
    interval reduce the replacement window; the installed protocol-v2 listener
    then supplies the durable atomic admission barrier for subsequent reloads.
    """
    if timeout_seconds <= 0:
        raise common.InstallError("drain timeout must be positive")
    integrity_ok, integrity_detail = payload.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    deadline = time.monotonic() + timeout_seconds
    if required_idle_seconds <= 0:
        raise common.InstallError("legacy idle window must be positive")
    previous_zero_at: float | None = None
    while time.monotonic() < deadline:
        if common.verified_proxy_listener_pids(ctx) != [old_pid]:
            raise common.InstallError(
                "verified listener changed during legacy drain; refusing lifecycle mutation"
            )
        runtime = _runtime_metrics(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        if isinstance(active, int) and not isinstance(active, bool) and active == 0:
            now = time.monotonic()
            if previous_zero_at is not None and now - previous_zero_at >= required_idle_seconds:
                return {"listener": old_pid, "runtime": runtime, "legacy": True}
            previous_zero_at = now
        else:
            previous_zero_at = None
        time.sleep(0.1)
    raise common.InstallError(
        f"legacy listener did not remain idle for {required_idle_seconds:g}s within {timeout_seconds:g}s; "
        "payload was not changed"
    )


def _drain_listener_with_legacy_bootstrap(
    ctx: common.InstallContext,
    timeout_seconds: float,
    *,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
) -> dict:
    """Use atomic drain when available; bootstrap exactly one legacy listener otherwise."""
    try:
        return _drain_listener(ctx, timeout_seconds)
    except common.InstallError as exc:
        if str(exc) != "listener drain control is unavailable":
            raise
    if not allow_legacy_bootstrap:
        raise common.InstallError(
            "listener predates atomic drain control; retry after an operator-approved maintenance window"
        )
    if force_legacy_bootstrap:
        integrity_ok, integrity_detail = payload.verify_payload_manifest(ctx)
        if not integrity_ok:
            raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
        listeners = common.verified_proxy_listener_pids(ctx)
        if len(listeners) != 1:
            raise common.InstallError(
                f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
            )
        return {"listener": listeners[0], "legacy": True, "forced": True}
    return _legacy_drain_listener(ctx, timeout_seconds, required_idle_seconds=5.0)


def status(ctx: common.InstallContext) -> dict:
    """Return non-secret runtime and transaction evidence without mutating either."""
    integrity_ok, integrity_detail = payload.verify_payload_manifest(ctx)
    listeners = common.verified_proxy_listener_pids(ctx)
    try:
        service = pick_adapter().status(ctx)
    except Exception:
        service = "unknown"
    state = route_state.load_install_state(ctx)
    return {
        "release": _installed_release(ctx),
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "route_authority": route_state.route_authority(ctx),
        "route_mode": state.get("route_mode") if state else None,
        "route": route_state.route_status(ctx, state),
        "service": service,
        "listener_pids": listeners,
        "runtime": _runtime_metrics(ctx),
        "payload_transaction": payload.transaction_status(ctx),
    }


def reload(
    ctx: common.InstallContext,
    timeout_seconds: float = 30.0,
) -> dict[str, int]:
    """Replace exactly one verified listener; prefer a live handoff over drain+restart.

    A listener whose own health snapshot advertises protocol-v2 handoff support
    is asked to prepare and hand off to a new child on its own already-open
    listening socket; the old listener is never terminated by this controller
    and keeps serving until the new one proves it.  A listener that predates
    handoff keeps the existing drain -> terminate -> watchdog-replace path
    unchanged.
    """
    runtime = _runtime_metrics(ctx)
    if control_handoff.runtime_supports_handoff(runtime):
        assert runtime is not None
        integrity_ok, integrity_detail = payload.verify_payload_manifest(ctx)
        if not integrity_ok:
            raise common.InstallError(
                f"payload integrity check failed before handoff reload: {integrity_detail}"
            )
        expected = control_handoff.expected_metadata(ctx.install_dir)
        lease_seconds = max(1.0, timeout_seconds)
        try:
            result = control_handoff.request(
                ctx,
                expected,
                runtime_reader=_runtime_metrics,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
        except BaseException as handoff_exc:
            try:
                resolution, resolved_runtime = control_handoff.resolve_after_controller_failure(
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
                raise common.InstallError(
                    "reload handoff outcome is unconfirmed; inspect the transaction-bound listener health"
                ) from handoff_exc
            raise
        return {"old_pid": result["old_pid"], "new_pid": result["child_pid"]}
    old_pid = _drain_listener_with_legacy_bootstrap(ctx, timeout_seconds)["listener"]
    try:
        common.terminate_pid(old_pid)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for pid in common.verified_proxy_listener_pids(ctx):
                if pid != old_pid:
                    return {"old_pid": old_pid, "new_pid": pid}
            time.sleep(0.1)
    except Exception:
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"watchdog did not replace verified proxy listener {old_pid} within {timeout_seconds:g}s; "
        "service restored to admission"
    )


def main() -> None:
    """Parse the lifecycle command and print its bounded evidence or result."""
    parser = argparse.ArgumentParser(description="Control the installed Codex DMX Proxy.")
    parser.add_argument(
        "command",
        choices=(
            "status",
            "enable",
            "disable",
            "reload",
            "adopt-aigw",
        ),
    )
    parser.add_argument("--aigw-account", default="dmx", help="AIGW account ID for adopt-aigw")
    parser.add_argument(
        "--direct-url",
        default=common.DEFAULT_UPSTREAM + "/v1",
        help="direct Responses endpoint for adopt-aigw",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    ctx = _context()
    state = route_state.load_install_state(ctx)

    if args.command == "adopt-aigw":
        try:
            state = adopt_aigw_route(ctx, account=args.aigw_account, direct_url=args.direct_url)
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        evidence = {
            "route": route_state.aigw_route_status(ctx, state, state["aigw_config_path"]),
            "authority": "aigw",
        }
        print(
            json.dumps(evidence, sort_keys=True)
            if args.as_json
            else "route: " + evidence["route"] + "\nauthority: AIGW canonical endpoint"
        )
        return

    if args.command == "status":
        evidence = status(ctx)
        if args.as_json:
            print(json.dumps(evidence, sort_keys=True))
        else:
            print(f"release: {evidence['release'] or 'unavailable'}")
            print(
                f"payload integrity: {'ok' if evidence['payload_integrity']['ok'] else 'FAILED'} ({evidence['payload_integrity']['detail']})"
            )
            print(f"route authority: {evidence['route_authority']}")
            print(f"route: {evidence['route']}")
            print(f"service: {evidence['service']}")
            print(
                f"verified listener pids: {', '.join(map(str, evidence['listener_pids'])) or 'none'}"
            )
            runtime = evidence["runtime"]
            if runtime is None:
                print("runtime metrics: unavailable")
            else:
                print(
                    f"runtime metrics: {runtime['uptime_seconds']}s uptime; "
                    f"{runtime['active_responses']} active Responses request(s)"
                )
            transaction = evidence["payload_transaction"]
            if transaction is None:
                print("payload transaction: none")
            else:
                print(f"payload transaction: {transaction['state']}")
        return

    if args.command == "reload":
        try:
            evidence = reload(
                ctx,
                timeout_seconds=args.timeout_seconds,
            )
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(
            json.dumps(evidence, sort_keys=True)
            if args.as_json
            else f"reloaded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']}"
        )
        return

    try:
        if state is not None and state.get("route_mode") == "aigw_endpoint":
            set_aigw_route(ctx, state, enabled=args.command == "enable")
        elif route_state.route_authority(ctx) == "aigw":
            raise common.InstallError(
                "AIGW owns the route; use AIGW or explicitly adopt-aigw first"
            )
        else:
            route_state.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except common.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print(
        "Reload Codex through its normal client lifecycle before expecting an already-running client to use a changed route."
    )


if __name__ == "__main__":
    main()
