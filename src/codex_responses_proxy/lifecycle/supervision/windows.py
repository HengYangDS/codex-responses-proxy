"""Persist the watchdog as one current-user scheduled task."""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from codex_responses_proxy import errors
from codex_responses_proxy import product_identity
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import runtime as service_runtime

# A fixed past boundary so the repeating time trigger is always active; the
# repetition, not this date, drives every self-heal relaunch.
_SELF_HEAL_START_BOUNDARY = "2020-01-01T00:00:00"
_TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", _TASK_NAMESPACE)


def _element(
    parent: ET.Element, name: str, text: str | None = None, **attributes: str
) -> ET.Element:
    child = ET.SubElement(parent, f"{{{_TASK_NAMESPACE}}}{name}", attributes)
    child.text = text
    return child


def _current_user() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME") or getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def render_task_xml(ctx: runtime_spec.NativeServiceContext) -> str:
    """Serialize the minimal Task Scheduler projection for one runtime."""
    root = ET.Element(f"{{{_TASK_NAMESPACE}}}Task", {"version": "1.2"})
    registration = _element(root, "RegistrationInfo")
    _element(registration, "Description", f"{product_identity.DISPLAY_NAME} watchdog")
    triggers = _element(root, "Triggers")
    logon = _element(triggers, "LogonTrigger")
    _element(logon, "Enabled", "true")
    _element(logon, "UserId", _current_user())
    timed = _element(triggers, "TimeTrigger")
    _element(timed, "Enabled", "true")
    _element(timed, "StartBoundary", _SELF_HEAL_START_BOUNDARY)
    repetition = _element(timed, "Repetition")
    _element(repetition, "Interval", "PT1M")
    _element(repetition, "StopAtDurationEnd", "false")
    principals = _element(root, "Principals")
    principal = _element(principals, "Principal", id="Author")
    _element(principal, "LogonType", "InteractiveToken")
    _element(principal, "RunLevel", "LeastPrivilege")
    settings = _element(root, "Settings")
    for name, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("StartWhenAvailable", "true"),
        ("ExecutionTimeLimit", "PT0S"),
        ("Enabled", "true"),
    ):
        _element(settings, name, value)
    restart = _element(settings, "RestartOnFailure")
    _element(restart, "Interval", "PT1M")
    _element(restart, "Count", "999")
    actions = _element(root, "Actions", Context="Author")
    execute = _element(actions, "Exec")
    _element(execute, "Command", ctx.executable)
    _element(execute, "Arguments", service_runtime.WATCHDOG_MODE)
    _element(execute, "WorkingDirectory", ctx.install_dir)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def configured_executable(ctx: runtime_spec.NativeServiceContext) -> str | None:
    """Return the executable declared by the registered scheduled task."""
    completed = subprocess.run(
        ["schtasks", "/query", "/tn", ctx.service_id, "/xml"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode:
        return None
    try:
        root = ET.fromstring(completed.stdout)
    except ET.ParseError:
        return None
    namespace = {"task": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    commands = root.findall(".//task:Actions/task:Exec/task:Command", namespace)
    arguments = root.findall(".//task:Actions/task:Exec/task:Arguments", namespace)
    if (
        len(commands) != 1
        or len(arguments) != 1
        or commands[0].text is None
        or arguments[0].text != service_runtime.WATCHDOG_MODE
    ):
        return None
    return commands[0].text


def install(ctx: runtime_spec.NativeServiceContext) -> None:
    """Install and start the Windows scheduled watchdog task."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as stream:
        xml_path = stream.name
        stream.write(render_task_xml(ctx).encode("utf-16"))
    try:
        subprocess.run(
            ["schtasks", "/delete", "/tn", ctx.service_id, "/f"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        created = subprocess.run(
            ["schtasks", "/create", "/tn", ctx.service_id, "/xml", xml_path],
            capture_output=True,
            check=False,
            text=True,
        )
        if created.returncode:
            detail = created.stderr.strip() or created.stdout.strip()
            raise errors.InstallError(f"schtasks create failed: {detail}")
    finally:
        os.unlink(xml_path)
    # Start it now (the trigger otherwise only fires at next logon).
    subprocess.run(
        ["schtasks", "/run", "/tn", ctx.service_id],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _running_watchdog_pids(ctx: runtime_spec.NativeServiceContext) -> list[int]:
    """Return PIDs exactly naming this installation's native watchdog role."""
    return process.pids_naming_executable(ctx.executable, roles={service_runtime.WATCHDOG_MODE})


def uninstall(ctx: runtime_spec.NativeServiceContext) -> None:
    """Stop and remove only this installation's scheduled watchdog task."""
    deleted = subprocess.run(
        ["schtasks", "/delete", "/tn", ctx.service_id, "/f"],
        capture_output=True,
        check=False,
        text=True,
    )
    if deleted.returncode:
        if status(ctx) != "absent":
            detail = deleted.stderr.strip() or deleted.stdout.strip()
            raise errors.InstallError(f"schtasks delete failed: {detail}")
    elif status(ctx) != "absent":
        raise errors.InstallError("scheduled watchdog task remains registered after deletion")
    # PID discovery and termination are separate observations. Re-read every
    # candidate immediately before signalling so PID reuse cannot target a new
    # process that appeared between them.
    for pid in _running_watchdog_pids(ctx):
        if not process.terminate_executable(
            pid, ctx.executable, roles={service_runtime.WATCHDOG_MODE}
        ):
            raise errors.InstallError(f"verified watchdog {pid} did not exit")
    if remaining := _running_watchdog_pids(ctx):
        raise errors.InstallError(f"verified watchdogs remain: {remaining}")


def status(ctx: runtime_spec.NativeServiceContext) -> str:
    """Return the Windows scheduled task's read-only status classification."""
    r = subprocess.run(
        ["schtasks", "/query", "/tn", ctx.service_id, "/fo", "list"],
        capture_output=True,
        check=False,
        text=True,
    )
    if r.returncode != 0:
        return "absent"
    if "Running" in r.stdout:
        return "running"
    return "installed"
