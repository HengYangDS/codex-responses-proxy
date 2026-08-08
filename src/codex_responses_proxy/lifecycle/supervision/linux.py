"""Persist the watchdog with a user service or verified login fallback."""

from __future__ import annotations

import os
import shutil
import subprocess

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import runtime as service_runtime

UNIT_TEMPLATE = """[Unit]
Description=Codex Responses Proxy watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={executable} {watchdog_mode}
Restart=always
RestartSec=3
{environment}

[Install]
WantedBy=default.target
"""


def _systemd_environment(ctx: runtime_context.RuntimeContext) -> str:
    return "\n".join(
        f"Environment={key}={value}" for key, value in ctx.service_environment().items()
    )


def _has_user_systemd() -> bool:
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True, text=True)
    # Any answer other than a bus-connection failure means a user manager exists.
    return "Failed to connect to bus" not in (r.stderr + r.stdout)


def _unit_path(ctx: runtime_context.RuntimeContext) -> str:
    return os.path.join(
        ctx.home, ".config", "systemd", "user", f"{runtime_context.SERVICE_ID}.service"
    )


def render_unit(ctx: runtime_context.RuntimeContext) -> str:
    """Render the user-level systemd watchdog unit for this installation."""
    return UNIT_TEMPLATE.format(
        executable=ctx.executable,
        watchdog_mode=service_runtime.WATCHDOG_MODE,
        environment=_systemd_environment(ctx),
    )


def _install_systemd(ctx: runtime_context.RuntimeContext) -> None:
    unit = _unit_path(ctx)
    os.makedirs(os.path.dirname(unit), exist_ok=True)
    with open(unit, "w", encoding="utf-8") as fh:
        fh.write(render_unit(ctx))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    r = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{runtime_context.SERVICE_ID}.service"],
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


def install(ctx: runtime_context.RuntimeContext) -> None:
    """Install and start the Linux user-level watchdog service."""
    if _has_user_systemd():
        _install_systemd(ctx)
    else:
        raise errors.ManualStartRequired(
            "a systemd user manager is required for durable Linux supervision; "
            f"run {ctx.executable} {service_runtime.WATCHDOG_MODE} from a native user service"
        )


def uninstall(ctx: runtime_context.RuntimeContext) -> None:
    """Stop and remove only this installation's Linux watchdog service."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        if not shutil.which("systemctl"):
            raise errors.InstallError("systemctl is unavailable; service removal is unproven")
        disabled = subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{runtime_context.SERVICE_ID}.service"],
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
    watchdogs = process.pids_naming_executable(
        ctx.executable, roles={service_runtime.WATCHDOG_MODE}
    )
    for pid in watchdogs:
        if not process.terminate_executable(
            pid, ctx.executable, roles={service_runtime.WATCHDOG_MODE}
        ):
            raise errors.InstallError(f"verified watchdog {pid} did not exit")
    if remaining := process.pids_naming_executable(
        ctx.executable, roles={service_runtime.WATCHDOG_MODE}
    ):
        raise errors.InstallError(f"verified watchdogs remain: {remaining}")


def status(ctx: runtime_context.RuntimeContext) -> str:
    """Return the Linux service manager's read-only status classification."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        r = subprocess.run(
            ["systemctl", "--user", "is-active", f"{runtime_context.SERVICE_ID}.service"],
            capture_output=True,
            text=True,
        )
        return "running" if r.stdout.strip() == "active" else "installed"
    return "absent"
