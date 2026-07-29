"""Persist the watchdog as one launchd user agent."""

from __future__ import annotations

import os
import subprocess

from codex_dmx_proxy import installation
from codex_dmx_proxy import errors

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>{watchdog}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>/dev/null</string>
  <key>StandardErrorPath</key>
  <string>/dev/null</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>DMX_PROXY_PORT</key>
    <string>{port}</string>
    <key>DMX_UPSTREAM</key>
    <string>{upstream}</string>
    <key>DMX_PROXY_PYTHON</key>
    <string>{python}</string>
    <key>DMX_PROXY_SCRIPT</key>
    <string>{proxy}</string>
    <key>DMX_PROXY_LOG_MAX_BYTES</key>
    <string>{proxy_log_max_bytes}</string>
    <key>DMX_PROXY_LOG_BACKUP_COUNT</key>
    <string>{proxy_log_backup_count}</string>
    <key>DMX_WATCHDOG_LOG_MAX_BYTES</key>
    <string>{watchdog_log_max_bytes}</string>
    <key>DMX_WATCHDOG_LOG_BACKUP_COUNT</key>
    <string>{watchdog_log_backup_count}</string>
  </dict>
</dict>
</plist>
"""


def _plist_path(ctx: installation.InstallContext) -> str:
    return os.path.join(ctx.home, "Library", "LaunchAgents", f"{installation.LABEL}.plist")


def render_plist(ctx: installation.InstallContext) -> str:
    """Render the launchd property list for this installation's watchdog."""
    return PLIST_TEMPLATE.format(
        label=installation.LABEL,
        python=ctx.python,
        watchdog=ctx.watchdog_script,
        proxy=ctx.proxy_script,
        log_dir=ctx.log_dir,
        port=ctx.port,
        upstream=ctx.upstream,
        proxy_log_max_bytes=ctx.proxy_log_max_bytes,
        proxy_log_backup_count=ctx.proxy_log_backup_count,
        watchdog_log_max_bytes=ctx.watchdog_log_max_bytes,
        watchdog_log_backup_count=ctx.watchdog_log_backup_count,
    )


def install(ctx: installation.InstallContext) -> None:
    """Install and bootstrap the macOS launchd watchdog service."""
    plist = _plist_path(ctx)
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    with open(plist, "w", encoding="utf-8") as fh:
        fh.write(render_plist(ctx))

    # Validate the plist we just wrote (fail-loud).
    subprocess.run(["plutil", "-lint", plist], check=True, stdout=subprocess.DEVNULL)

    # Clean any prior instance, then load -w (the -w clears a 'disabled' label,
    # which a plain bootstrap cannot — that was the real cause of the observed
    # 'bootstrap failed 5: Input/output error').
    subprocess.run(
        ["launchctl", "unload", plist], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    r = subprocess.run(["launchctl", "load", "-w", plist], capture_output=True, text=True)
    if r.returncode != 0:
        raise errors.InstallError(f"launchctl load failed: {r.stderr.strip()}")


def uninstall(ctx: installation.InstallContext) -> None:
    """Boot out and remove only this installation's launchd service."""
    plist = _plist_path(ctx)
    if os.path.exists(plist):
        unloaded = subprocess.run(["launchctl", "unload", plist], capture_output=True, text=True)
        if unloaded.returncode:
            detail = unloaded.stderr.strip() or unloaded.stdout.strip()
            raise errors.InstallError(f"launchctl unload failed: {detail}")
        listed = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        if listed.returncode or installation.LABEL in listed.stdout:
            raise errors.InstallError("launchd watchdog remains registered after unload")
        os.remove(plist)


def status(ctx: installation.InstallContext) -> str:
    """Return the macOS launchd service's read-only status classification."""
    plist = _plist_path(ctx)
    if not os.path.exists(plist):
        return "absent"
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if installation.LABEL in r.stdout:
        return "running"
    return "installed"
