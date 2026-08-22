"""Persist the watchdog with a user service or verified login fallback."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import platformdirs

from codex_responses_proxy import errors
from codex_responses_proxy import product_identity
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import runtime as service_runtime

UNIT_TEMPLATE = f"""[Unit]
Description={product_identity.DISPLAY_NAME} watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={{executable}} {{watchdog_mode}}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""


def _has_user_systemd() -> bool:
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-system-running"],
        capture_output=True,
        check=False,
        text=True,
    )
    # Any answer other than a bus-connection failure means a user manager exists.
    return "Failed to connect to bus" not in (r.stderr + r.stdout)


def _unit_path(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the systemd user-unit carrier owned by this service identity."""
    return str(platformdirs.user_config_path() / "systemd" / "user" / f"{ctx.service_id}.service")


def render_unit(ctx: runtime_spec.NativeServiceContext) -> str:
    """Render the user-level systemd watchdog unit for this installation."""
    return UNIT_TEMPLATE.format(
        executable=ctx.executable,
        watchdog_mode=service_runtime.WATCHDOG_MODE,
    )


def configured_executable(ctx: runtime_spec.NativeServiceContext) -> str | None:
    """Return the executable from one unambiguous product systemd unit."""
    try:
        lines = Path(_unit_path(ctx)).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    commands = [line.removeprefix("ExecStart=") for line in lines if line.startswith("ExecStart=")]
    if len(commands) != 1:
        return None
    try:
        arguments = shlex.split(commands[0], posix=True)
    except ValueError:
        return None
    if len(arguments) != 2 or arguments[1] != service_runtime.WATCHDOG_MODE:
        return None
    return arguments[0]


def _install_systemd(ctx: runtime_spec.NativeServiceContext) -> None:
    unit = _unit_path(ctx)
    os.makedirs(os.path.dirname(unit), exist_ok=True)
    Path(unit).write_text(render_unit(ctx), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    r = subprocess.run(
        ["systemctl", "--user", "enable", f"{ctx.service_id}.service"],
        capture_output=True,
        check=False,
        text=True,
    )
    if r.returncode != 0:
        raise errors.InstallError(f"systemctl enable failed: {r.stderr.strip()}")
    restarted = subprocess.run(
        ["systemctl", "--user", "restart", f"{ctx.service_id}.service"],
        capture_output=True,
        check=False,
        text=True,
    )
    if restarted.returncode != 0:
        detail = restarted.stderr.strip() or restarted.stdout.strip()
        raise errors.InstallError(f"systemctl restart failed: {detail}")
    # Survive logout / start at boot. Best-effort: on hardened hosts this may need
    # an admin once; we don't fail the install if it can't self-authorize.
    subprocess.run(
        ["loginctl", "enable-linger", os.environ.get("USER", "")],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install(ctx: runtime_spec.NativeServiceContext) -> None:
    """Install and start the Linux user-level watchdog service."""
    if _has_user_systemd():
        _install_systemd(ctx)
    else:
        raise errors.ManualStartRequiredError(
            "a systemd user manager is required for durable Linux supervision; "
            f"run {ctx.executable} {service_runtime.WATCHDOG_MODE} from a native user service"
        )


def uninstall(ctx: runtime_spec.NativeServiceContext) -> None:
    """Stop and remove only this installation's Linux watchdog service."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        if not shutil.which("systemctl"):
            raise errors.InstallError("systemctl is unavailable; service removal is unproven")
        disabled = subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{ctx.service_id}.service"],
            capture_output=True,
            check=False,
            text=True,
        )
        if disabled.returncode:
            detail = disabled.stderr.strip() or disabled.stdout.strip()
            raise errors.InstallError(f"systemctl disable failed: {detail}")
        os.remove(unit)
        reloaded = subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            check=False,
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


def status(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the Linux service manager's read-only status classification."""
    unit = _unit_path(ctx)
    if os.path.exists(unit):
        r = subprocess.run(
            ["systemctl", "--user", "is-active", f"{ctx.service_id}.service"],
            capture_output=True,
            check=False,
            text=True,
        )
        return "running" if r.stdout.strip() == "active" else "installed"
    return "absent"
