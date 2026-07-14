#!/usr/bin/env python3
"""control.py — reversible route control for an installed codex-dmx-proxy."""

from __future__ import annotations

import argparse
import os
import sys
import subprocess

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
        import json
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
    result = subprocess.run(
        ["aigw", "account", "edit", account, "--openai-url", endpoint],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise common.InstallError(f"AIGW endpoint update failed: {detail or 'unknown error'}")


def adopt_aigw_route(ctx: common.InstallContext, *, account: str, direct_url: str) -> dict:
    """Adopt the canonical AIGW endpoint only when it is already direct/proxy."""
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
        # AIGW owns the canonical file and projection. Refresh the state proof
        # after its successful transactional command rather than assuming a
        # mocked or failed external command changed the desired endpoint.
        status = common.aigw_route_status(ctx, state, state["aigw_config_path"])
        expected = "enabled" if enabled else "disabled"
        if status != expected:
            raise common.InstallError("AIGW endpoint update did not reach the expected canonical state")


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the installed codex-dmx-proxy route.")
    parser.add_argument("command", choices=("status", "enable", "disable", "adopt-aigw"))
    parser.add_argument("--aigw-account", default="dmx", help="AIGW Account ID for adopt-aigw")
    parser.add_argument("--direct-url", default=common.DEFAULT_UPSTREAM + "/v1", help="direct AIGW responses endpoint for adopt-aigw")
    args = parser.parse_args()
    ctx = _context()
    state = common.load_install_state(ctx)
    if args.command == "adopt-aigw":
        try:
            state = adopt_aigw_route(ctx, account=args.aigw_account, direct_url=args.direct_url)
        except common.InstallError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        print(f"route: {common.aigw_route_status(ctx, state, state['aigw_config_path'])}")
        print("authority: AIGW canonical endpoint")
        return
    if args.command == "status":
        route = common.route_status(ctx, state)
        try:
            service = pick_adapter().status(ctx)
        except Exception:
            service = "unknown"
        print(f"route: {route}")
        if state is not None and state.get("route_mode") == "aigw_endpoint":
            print("authority: AIGW canonical endpoint")
        print(f"service: {service}")
        return
    try:
        if state is not None and state.get("route_mode") == "aigw_endpoint":
            set_aigw_route(ctx, state, enabled=args.command == "enable")
        else:
            common.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except common.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print("Restart or reload Codex normally before expecting an already-running client to use the new route.")


if __name__ == "__main__":
    main()
