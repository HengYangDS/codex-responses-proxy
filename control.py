#!/usr/bin/env python3
"""control.py — non-secret route evidence and lifecycle control for the installed proxy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codex_dmx_proxy.supervision.select import adapter  # noqa: E402
from codex_dmx_proxy.deployment import handoff  # noqa: E402
from codex_dmx_proxy import installation  # noqa: E402
from codex_dmx_proxy import errors  # noqa: E402
from codex_dmx_proxy import process  # noqa: E402
from codex_dmx_proxy.release import projection, transaction  # noqa: E402
from codex_dmx_proxy.route import management as route_state  # noqa: E402


def _context() -> installation.InstallContext:
    codex_home = installation.codex_home()
    home = os.path.dirname(codex_home)
    install_dir = os.path.join(codex_home, "dmx-proxy")
    state_path = os.path.join(install_dir, route_state.STATE_FILENAME)
    port = installation.DEFAULT_PORT
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            value = json.load(fh).get("proxy_url", "")
        parsed = urllib.parse.urlsplit(value)
        scoped_paths = {f"/{route}/v1" for route in route_state.PROVIDER_ROUTES}
        if (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"/v1", *scoped_paths}
            and parsed.query == ""
            and parsed.fragment == ""
            and parsed.port is not None
            and parsed.port > 0
        ):
            port = parsed.port
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return installation.InstallContext(
        home=home,
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "codex_dmx_proxy", "listener", "entrypoint.py"),
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
        raise errors.InstallError("could not resolve the canonical AIGW config path")
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
        raise errors.InstallError(f"AIGW endpoint update failed: {detail or 'unknown error'}")


def adopt_aigw_route(
    ctx: installation.InstallContext,
    *,
    account: str,
    direct_url: str,
    provider_route: str = "dmxapi",
) -> dict:
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
        raise errors.InstallError("could not read canonical AIGW config") from exc
    direct_url = route_state.normalize_upstream_url(direct_url)
    proxy_url = route_state.provider_proxy_base_url(ctx.port, provider_route)
    if endpoint not in (direct_url, proxy_url):
        raise errors.InstallError(
            "AIGW endpoint differs from requested direct/proxy route; refusing adoption"
        )
    state = route_state.make_aigw_install_state(
        ctx,
        aigw_config_path=config_path,
        account=account,
        direct_url=direct_url,
        provider_route=provider_route,
    )
    route_state.write_install_state(ctx, state)
    return state


def set_aigw_route(ctx: installation.InstallContext, state: dict | None, *, enabled: bool) -> None:
    """Ask AIGW to toggle an adopted canonical endpoint without editing its config."""
    if state is None or state.get("route_mode") != "aigw_endpoint":
        raise errors.InstallError("AIGW route is unmanaged; run control.py adopt-aigw first")
    if state.get("schema_version") == 2 and enabled:
        raise errors.InstallError(
            "legacy AIGW route state cannot enable /v1; project the scoped endpoint "
            "through AIGW and run control.py adopt-aigw"
        )
    status = route_state.aigw_route_status(ctx, state, state["aigw_config_path"])
    if status == "drifted":
        raise errors.InstallError(
            "canonical AIGW endpoint has changed outside proxy control; refusing to overwrite it"
        )
    target = (
        route_state.provider_proxy_base_url(
            ctx.port,
            route_state.aigw_provider_route(state),
        )
        if enabled
        else state["direct_url"]
    )
    if status != ("enabled" if enabled else "disabled"):
        _set_aigw_account_endpoint(state["aigw_account"], target)
        status = route_state.aigw_route_status(ctx, state, state["aigw_config_path"])
        expected = "enabled" if enabled else "disabled"
        if status != expected:
            raise errors.InstallError(
                "AIGW endpoint update did not reach the expected canonical state"
            )


def _installed_release(ctx: installation.InstallContext) -> str | None:
    try:
        with open(os.path.join(ctx.install_dir, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _runtime_metrics(ctx: installation.InstallContext) -> dict | None:
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


def status(ctx: installation.InstallContext) -> dict:
    """Return non-secret runtime and transaction evidence without mutating either."""
    integrity_ok, integrity_detail = projection.verify_payload_manifest(ctx)
    listeners = process.verified_proxy_listener_pids(ctx)
    try:
        service = adapter().status(ctx)
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
        "payload_transaction": transaction.transaction_status(ctx),
    }


def reload(
    ctx: installation.InstallContext,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Reload one protocol-v2 listener through its live socket handoff."""

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
    parser.add_argument("--aigw-account", default="dmxapi", help="AIGW account ID for adopt-aigw")
    parser.add_argument(
        "--provider-route",
        default="dmxapi",
        choices=tuple(sorted(route_state.PROVIDER_ROUTES)),
        help="provider-scoped proxy route for adopt-aigw",
    )
    parser.add_argument(
        "--direct-url",
        default=installation.DEFAULT_UPSTREAM + "/v1",
        help="direct Responses endpoint for adopt-aigw",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    ctx = _context()
    state = route_state.load_install_state(ctx)

    if args.command == "adopt-aigw":
        try:
            state = adopt_aigw_route(
                ctx,
                account=args.aigw_account,
                direct_url=args.direct_url,
                provider_route=args.provider_route,
            )
        except errors.InstallError as exc:
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
        except errors.InstallError as exc:
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
            raise errors.InstallError(
                "AIGW owns the route; use AIGW or explicitly adopt-aigw first"
            )
        else:
            route_state.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except errors.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print(
        "Reload Codex through its normal client lifecycle before expecting an already-running client to use a changed route."
    )


if __name__ == "__main__":
    main()
