#!/usr/bin/env python3
"""uninstall.py — remove the Codex dmx-responses-proxy from this machine.

Reverses install.py: stops + deregisters the watchdog service, restores the most
recent config.toml backup (rolling base_url back to the direct upstream), and
optionally removes the install dir. Idempotent.
"""

from __future__ import annotations

import os
import sys
import argparse
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import common, pick_adapter, route_state  # noqa: E402
import control  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _stop_proxy(port: int, *, ctx: common.InstallContext | None = None) -> int:
    """Terminate only listeners verified against this installed proxy script."""
    if ctx is not None:
        pids = common.verified_proxy_listener_pids(ctx)
    else:
        pids = [
            pid
            for pid in common.listener_pids(port)
            if "dmx_responses_proxy.py" in common.process_command(pid)
        ]
    for pid in pids:
        common.terminate_pid(pid)
    return len(pids)


def restore_config(ctx: common.InstallContext) -> bool:
    """Restore only an exact managed direct route and preserve drifted state."""
    state = route_state.load_install_state(ctx)
    if state is None:
        _say("  no valid managed route state found; leaving config.toml as-is.")
        return False
    if state.get("route_mode") == "aigw_endpoint":
        status = route_state.route_status(ctx, state)
        if status == "drifted":
            _say("  canonical AIGW endpoint has drifted; leaving it unchanged.")
            return False
        if status == "enabled":
            try:
                control.set_aigw_route(ctx, state, enabled=False)
            except common.InstallError as exc:
                _say(f"  AIGW route restore failed; leaving proxy active: {exc}")
                return False
        if route_state.route_status(ctx, state) != "disabled":
            _say(
                "  canonical AIGW endpoint did not reach the recorded direct route; leaving it unchanged."
            )
            return False
        route_state.remove_install_state(ctx)
        _say("  restored canonical AIGW endpoint to the recorded direct route")
        return True
    if route_state.route_status(ctx, state) != "enabled":
        _say("  config is disabled or drifted; leaving it unchanged.")
        return False
    backup = state["backup_path"]
    if not os.path.isfile(backup):
        _say("  recorded config backup is unavailable; leaving config.toml as-is.")
        return False
    with open(backup, "r", encoding="utf-8") as fh:
        restored = fh.read()
    if route_state._sha256_text(restored) != state["direct_sha256"]:
        _say("  recorded config backup has changed; leaving config.toml as-is.")
        return False
    route_state._atomic_write_text(ctx.codex_config, restored)
    route_state.remove_install_state(ctx)
    _say(f"  restored config from {os.path.basename(backup)}")
    return True


def main() -> None:
    """Remove the managed service and optionally restore or purge owned state."""
    ap = argparse.ArgumentParser(description="Uninstall the Codex dmx-responses-proxy.")
    ap.add_argument("--port", type=int, default=common.DEFAULT_PORT)
    ap.add_argument(
        "--purge", action="store_true", help="also delete the install dir (~/.codex/dmx-proxy)"
    )
    ap.add_argument("--keep-config", action="store_true", help="do not restore config.toml backup")
    args = ap.parse_args()
    try:
        args.port = common.validate_port(args.port)
    except common.InstallError as exc:
        ap.error(str(exc))

    codex_home = common.codex_home()
    install_dir = os.path.join(codex_home, "dmx-proxy")
    ctx = common.InstallContext(
        home=os.path.dirname(codex_home),
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=sys.executable,
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=args.port,
    )

    if route_state.route_authority(ctx) == "aigw":
        raise SystemExit(
            "ERROR: AIGW owns the active route; change the route with AIGW before uninstalling the proxy."
        )
    adapter = pick_adapter()

    _say("Uninstalling codex-dmx-proxy ...")
    if not args.keep_config:
        _say("[1/3] restoring route ...")
        restore_config(ctx)
    else:
        _say("[1/3] keeping route (per --keep-config)")

    _say("[2/3] deregistering watchdog service ...")
    try:
        adapter.uninstall(ctx)
    except Exception as e:
        _say(f"  (service removal note: {e})")
    _stop_proxy(args.port, ctx=ctx)

    if args.purge:
        _say("[3/3] removing install dir ...")
        shutil.rmtree(ctx.install_dir, ignore_errors=True)
    else:
        _say(f"[3/3] leaving install dir {ctx.install_dir} (use --purge to delete)")

    _say(
        "\nDone. Existing conversations remain unchanged; verify the reverted route through "
        "the client's normal configuration-reload lifecycle before treating it as active."
    )


if __name__ == "__main__":
    main()
