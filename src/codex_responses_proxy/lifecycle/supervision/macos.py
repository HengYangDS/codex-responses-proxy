"""Persist one Background watchdog in the current user's launchd domain."""

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
from codex_responses_proxy.lifecycle import owned_files
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import inventory
from codex_responses_proxy.service import runtime as service_runtime

if TYPE_CHECKING:
    from codex_responses_proxy.lifecycle import runtime_spec

_SERVICE_ABSENT = 113
_PID = re.compile(r"(?m)^\s*pid = (?P<pid>[1-9][0-9]*)\s*$")
_GUI_ASID = re.compile(r"(?m)^\tgui asid = [1-9][0-9]*\s*$")


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
    return f"user/{uid}"


def _service_target(ctx: runtime_spec.NativeServiceContext, domain: str) -> str:
    return f"{domain}/{ctx.service_id}"


def _domains() -> tuple[str, ...]:
    """Prove the user domain and observe GUI services only for an associated login."""
    domain = _domain_target()
    completed = subprocess.run(
        [_native_tool("launchctl"), "print", domain],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        raise errors.NativeServiceUnavailableError(
            "a reachable launchd user domain is required for macOS installation"
        )
    if (
        not completed.stdout.startswith(f"{domain} = {{\n")
        or "\ttype = user\n" not in completed.stdout
    ):
        raise errors.InstallError("launchd user-domain identity is unproved")
    if _GUI_ASID.search(completed.stdout):
        return domain, domain.replace("user/", "gui/", 1)
    return (domain,)


def _service(ctx: runtime_spec.NativeServiceContext, domain: str) -> _Service:
    completed = subprocess.run(
        [_native_tool("launchctl"), "print", _service_target(ctx, domain)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode == _SERVICE_ABSENT:
        return _Service(False, None)
    if completed.returncode:
        msg = f"launchctl print failed (exit {completed.returncode})"
        raise errors.InstallError(msg)
    match = _PID.search(completed.stdout)
    return _Service(True, int(match.group("pid")) if match else None)


def _registered_service(
    ctx: runtime_spec.NativeServiceContext,
) -> tuple[str, _Service]:
    """Observe every applicable domain and reject competing registrations."""
    domains = _domains()
    registered = [
        (domain, current) for domain in domains if (current := _service(ctx, domain)).registered
    ]
    if len(registered) > 1:
        raise errors.InstallError("launchd watchdog is registered in both user and GUI domains")
    return registered[0] if registered else (domains[0], _Service(False, None))


def _require_success(completed: subprocess.CompletedProcess[str], operation: str) -> None:
    if completed.returncode:
        msg = f"launchctl {operation} failed (exit {completed.returncode})"
        raise errors.InstallError(msg)


def render_plist(ctx: runtime_spec.NativeServiceContext) -> str:
    """Serialize the minimal launchd projection for one installed runtime."""
    payload = {
        "Label": ctx.service_id,
        "ProgramArguments": [ctx.executable, service_runtime.WATCHDOG_MODE],
        "LimitLoadToSessionType": "Background",
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": config.path_join(ctx.log_dir, "watchdog.stderr.log"),
        "EnvironmentVariables": {"HOME": ctx.user_home},
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode()


def _carrier(ctx: runtime_spec.NativeServiceContext) -> tuple[bytes, str] | None:
    """Read only a regular launch-agent file bound to this home and installation."""
    home = Path(ctx.user_home)
    target = Path(_plist_path(ctx))
    relative = target.relative_to(home).as_posix()
    target = owned_files.regular_file(home, relative, "macOS launch-agent carrier", missing_ok=True)
    if target is None:
        return None
    content = owned_files.read_bytes(target, root=home, label="macOS launch-agent carrier")
    try:
        payload = plistlib.loads(content)
    except plistlib.InvalidFileException as exc:
        raise errors.InstallError("macOS launch-agent carrier is invalid") from exc
    arguments = payload.get("ProgramArguments") if isinstance(payload, dict) else None
    environment = payload.get("EnvironmentVariables") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("Label") != ctx.service_id
        or not isinstance(arguments, list)
        or len(arguments) != 2
        or not all(isinstance(value, str) for value in arguments)
        or arguments[1] != service_runtime.WATCHDOG_MODE
        or environment != {"HOME": ctx.user_home}
        or payload.get("LimitLoadToSessionType", "Background") != "Background"
    ):
        raise errors.InstallError("macOS launch-agent carrier ownership is unproved")
    executable = arguments[0]
    if not isinstance(executable, str):
        raise errors.InstallError("macOS launch-agent executable ownership is unproved")
    path = Path(executable)
    resolved = path.resolve()
    root = Path(ctx.install_dir).resolve()
    if (
        not path.is_absolute()
        or not resolved.is_relative_to(root)
        or path.name != Path(ctx.executable).name
        or path.parent.name != "bin"
        or payload.get("Program", executable) != executable
    ):
        raise errors.InstallError("macOS launch-agent executable ownership is unproved")
    relative = resolved.relative_to(root)
    if relative != Path(inventory.EXECUTABLE):
        if len(relative.parts) != 4 or relative.parts[0] != identity.PAYLOAD_GENERATIONS_DIRNAME:
            raise errors.InstallError("macOS launch-agent executable ownership is unproved")
        try:
            identity.require_payload_generation_name(relative.parts[1])
        except ValueError as exc:
            raise errors.InstallError(
                "macOS launch-agent generation ownership is unproved"
            ) from exc
    return content, executable


def configured_executable(ctx: runtime_spec.NativeServiceContext) -> str | None:
    """Return an owned native watchdog executable, or absence of its carrier."""
    carrier = _carrier(ctx)
    return carrier[1] if carrier is not None else None


def install(ctx: runtime_spec.NativeServiceContext) -> None:
    """Replace and prove one exact launchd watchdog process generation."""
    plist = _plist_path(ctx)
    previous_carrier = _carrier(ctx)
    previous_executable = previous_carrier[1] if previous_carrier is not None else None
    previous_domain, previous = _registered_service(ctx)
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
            [_native_tool("launchctl"), "bootout", _service_target(ctx, previous_domain)],
            capture_output=True,
            check=False,
            text=True,
        )
        _require_success(bootout, "bootout")
    if generation is not None and not process.wait_for_exit(generation):
        msg = f"launchd watchdog generation {generation.pid} remains after bootout"
        raise errors.InstallError(msg)
    if previous.registered and _service(ctx, previous_domain).registered:
        raise errors.InstallError("launchd watchdog remains registered after bootout")
    if _carrier(ctx) != previous_carrier:
        raise errors.InstallError("macOS launch-agent carrier changed before replacement")

    Path(ctx.log_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    owned_files.write_bytes(Path(plist), render_plist(ctx).encode(), root=Path(ctx.user_home))
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
        [_native_tool("launchctl"), "kickstart", "-p", _service_target(ctx, _domain_target())],
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
    observed = _service(ctx, _domain_target())
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
    previous_carrier = _carrier(ctx)
    domain, current = _registered_service(ctx)
    generation = None
    if current.pid is not None:
        executable = previous_carrier[1] if previous_carrier is not None else None
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
            [_native_tool("launchctl"), "bootout", _service_target(ctx, domain)],
            capture_output=True,
            check=False,
            text=True,
        )
        _require_success(bootout, "bootout")
    if generation is not None and not process.wait_for_exit(generation):
        msg = f"launchd watchdog generation {generation.pid} remains after bootout"
        raise errors.InstallError(msg)
    if _service(ctx, domain).registered:
        msg = "launchd watchdog remains registered after bootout"
        raise errors.InstallError(msg)
    if _carrier(ctx) != previous_carrier:
        raise errors.InstallError("macOS launch-agent carrier changed before removal")
    Path(plist).unlink(missing_ok=True)


def status(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the macOS launchd service's read-only status classification."""
    plist = _plist_path(ctx)
    _domain, current = _registered_service(ctx)
    if current.pid is not None:
        return "running"
    return "installed" if current.registered or Path(plist).exists() else "absent"
