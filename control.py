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

from platform_adapters import pick_adapter, common  # noqa: E402


def _context() -> common.InstallContext:
    codex_home = common.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    state_path = os.path.join(install_dir, common.STATE_FILENAME)
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
        ["aigw", "config", "path"], capture_output=True, text=True, check=False,
    )
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        raise common.InstallError("could not resolve the canonical AIGW config path")
    return path


def _set_aigw_account_endpoint(account: str, endpoint: str) -> None:
    """Request an endpoint change through AIGW; never edit its config directly."""
    result = subprocess.run(
        ["aigw", "account", "edit", account, "--openai-url", endpoint],
        capture_output=True, text=True, check=False,
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
            endpoint = common.aigw_endpoint(fh.read(), account)
    except OSError as exc:
        raise common.InstallError("could not read canonical AIGW config") from exc
    direct_url = common.normalize_upstream_url(direct_url)
    proxy_url = common.proxy_base_url(ctx.port)
    if endpoint not in (direct_url, proxy_url):
        raise common.InstallError("AIGW endpoint differs from requested direct/proxy route; refusing adoption")
    state = common.make_aigw_install_state(
        ctx, aigw_config_path=config_path, account=account, direct_url=direct_url,
    )
    common.write_install_state(ctx, state)
    return state


def set_aigw_route(ctx: common.InstallContext, state: dict | None, *, enabled: bool) -> None:
    if state is None or state.get("route_mode") != "aigw_endpoint":
        raise common.InstallError("AIGW route is unmanaged; run control.py adopt-aigw first")
    status = common.aigw_route_status(ctx, state, state["aigw_config_path"])
    if status == "drifted":
        raise common.InstallError("canonical AIGW endpoint has changed outside proxy control; refusing to overwrite it")
    target = state["proxy_url"] if enabled else state["direct_url"]
    if status != ("enabled" if enabled else "disabled"):
        _set_aigw_account_endpoint(state["aigw_account"], target)
        status = common.aigw_route_status(ctx, state, state["aigw_config_path"])
        expected = "enabled" if enabled else "disabled"
        if status != expected:
            raise common.InstallError("AIGW endpoint update did not reach the expected canonical state")


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


def status(ctx: common.InstallContext) -> dict:
    """Return non-secret runtime evidence for the installed projection."""
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    listeners = common.verified_proxy_listener_pids(ctx)
    try:
        service = pick_adapter().status(ctx)
    except Exception:
        service = "unknown"
    state = common.load_install_state(ctx)
    return {
        "release": _installed_release(ctx),
        "payload_integrity": {"ok": integrity_ok, "detail": integrity_detail},
        "route_authority": common.route_authority(ctx),
        "route_mode": state.get("route_mode") if state else None,
        "route": common.route_status(ctx, state),
        "service": service,
        "listener_pids": listeners,
        "runtime": _runtime_metrics(ctx),
    }


def reload(
    ctx: common.InstallContext,
    timeout_seconds: float = 30.0,
    *,
    force_active_responses: bool = False,
) -> dict[str, int]:
    """Replace exactly one drained verified listener via its watchdog.

    A reload interrupts active SSE Responses.  When loopback health cannot prove
    zero active requests, refuse by default; ``force_active_responses`` exists
    only for an explicitly authorized, controlled interruption.
    """
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    listeners = common.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise common.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    runtime = _runtime_metrics(ctx)
    active = runtime.get("active_responses") if isinstance(runtime, dict) else None
    if not force_active_responses and (isinstance(active, bool) or not isinstance(active, int) or active != 0):
        observed = "unavailable" if active is None else str(active)
        raise common.InstallError(
            f"refusing reload while active Responses are not proven drained (active_responses={observed})"
        )
    old_pid = listeners[0]
    common.terminate_pid(old_pid)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for pid in common.verified_proxy_listener_pids(ctx):
            if pid != old_pid:
                return {"old_pid": old_pid, "new_pid": pid}
        time.sleep(0.1)
    raise common.InstallError(
        f"watchdog did not replace verified proxy listener {old_pid} within {timeout_seconds:g}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the installed Codex DMX Proxy.")
    parser.add_argument("command", choices=("status", "enable", "disable", "reload", "adopt-aigw"))
    parser.add_argument("--aigw-account", default="dmx", help="AIGW account ID for adopt-aigw")
    parser.add_argument("--direct-url", default=common.DEFAULT_UPSTREAM + "/v1", help="direct Responses endpoint for adopt-aigw")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--force-active-responses",
        action="store_true",
        help="interrupt active local Responses after explicit operator authorization",
    )
    args = parser.parse_args()
    ctx = _context()
    state = common.load_install_state(ctx)

    if args.command == "adopt-aigw":
        try:
            state = adopt_aigw_route(ctx, account=args.aigw_account, direct_url=args.direct_url)
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        evidence = {"route": common.aigw_route_status(ctx, state, state["aigw_config_path"]), "authority": "aigw"}
        print(json.dumps(evidence, sort_keys=True) if args.as_json else "route: " + evidence["route"] + "\nauthority: AIGW canonical endpoint")
        return

    if args.command == "status":
        evidence = status(ctx)
        if args.as_json:
            print(json.dumps(evidence, sort_keys=True))
        else:
            print(f"release: {evidence['release'] or 'unavailable'}")
            print(f"payload integrity: {'ok' if evidence['payload_integrity']['ok'] else 'FAILED'} ({evidence['payload_integrity']['detail']})")
            print(f"route authority: {evidence['route_authority']}")
            print(f"route: {evidence['route']}")
            print(f"service: {evidence['service']}")
            print(f"verified listener pids: {', '.join(map(str, evidence['listener_pids'])) or 'none'}")
            runtime = evidence["runtime"]
            if runtime is None:
                print("runtime metrics: unavailable")
            else:
                print(f"runtime metrics: {runtime['uptime_seconds']}s uptime; "
                      f"{runtime['active_responses']} active Responses request(s)")
        return

    if args.command == "reload":
        try:
            evidence = reload(
                ctx,
                timeout_seconds=args.timeout_seconds,
                force_active_responses=args.force_active_responses,
            )
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else f"reloaded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']}")
        return

    try:
        if state is not None and state.get("route_mode") == "aigw_endpoint":
            set_aigw_route(ctx, state, enabled=args.command == "enable")
        elif common.route_authority(ctx) == "aigw":
            raise common.InstallError("AIGW owns the route; use AIGW or explicitly adopt-aigw first")
        else:
            common.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except common.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print("Reload Codex through its normal client lifecycle before expecting an already-running client to use a changed route.")


if __name__ == "__main__":
    main()
