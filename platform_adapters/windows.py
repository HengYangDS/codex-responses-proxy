"""windows — register the watchdog as a per-user Scheduled Task.

Standard user, no admin: a task in the user's own context with an at-logon trigger
and restart-on-failure. Key correctness points (from research):
  * <ExecutionTimeLimit>PT0S</ExecutionTimeLimit> — else Task Scheduler kills the
    long-lived watchdog after the 72h default.
  * pythonw.exe — no console window flashes at logon.
  * InteractiveToken + LeastPrivilege — runs admin-free and password-free.
  * schtasks command line cannot combine ONLOGON + restart, so we import XML.
"""

from __future__ import annotations

import os
import subprocess
import getpass

from . import common

TASK_NAME = "CodexDmxWatchdog"

TASK_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Codex dmx-responses-proxy watchdog</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
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
      <Command>{pythonw}</Command>
      <Arguments>"{watchdog}"</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _current_user() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME") or getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def _xml_path(ctx: common.InstallContext) -> str:
    return os.path.join(ctx.install_dir, f"{TASK_NAME}.xml")


def render_task_xml(ctx: common.InstallContext) -> str:
    return TASK_XML_TEMPLATE.format(
        user=_current_user(),
        pythonw=common.windows_pythonw(ctx.python),
        watchdog=ctx.watchdog_script,
        workdir=ctx.install_dir,
    )


def install(ctx: common.InstallContext) -> None:
    xml_path = _xml_path(ctx)
    # Task Scheduler is happiest importing UTF-16 XML.
    with open(xml_path, "w", encoding="utf-16") as fh:
        fh.write(render_task_xml(ctx))

    # Persist the watchdog env for the proxy the task will spawn. The task runs the
    # watchdog which reads these from its own process env; since the task XML can't
    # easily carry env, we write a tiny launcher .cmd that sets them then runs python.
    launcher = os.path.join(ctx.install_dir, "run-watchdog.cmd")
    with open(launcher, "w", encoding="utf-8") as fh:
        fh.write(
            "@echo off\r\n"
            f'set DMX_PROXY_PORT={ctx.port}\r\n'
            f'set DMX_UPSTREAM={ctx.upstream}\r\n'
            f'set DMX_PROXY_PYTHON={ctx.python}\r\n'
            f'set DMX_PROXY_SCRIPT={ctx.proxy_script}\r\n'
            f'"{common.windows_pythonw(ctx.python)}" "{ctx.watchdog_script}"\r\n'
        )

    subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run(["schtasks", "/create", "/tn", TASK_NAME, "/xml", xml_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise common.InstallError(f"schtasks create failed: {r.stderr.strip() or r.stdout.strip()}")
    # Start it now (the trigger otherwise only fires at next logon).
    subprocess.run(["schtasks", "/run", "/tn", TASK_NAME],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def uninstall(ctx: common.InstallContext) -> None:
    subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def status(ctx: common.InstallContext) -> str:
    r = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "list"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "absent"
    if "Running" in r.stdout:
        return "running"
    return "installed"
