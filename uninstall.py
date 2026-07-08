#!/usr/bin/env python3
"""uninstall.py — remove the Codex dmx-responses-proxy from this machine.

Reverses install.py: stops + deregisters the watchdog service, restores the most
recent config.toml backup (rolling base_url back to the direct upstream), and
optionally removes the install dir. Idempotent.
"""

from __future__ import annotations

import os
import sys
import glob
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import pick_adapter, common  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _stop_proxy(port: int) -> None:
    """Best-effort: kill any running proxy so the port is freed."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/f", "/im", "pythonw.exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-f", "dmx_responses_proxy.py"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def restore_config(ctx: common.InstallContext) -> None:
    backups = sorted(
        glob.glob(f"{ctx.codex_config}.bak-*"),
        key=lambda p: os.path.getmtime(p),
    )
    if not backups:
        _say("  no config backup found; leaving config.toml as-is. If needed, set "
             "base_url back to your upstream manually.")
        return
    latest = backups[-1]
    shutil.copy2(latest, ctx.codex_config)
    _say(f"  restored config from {os.path.basename(latest)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Uninstall the Codex dmx-responses-proxy.")
    ap.add_argument("--port", type=int, default=common.DEFAULT_PORT)
    ap.add_argument("--purge", action="store_true",
                    help="also delete the install dir (~/.codex/dmx-proxy)")
    ap.add_argument("--keep-config", action="store_true",
                    help="do not restore config.toml backup")
    args = ap.parse_args()

    adapter = pick_adapter()
    ctx = common.InstallContext(
        home=common.home_dir(),
        install_dir=os.path.join(common.home_dir(), common.INSTALL_DIRNAME),
        proxy_script="", watchdog_script="", python="",
        codex_config=common.codex_config_path(),
        log_dir=os.path.join(common.codex_home(), "log"),
        port=args.port,
    )

    _say("Uninstalling codex-dmx-proxy ...")
    _say("[1/3] deregistering watchdog service ...")
    try:
        adapter.uninstall(ctx)
    except Exception as e:
        _say(f"  (service removal note: {e})")
    _stop_proxy(args.port)

    if not args.keep_config:
        _say("[2/3] restoring config.toml ...")
        restore_config(ctx)
    else:
        _say("[2/3] keeping config (per --keep-config)")

    if args.purge:
        _say("[3/3] removing install dir ...")
        shutil.rmtree(ctx.install_dir, ignore_errors=True)
    else:
        _say(f"[3/3] leaving install dir {ctx.install_dir} (use --purge to delete)")

    _say("\nDone. Fully quit & reopen Codex to apply the reverted config.")


if __name__ == "__main__":
    main()
