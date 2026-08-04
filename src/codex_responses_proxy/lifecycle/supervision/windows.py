"""Persist the watchdog as one current-user scheduled task."""

from __future__ import annotations

import os
import subprocess
import getpass
from xml.sax.saxutils import escape as xml_escape

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import runtime as service_runtime


# A fixed past boundary so the repeating time trigger is always active; the
# repetition, not this date, drives every self-heal relaunch.
_SELF_HEAL_START_BOUNDARY = "2020-01-01T00:00:00"

TASK_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Codex Responses Proxy watchdog</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Enabled>true</Enabled>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{executable}</Command>
      <Arguments>{watchdog_mode}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _current_user() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME") or getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def _xml_path(ctx: runtime_context.RuntimeContext) -> str:
    return os.path.join(ctx.install_dir, f"{runtime_context.SERVICE_ID}.xml")


def render_task_xml(ctx: runtime_context.RuntimeContext) -> str:
    """Render the scheduled-task XML for the native watchdog role."""
    return TASK_XML_TEMPLATE.format(
        user=xml_escape(_current_user()),
        executable=xml_escape(ctx.executable),
        watchdog_mode=service_runtime.WATCHDOG_MODE,
        workdir=xml_escape(ctx.install_dir),
        start_boundary=_SELF_HEAL_START_BOUNDARY,
    )


def install(ctx: runtime_context.RuntimeContext) -> None:
    """Install and start the Windows scheduled watchdog task."""
    xml_path = _xml_path(ctx)
    # Task Scheduler is happiest importing UTF-16 XML.
    with open(xml_path, "w", encoding="utf-16") as fh:
        fh.write(render_task_xml(ctx))

    subprocess.run(
        ["schtasks", "/delete", "/tn", runtime_context.SERVICE_ID, "/f"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    r = subprocess.run(
        ["schtasks", "/create", "/tn", runtime_context.SERVICE_ID, "/xml", xml_path],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise errors.InstallError(f"schtasks create failed: {r.stderr.strip() or r.stdout.strip()}")
    # Start it now (the trigger otherwise only fires at next logon).
    subprocess.run(
        ["schtasks", "/run", "/tn", runtime_context.SERVICE_ID],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _running_watchdog_pids(ctx: runtime_context.RuntimeContext) -> list[int]:
    """Return PIDs exactly naming this installation's native watchdog role."""

    return process.pids_naming_executable(ctx.executable, roles={service_runtime.WATCHDOG_MODE})


def uninstall(ctx: runtime_context.RuntimeContext) -> None:
    """Stop and remove only this installation's scheduled watchdog task."""
    deleted = subprocess.run(
        ["schtasks", "/delete", "/tn", runtime_context.SERVICE_ID, "/f"],
        capture_output=True,
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


def status(ctx: runtime_context.RuntimeContext) -> str:
    """Return the Windows scheduled task's read-only status classification."""
    r = subprocess.run(
        ["schtasks", "/query", "/tn", runtime_context.SERVICE_ID, "/fo", "list"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return "absent"
    if "Running" in r.stdout:
        return "running"
    return "installed"
