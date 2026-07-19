"""linux — register the watchdog via systemd --user (preferred) or a cron @reboot
restart-loop fallback when there is no user systemd bus (minimal containers, WSL1,
some hardened hosts).

No root required in the systemd path: user units live under
~/.config/systemd/user/ and ``loginctl enable-linger`` makes them start at boot.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from . import common

UNIT_TEMPLATE = """[Unit]
Description=Codex dmx-responses-proxy watchdog
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
    r = subprocess.run(["systemctl", "--user", "is-system-running"],
                       capture_output=True, text=True)
    # Any answer other than a bus-connection failure means a user manager exists.
    return "Failed to connect to bus" not in (r.stderr + r.stdout)


def _unit_path(ctx: common.InstallContext) -> str:
    return os.path.join(ctx.home, ".config", "systemd", "user", f"{common.LABEL}.service")


def _cron_wrapper_path(ctx: common.InstallContext) -> str:
    return os.path.join(ctx.install_dir, "watchdog", "run-watchdog.sh")


def render_unit(ctx: common.InstallContext) -> str:
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


def _install_systemd(ctx: common.InstallContext) -> None:
    unit = _unit_path(ctx)
    os.makedirs(os.path.dirname(unit), exist_ok=True)
    with open(unit, "w", encoding="utf-8") as fh:
        fh.write(render_unit(ctx))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    r = subprocess.run(["systemctl", "--user", "enable", "--now", f"{common.LABEL}.service"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise common.InstallError(f"systemctl enable failed: {r.stderr.strip()}")
    # Survive logout / start at boot. Best-effort: on hardened hosts this may need
    # an admin once; we don't fail the install if it can't self-authorize.
    subprocess.run(["loginctl", "enable-linger", os.environ.get("USER", "")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _install_cron(ctx: common.InstallContext) -> None:
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
        # No systemd user bus AND no crontab (minimal container / locked-down host).
        # Don't abort the whole install — the files are placed and the watchdog can
        # run. Start it now for THIS session and tell the caller boot-persistence
        # needs a manual hook. This degrades gracefully instead of failing hard.
        subprocess.Popen([wrapper], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        raise common.ManualStartRequired(
            "no systemd user bus and no crontab: started the watchdog for this "
            f"session, but it won't survive reboot. To persist, add to your login "
            f"shell profile or an init hook:\n    {wrapper}"
        )
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    marker = f"# {common.LABEL}"
    lines = [ln for ln in existing.splitlines() if marker not in ln and wrapper not in ln]
    lines.append(f"@reboot {wrapper}  {marker}")
    proc = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)
    if proc.returncode != 0:
        raise common.InstallError("failed to install crontab @reboot entry")
    # Start it now too (cron only fires at boot).
    subprocess.Popen([wrapper], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def install(ctx: common.InstallContext) -> None:
    if _has_user_systemd():
        _install_systemd(ctx)
    else:
        _install_cron(ctx)


def uninstall(ctx: common.InstallContext) -> None:
    # systemd path
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{common.LABEL}.service"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(unit)
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # cron path
    if shutil.which("crontab"):
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        marker = f"# {common.LABEL}"
        if marker in existing:
            lines = [ln for ln in existing.splitlines() if marker not in ln]
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)


def status(ctx: common.InstallContext) -> str:
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        r = subprocess.run(["systemctl", "--user", "is-active", f"{common.LABEL}.service"],
                           capture_output=True, text=True)
        return "running" if r.stdout.strip() == "active" else "installed"
    if shutil.which("crontab"):
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        if f"# {common.LABEL}" in existing:
            return "installed"
    return "absent"
