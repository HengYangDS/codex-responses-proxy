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
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from platform_adapters import pick_adapter, common  # noqa: E402


def _say(msg: str) -> None:
    print(msg, flush=True)


def _listener_pids(port: int) -> list[int]:
    """Return only PIDs listening on the requested loopback TCP port."""
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            ).stdout
            pids = []
            for line in output.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[1].endswith(f":{port}") and fields[3].upper() == "LISTENING":
                    try:
                        pids.append(int(fields[-1]))
                    except ValueError:
                        pass
            return pids
        output = subprocess.run(
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
            capture_output=True, text=True,
        ).stdout
        return [int(value) for value in output.split() if value.isdigit()]
    except Exception:
        return []


def _process_command(pid: int) -> str:
    try:
        if os.name == "nt":
            command = (
                "$p=Get-CimInstance Win32_Process -Filter \"ProcessId=" + str(pid) + "\";"
                "if ($p) {$p.CommandLine}"
            )
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True, text=True,
            ).stdout.strip()
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return ""


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/pid", str(pid), "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _stop_proxy(port: int) -> int:
    """Terminate only a port listener proven to be this proxy. Returns count."""
    stopped = 0
    for pid in _listener_pids(port):
        if "dmx_responses_proxy.py" not in _process_command(pid):
            continue
        _terminate_pid(pid)
        stopped += 1
    return stopped


def restore_config(ctx: common.InstallContext) -> bool:
    state = common.load_install_state(ctx)
    if state is None:
        _say("  no valid managed route state found; leaving config.toml as-is.")
        return False
    if common.route_status(ctx, state) != "enabled":
        _say("  config is disabled or drifted; leaving it unchanged.")
        return False
    backup = state["backup_path"]
    if not os.path.isfile(backup):
        _say("  recorded config backup is unavailable; leaving config.toml as-is.")
        return False
    with open(ctx.codex_config, "r", encoding="utf-8") as fh:
        current = fh.read()
    direct = state["direct_urls"][0]
    restored, changed = common._replace_managed_urls(current, [state["proxy_url"]], direct)
    if changed == 0:
        _say("  managed proxy route was not found; leaving config.toml as-is.")
        return False
    common._atomic_write_text(ctx.codex_config, restored)
    common.remove_install_state(ctx)
    _say(f"  restored config from {os.path.basename(backup)}")
    return True


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
