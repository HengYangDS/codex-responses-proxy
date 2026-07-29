#!/usr/bin/env python3
"""Remove Codex DMX Proxy from this machine.

Stops and deregisters the watchdog service, then restores only the direct route
recorded in valid managed state. A proxy-owned Codex route is restored from its
recorded, digest-matched backup; an adopted AIGW route is disabled through the
AIGW CLI and verified before state removal. ``--purge`` removes only files proved
owned by a valid payload manifest; unknown install content is preserved and
reported as an incomplete uninstall.
"""

from __future__ import annotations

import os
import sys
import argparse
from typing import Protocol, cast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codex_dmx_proxy.supervision.select import adapter  # noqa: E402
from codex_dmx_proxy import installation  # noqa: E402
from codex_dmx_proxy import errors  # noqa: E402
from codex_dmx_proxy import process  # noqa: E402
from codex_dmx_proxy.release import projection  # noqa: E402
from codex_dmx_proxy.route import management as route_state  # noqa: E402
import control  # noqa: E402


class ServiceAdapter(Protocol):
    """Native supervision operations required by uninstall."""

    def uninstall(self, ctx: installation.InstallContext) -> None: ...

    def status(self, ctx: installation.InstallContext) -> str: ...


def _say(msg: str) -> None:
    print(msg, flush=True)


def _stop_proxy(ctx: installation.InstallContext) -> int:
    """Terminate and prove exit of each listener owned by this installation."""
    pids = process.verified_proxy_listener_pids(ctx)
    for pid in pids:
        if not process.terminate_pid(pid, expected_path=ctx.proxy_script):
            raise errors.InstallError(f"verified proxy listener {pid} did not exit")
    remaining = process.verified_proxy_listener_pids(ctx)
    if remaining:
        raise errors.InstallError(f"verified proxy listeners remain: {remaining}")
    return len(pids)


def _remove_service(service: ServiceAdapter, ctx: installation.InstallContext) -> None:
    """Deregister supervision and require its read-only status to prove absence."""
    service.uninstall(ctx)
    state = service.status(ctx)
    if state != "absent":
        raise errors.InstallError(f"watchdog service remains {state}")


def restore_config(ctx: installation.InstallContext) -> bool:
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
            except errors.InstallError as exc:
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
    ap = argparse.ArgumentParser(description="Uninstall Codex DMX Proxy.")
    ap.add_argument("--port", type=int, default=installation.DEFAULT_PORT)
    ap.add_argument(
        "--purge",
        action="store_true",
        help="also remove the manifest-owned runtime payload; preserve unknown content",
    )
    ap.add_argument("--keep-config", action="store_true", help="do not restore the managed route")
    args = ap.parse_args()
    try:
        args.port = installation.validate_port(args.port)
    except errors.InstallError as exc:
        ap.error(str(exc))

    codex_home = installation.codex_home()
    install_dir = os.path.join(codex_home, "dmx-proxy")
    ctx = installation.InstallContext(
        home=os.path.dirname(codex_home),
        install_dir=install_dir,
        proxy_script=os.path.join(install_dir, "codex_dmx_proxy", "listener", "entrypoint.py"),
        watchdog_script=os.path.join(install_dir, "watchdog", "watchdog.py"),
        python=sys.executable,
        codex_config=os.path.join(codex_home, "config.toml"),
        log_dir=os.path.join(codex_home, "log"),
        port=args.port,
    )

    state = route_state.load_install_state(ctx)
    if route_state.route_authority(ctx) == "aigw" and (
        state is None or state.get("route_mode") != "aigw_endpoint" or args.keep_config
    ):
        raise SystemExit(
            "ERROR: AIGW owns the route; uninstall requires an adopted managed route so it can "
            "delegate exact restoration through AIGW before removing the service."
        )
    service = cast(ServiceAdapter, adapter())

    _say("Uninstalling codex-dmx-proxy ...")
    if not args.keep_config:
        _say("[1/3] restoring route ...")
        restore_config(ctx)
    else:
        _say("[1/3] keeping route (per --keep-config)")

    _say("[2/3] deregistering watchdog service ...")
    try:
        _remove_service(service, ctx)
        _stop_proxy(ctx)
    except (errors.InstallError, OSError) as exc:
        raise SystemExit(f"ERROR: uninstall stopped before payload mutation: {exc}") from exc

    if args.purge:
        _say("[3/3] removing manifest-owned payload ...")
        try:
            remaining = projection.purge_installed_projection(ctx)
        except errors.InstallError as exc:
            raise SystemExit(f"ERROR: payload purge refused: {exc}") from exc
        if remaining:
            raise SystemExit(
                "ERROR: manifest-owned payload was removed, but unknown install content remains: "
                + ", ".join(remaining)
            )
    else:
        _say(f"[3/3] leaving install dir {ctx.install_dir} (use --purge to delete)")

    _say(
        "\nDone. Existing conversations remain unchanged; verify the reverted route through "
        "the client's normal configuration-reload lifecycle before treating it as active."
    )


if __name__ == "__main__":
    main()
