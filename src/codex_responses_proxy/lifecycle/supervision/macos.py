"""Persist the watchdog as one launchd user agent."""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config
from codex_responses_proxy.service import runtime as service_runtime

if TYPE_CHECKING:
    from codex_responses_proxy.lifecycle import runtime_spec

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
    <key>HOME</key>
    <string>{home}</string>
  </dict>
</dict>
</plist>
"""
_SERVICE_ABSENT = 113
_PID = re.compile(r"(?m)^\s*pid = (?P<pid>[1-9][0-9]*)\s*$")


@dataclass(frozen=True, slots=True)
class _Service:
    registered: bool
    pid: int | None


def _native_tool(name: str) -> str:
    """Resolve one macOS system tool independently of the caller's PATH."""
    executable = shutil.which(name, path=os.defpath)
    if executable is None:
        raise errors.InstallError(f"native macOS tool is unavailable: {name}")
    return executable


def _plist_path(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the launch-agent carrier owned by this service identity."""
    return str(Path(ctx.user_home, "Library", "LaunchAgents", f"{ctx.service_id}.plist"))


def _domain_target() -> str:
    getuid: object = getattr(os, "getuid", None)
    if not callable(getuid):
        raise errors.InstallError("macOS user identity is unavailable")
    uid = cast(Callable[[], int], getuid)()
    return f"gui/{uid}"


def _service_target(ctx: runtime_spec.NativeServiceContext) -> str:
    return f"{_domain_target()}/{ctx.service_id}"


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"


def _service(ctx: runtime_spec.NativeServiceContext) -> _Service:
    completed = subprocess.run(
        [_native_tool("launchctl"), "print", _service_target(ctx)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode == _SERVICE_ABSENT:
        return _Service(False, None)
    if completed.returncode:
        msg = f"launchctl print failed: {_detail(completed)}"
        raise errors.InstallError(msg)
    match = _PID.search(completed.stdout)
    return _Service(True, int(match.group("pid")) if match else None)


def _require_success(completed: subprocess.CompletedProcess[str], operation: str) -> None:
    if completed.returncode:
        msg = f"launchctl {operation} failed: {_detail(completed)}"
        raise errors.InstallError(msg)


def render_plist(ctx: runtime_spec.NativeServiceContext) -> str:
    """Serialize the minimal launchd projection for one installed runtime."""
    payload = {
        "Label": ctx.service_id,
        "ProgramArguments": [ctx.executable, service_runtime.WATCHDOG_MODE],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": config.path_join(ctx.log_dir, "watchdog.stderr.log"),
        "EnvironmentVariables": {"HOME": ctx.user_home},
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode()


def configured_executable(ctx: runtime_spec.NativeServiceContext) -> str | None:
    """Return the executable declared by one valid product launch agent."""
    try:
        with Path(_plist_path(ctx)).open("rb") as handle:
            payload = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    arguments = payload.get("ProgramArguments") if isinstance(payload, dict) else None
    if (
        not isinstance(arguments, list)
        or len(arguments) != 2
        or not all(isinstance(value, str) for value in arguments)
        or arguments[1] != service_runtime.WATCHDOG_MODE
    ):
        return None
    executable = arguments[0]
    return executable if isinstance(executable, str) else None


def install(ctx: runtime_spec.NativeServiceContext) -> None:
    """Replace and prove one exact launchd watchdog process generation."""
    plist = _plist_path(ctx)
    previous_executable = configured_executable(ctx)
    previous = _service(ctx)
    generation = None
    if previous.pid is not None:
        if previous_executable is None:
            msg = "registered launchd watchdog executable is unproved"
            raise errors.InstallError(msg)
        generation = process.capture_executable(
            previous.pid,
            previous_executable,
            roles={service_runtime.WATCHDOG_MODE},
        )
        if generation is None:
            msg = "registered launchd watchdog process identity is unproved"
            raise errors.InstallError(msg)
    if previous.registered:
        bootout = subprocess.run(
            [_native_tool("launchctl"), "bootout", _service_target(ctx)],
            capture_output=True,
            check=False,
            text=True,
        )
        _require_success(bootout, "bootout")
    if generation is not None and not process.wait_for_exit(generation):
        msg = f"launchd watchdog generation {generation.pid} remains after bootout"
        raise errors.InstallError(msg)

    Path(ctx.log_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    Path(plist).parent.mkdir(parents=True, exist_ok=True)
    Path(plist).write_text(render_plist(ctx), encoding="utf-8")
    subprocess.run(
        [_native_tool("plutil"), "-lint", plist],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    bootstrap = subprocess.run(
        [_native_tool("launchctl"), "bootstrap", _domain_target(), plist],
        capture_output=True,
        check=False,
        text=True,
    )
    _require_success(bootstrap, "bootstrap")
    kickstart = subprocess.run(
        [_native_tool("launchctl"), "kickstart", "-p", _service_target(ctx)],
        capture_output=True,
        check=False,
        text=True,
    )
    _require_success(kickstart, "kickstart")
    try:
        successor_pid = int(kickstart.stdout.strip())
    except ValueError as error:
        msg = "launchctl kickstart returned no watchdog pid"
        raise errors.InstallError(msg) from error
    observed = _service(ctx)
    if observed.pid != successor_pid:
        msg = "launchd watchdog pid was not re-observed for the exact service"
        raise errors.InstallError(msg)
    if previous.pid is not None and successor_pid == previous.pid:
        msg = "launchd watchdog generation did not change"
        raise errors.InstallError(msg)
    successor = process.wait_for_executable(
        successor_pid,
        ctx.executable,
        roles={service_runtime.WATCHDOG_MODE},
    )
    if successor is None or not process.owned_process_alive(successor):
        msg = "launchd successor watchdog process identity is unproved"
        raise errors.InstallError(msg)


def uninstall(ctx: runtime_spec.NativeServiceContext) -> None:
    """Boot out and remove only this installation's launchd service."""
    plist = _plist_path(ctx)
    current = _service(ctx)
    generation = None
    if current.pid is not None:
        executable = configured_executable(ctx)
        if executable is None:
            msg = "registered launchd watchdog executable is unproved"
            raise errors.InstallError(msg)
        generation = process.wait_for_executable(
            current.pid,
            executable,
            roles={service_runtime.WATCHDOG_MODE},
        )
        if generation is None:
            msg = "registered launchd watchdog process identity is unproved"
            raise errors.InstallError(msg)
    if current.registered:
        bootout = subprocess.run(
            [_native_tool("launchctl"), "bootout", _service_target(ctx)],
            capture_output=True,
            check=False,
            text=True,
        )
        _require_success(bootout, "bootout")
    if generation is not None and not process.wait_for_exit(generation):
        msg = f"launchd watchdog generation {generation.pid} remains after bootout"
        raise errors.InstallError(msg)
    if _service(ctx).registered:
        msg = "launchd watchdog remains registered after bootout"
        raise errors.InstallError(msg)
    Path(plist).unlink(missing_ok=True)


def status(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the macOS launchd service's read-only status classification."""
    plist = _plist_path(ctx)
    if not Path(plist).exists():
        return "absent"
    return "running" if _service(ctx).pid is not None else "installed"
