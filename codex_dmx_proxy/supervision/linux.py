"""Persist the watchdog with a user service or verified login fallback."""

from __future__ import annotations

import os
import shutil
import subprocess

from codex_dmx_proxy import installation
from codex_dmx_proxy import errors
from codex_dmx_proxy import process

UNIT_TEMPLATE = """[Unit]
Description=Codex DMX Proxy watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} {watchdog}
Restart=always
RestartSec=3
Environment=DMX_PROXY_PORT={port}
Environment=DMX_UPSTREAM={upstream}
Environment=DMX_PROXY_PYTHON={python}
Environment=DMX_PROXY_SCRIPT={proxy}
Environment=DMX_PROXY_LOG_MAX_BYTES={proxy_log_max_bytes}
Environment=DMX_PROXY_LOG_BACKUP_COUNT={proxy_log_backup_count}
Environment=DMX_WATCHDOG_LOG_MAX_BYTES={watchdog_log_max_bytes}
Environment=DMX_WATCHDOG_LOG_BACKUP_COUNT={watchdog_log_backup_count}

[Install]
WantedBy=default.target
"""


def _has_user_systemd() -> bool:
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True, text=True)
    # Any answer other than a bus-connection failure means a user manager exists.
    return "Failed to connect to bus" not in (r.stderr + r.stdout)


def _unit_path(ctx: installation.InstallContext) -> str:
    return os.path.join(ctx.home, ".config", "systemd", "user", f"{installation.LABEL}.service")


def _cron_wrapper_path(ctx: installation.InstallContext) -> str:
    return os.path.join(ctx.install_dir, "watchdog", "run-watchdog.sh")


def render_unit(ctx: installation.InstallContext) -> str:
    """Render the user-level systemd watchdog unit for this installation."""
    return UNIT_TEMPLATE.format(
        python=ctx.python,
        watchdog=ctx.watchdog_script,
        proxy=ctx.proxy_script,
        port=ctx.port,
        upstream=ctx.upstream,
        proxy_log_max_bytes=ctx.proxy_log_max_bytes,
        proxy_log_backup_count=ctx.proxy_log_backup_count,
        watchdog_log_max_bytes=ctx.watchdog_log_max_bytes,
        watchdog_log_backup_count=ctx.watchdog_log_backup_count,
    )


def _install_systemd(ctx: installation.InstallContext) -> None:
    unit = _unit_path(ctx)
    os.makedirs(os.path.dirname(unit), exist_ok=True)
    with open(unit, "w", encoding="utf-8") as fh:
        fh.write(render_unit(ctx))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    r = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{installation.LABEL}.service"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise errors.InstallError(f"systemctl enable failed: {r.stderr.strip()}")
    # Survive logout / start at boot. Best-effort: on hardened hosts this may need
    # an admin once; we don't fail the install if it can't self-authorize.
    subprocess.run(
        ["loginctl", "enable-linger", os.environ.get("USER", "")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _install_cron(ctx: installation.InstallContext) -> None:
    """Fallback: cron @reboot launches a restart-loop wrapper (most portable
    non-root 'start at boot' + 'restart on crash' primitive)."""
    wrapper = _cron_wrapper_path(ctx)
    os.makedirs(os.path.dirname(wrapper), exist_ok=True)
    with open(wrapper, "w", encoding="utf-8") as fh:
        fh.write(
            "#!/bin/sh\n"
            f'export DMX_PROXY_PORT="{ctx.port}"\n'
            f'export DMX_UPSTREAM="{ctx.upstream}"\n'
            f'export DMX_PROXY_PYTHON="{ctx.python}"\n'
            f'export DMX_PROXY_SCRIPT="{ctx.proxy_script}"\n'
            f'export DMX_PROXY_LOG_MAX_BYTES="{ctx.proxy_log_max_bytes}"\n'
            f'export DMX_PROXY_LOG_BACKUP_COUNT="{ctx.proxy_log_backup_count}"\n'
            f'export DMX_WATCHDOG_LOG_MAX_BYTES="{ctx.watchdog_log_max_bytes}"\n'
            f'export DMX_WATCHDOG_LOG_BACKUP_COUNT="{ctx.watchdog_log_backup_count}"\n'
            "while true; do\n"
            f'  "{ctx.python}" "{ctx.watchdog_script}"\n'
            "  sleep 3\n"
            "done\n"
        )
    os.chmod(wrapper, 0o755)
    if not shutil.which("crontab"):
        raise errors.ManualStartRequired(
            "no systemd user bus and no crontab: no watchdog was started because "
            "an unowned session process cannot satisfy durable supervision. "
            f"Configure a user service or login hook for {wrapper}, then reinstall."
        )
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    marker = f"# {installation.LABEL}"
    lines = [ln for ln in existing.splitlines() if marker not in ln and wrapper not in ln]
    lines.append(f"@reboot {wrapper}  {marker}")
    proc = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)
    if proc.returncode != 0:
        raise errors.InstallError("failed to install crontab @reboot entry")
    # Start it now too (cron only fires at boot).
    subprocess.Popen(
        [wrapper], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )


def install(ctx: installation.InstallContext) -> None:
    """Install and start the Linux user-level watchdog service."""
    if _has_user_systemd():
        _install_systemd(ctx)
    else:
        _install_cron(ctx)


def uninstall(ctx: installation.InstallContext) -> None:
    """Stop and remove only this installation's Linux watchdog service."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        if not shutil.which("systemctl"):
            raise errors.InstallError("systemctl is unavailable; service removal is unproven")
        disabled = subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{installation.LABEL}.service"],
            capture_output=True,
            text=True,
        )
        if disabled.returncode:
            detail = disabled.stderr.strip() or disabled.stdout.strip()
            raise errors.InstallError(f"systemctl disable failed: {detail}")
        os.remove(unit)
        reloaded = subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            text=True,
        )
        if reloaded.returncode:
            raise errors.InstallError("systemctl daemon-reload failed after unit removal")
        if status(ctx) != "absent":
            raise errors.InstallError("systemd watchdog remains registered after removal")
    if shutil.which("crontab"):
        listed = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if listed.returncode not in (0, 1):
            raise errors.InstallError("crontab inventory failed")
        marker = f"# {installation.LABEL}"
        if marker in listed.stdout:
            lines = [line for line in listed.stdout.splitlines() if marker not in line]
            removed = subprocess.run(
                ["crontab", "-"],
                input="\n".join(lines) + "\n",
                capture_output=True,
                text=True,
            )
            if removed.returncode:
                raise errors.InstallError("crontab removal failed")
            verified = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if verified.returncode not in (0, 1) or marker in verified.stdout:
                raise errors.InstallError("cron watchdog remains registered after removal")
    watchdogs = process.pids_naming_path(ctx.watchdog_script)
    for pid in watchdogs:
        if not process.terminate_pid(pid, expected_path=ctx.watchdog_script):
            raise errors.InstallError(f"verified watchdog {pid} did not exit")
    if remaining := process.pids_naming_path(ctx.watchdog_script):
        raise errors.InstallError(f"verified watchdogs remain: {remaining}")


def status(ctx: installation.InstallContext) -> str:
    """Return the Linux service manager's read-only status classification."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        r = subprocess.run(
            ["systemctl", "--user", "is-active", f"{installation.LABEL}.service"],
            capture_output=True,
            text=True,
        )
        return "running" if r.stdout.strip() == "active" else "installed"
    if shutil.which("crontab"):
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        if f"# {installation.LABEL}" in existing:
            return "installed"
    return "absent"
