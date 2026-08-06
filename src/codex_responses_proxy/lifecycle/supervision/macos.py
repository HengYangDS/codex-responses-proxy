"""Persist the watchdog as one launchd user agent."""

from __future__ import annotations

import os
import subprocess

from codex_responses_proxy.runtime import config
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy import errors
from codex_responses_proxy.service import runtime as service_runtime

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{executable}</string>
    <string>{watchdog_mode}</string>
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
  <string>{stderr_log}</string>
  <key>EnvironmentVariables</key>
  <dict>
{environment}
  </dict>
</dict>
</plist>
"""


def _environment_xml(ctx: runtime_context.RuntimeContext) -> str:
    return "\n".join(
        f"    <key>{key}</key>\n    <string>{value}</string>"
        for key, value in ctx.service_environment().items()
    )


def _plist_path(ctx: runtime_context.RuntimeContext) -> str:
    return os.path.join(ctx.home, "Library", "LaunchAgents", f"{runtime_context.SERVICE_ID}.plist")


def render_plist(ctx: runtime_context.RuntimeContext) -> str:
    """Render a watchdog service whose pre-logging failures remain visible."""
    return PLIST_TEMPLATE.format(
        label=runtime_context.SERVICE_ID,
        executable=ctx.executable,
        watchdog_mode=service_runtime.WATCHDOG_MODE,
        stderr_log=config.path_join(ctx.log_dir, "watchdog.stderr.log"),
        environment=_environment_xml(ctx),
    )


def install(ctx: runtime_context.RuntimeContext) -> None:
    """Install and bootstrap the macOS launchd watchdog service."""
    plist = _plist_path(ctx)
    os.makedirs(ctx.log_dir, mode=0o700, exist_ok=True)
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


def uninstall(ctx: runtime_context.RuntimeContext) -> None:
    """Boot out and remove only this installation's launchd service."""
    plist = _plist_path(ctx)
    if os.path.exists(plist):
        unloaded = subprocess.run(["launchctl", "unload", plist], capture_output=True, text=True)
        if unloaded.returncode:
            detail = unloaded.stderr.strip() or unloaded.stdout.strip()
            raise errors.InstallError(f"launchctl unload failed: {detail}")
        listed = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        if listed.returncode or runtime_context.SERVICE_ID in listed.stdout:
            raise errors.InstallError("launchd watchdog remains registered after unload")
        os.remove(plist)


def status(ctx: runtime_context.RuntimeContext) -> str:
    """Return the macOS launchd service's read-only status classification."""
    plist = _plist_path(ctx)
    if not os.path.exists(plist):
        return "absent"
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if runtime_context.SERVICE_ID in r.stdout:
        return "running"
    return "installed"
