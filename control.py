#!/usr/bin/env python3
"""control.py — reversible route control for an installed codex-dmx-proxy."""

from __future__ import annotations

import argparse
import os
import sys

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the installed codex-dmx-proxy route.")
    parser.add_argument("command", choices=("status", "enable", "disable"))
    args = parser.parse_args()
    ctx = _context()
    state = common.load_install_state(ctx)
    if args.command == "status":
        route = common.route_status(ctx, state)
        try:
            service = pick_adapter().status(ctx)
        except Exception:
            service = "unknown"
        print(f"route: {route}")
        print(f"service: {service}")
        return
    try:
        common.set_proxy_route(ctx, state, enabled=args.command == "enable")
    except common.InstallError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"route: {args.command}d")
    print("Restart or reload Codex normally before expecting an already-running client to use the new route.")


if __name__ == "__main__":
    main()
