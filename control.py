#!/usr/bin/env python3
"""control.py — non-secret route evidence and lifecycle control for the installed proxy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
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


def _drain_request(ctx: common.InstallContext, *, enabled: bool, lease_seconds: float | None = None) -> dict:
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


def _drain_listener(ctx: common.InstallContext, timeout_seconds: float) -> dict:
    """Close admission then wait for the same verified listener to reach zero.

    The listener owns the latch and counter under one lock.  Thus an acknowledged
    snapshot with ``draining=true`` and ``active_responses=0`` proves that no new
    Responses request can enter before the listener is terminated.
    """
    if timeout_seconds <= 0:
        raise common.InstallError("drain timeout must be positive")
    integrity_ok, integrity_detail = common.verify_payload_manifest(ctx)
    if not integrity_ok:
        raise common.InstallError(f"payload integrity check failed: {integrity_detail}")
    baseline = _set_listener_drain(ctx, enabled=True, lease_seconds=timeout_seconds + 5)
    old_pid = baseline["listener"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        listeners = common.verified_proxy_listener_pids(ctx)
        if listeners != [old_pid]:
            raise common.InstallError("verified listener changed during drain; refusing lifecycle mutation")
        runtime = _runtime_metrics(ctx)
        if not isinstance(runtime, dict):
            time.sleep(0.1)
            continue
        active = runtime.get("active_responses")
        if runtime.get("draining") is True and isinstance(active, int) and not isinstance(active, bool) and active == 0:
            return {"listener": old_pid, "runtime": runtime}
        time.sleep(0.1)
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"listener did not drain active Responses within {timeout_seconds:g}s; service restored to admission"
    )


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
) -> dict[str, int]:
    """Drain then replace exactly one verified listener via its watchdog."""
    old_pid = _drain_listener(ctx, timeout_seconds)["listener"]
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


def upgrade_from_stage(ctx: common.InstallContext, stage: str, timeout_seconds: float = 30.0) -> dict[str, int | str]:
    """Drain, commit a pre-verified stage, then replace the verified listener."""
    staged_version = Path(stage, "VERSION").read_text(encoding="utf-8").strip()
    if not staged_version:
        raise common.InstallError("staged payload has no release version")
    old_pid = _drain_listener(ctx, timeout_seconds)["listener"]
    try:
        common.commit_payload_transaction(ctx, stage)
        common.terminate_pid(old_pid)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            listeners = common.verified_proxy_listener_pids(ctx)
            for pid in listeners:
                if pid == old_pid:
                    continue
                runtime = _runtime_metrics(ctx)
                if isinstance(runtime, dict) and runtime.get("release") == staged_version:
                    common.finalize_payload_transaction(ctx)
                    return {"old_pid": old_pid, "new_pid": pid, "release": staged_version}
            time.sleep(0.1)
    except Exception as exc:
        try:
            transaction = common.payload_transaction_dir(ctx)
            if os.path.isdir(os.path.join(transaction, "rollback")):
                common.restore_payload_transaction(ctx)
        except Exception as rollback_exc:
            raise common.InstallError(
                f"upgrade replacement failed and payload rollback failed: {rollback_exc}"
            ) from exc
        common.finalize_payload_transaction(ctx)
        try:
            _set_listener_drain(ctx, enabled=False)
        except common.InstallError:
            pass
        raise common.InstallError(f"upgrade replacement failed; payload restored: {exc}") from exc
    try:
        common.restore_payload_transaction(ctx)
    except Exception as rollback_exc:
        raise common.InstallError(
            f"watchdog replacement timed out and payload rollback failed: {rollback_exc}"
        ) from rollback_exc
    common.finalize_payload_transaction(ctx)
    try:
        _set_listener_drain(ctx, enabled=False)
    except common.InstallError:
        pass
    raise common.InstallError(
        f"watchdog did not replace verified proxy listener {old_pid} with release {staged_version} "
        f"within {timeout_seconds:g}s; payload restored"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the installed Codex DMX Proxy.")
    parser.add_argument("command", choices=("status", "enable", "disable", "reload", "adopt-aigw", "upgrade"))
    parser.add_argument("--stage", help="validated payload stage created by install.py --stage-only")
    parser.add_argument("--aigw-account", default="dmx", help="AIGW account ID for adopt-aigw")
    parser.add_argument("--direct-url", default=common.DEFAULT_UPSTREAM + "/v1", help="direct Responses endpoint for adopt-aigw")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
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
            )
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else f"reloaded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']}")
        return

    if args.command == "upgrade":
        if not args.stage:
            raise SystemExit("ERROR: upgrade requires --stage")
        try:
            evidence = upgrade_from_stage(ctx, args.stage, timeout_seconds=args.timeout_seconds)
        except (common.InstallError, OSError) as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(json.dumps(evidence, sort_keys=True) if args.as_json else (
            f"upgraded verified proxy listener: {evidence['old_pid']} -> {evidence['new_pid']} "
            f"(release {evidence['release']})"
        ))
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
