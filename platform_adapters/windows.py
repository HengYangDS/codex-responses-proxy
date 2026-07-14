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
from xml.sax.saxutils import escape as xml_escape

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
      <Command>{comspec}</Command>
      <Arguments>/d /c ""{launcher}""</Arguments>
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


def _launcher_path(ctx: common.InstallContext) -> str:
    return os.path.join(ctx.install_dir, "run-watchdog.cmd")


def render_launcher(ctx: common.InstallContext) -> str:
    """Render the only process entry point that carries watchdog configuration."""
    pythonw = common.windows_pythonw(ctx.python)
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "DMX_PROXY_PORT={ctx.port}"\r\n'
        f'set "DMX_UPSTREAM={ctx.upstream}"\r\n'
        f'set "DMX_PROXY_PYTHON={ctx.python}"\r\n'
        f'set "DMX_PROXY_SCRIPT={ctx.proxy_script}"\r\n'
        f'"{pythonw}" "{ctx.watchdog_script}"\r\n'
    )


def render_task_xml(ctx: common.InstallContext) -> str:
    return TASK_XML_TEMPLATE.format(
        user=xml_escape(_current_user()),
        comspec=xml_escape(os.environ.get("ComSpec", r"C:\\Windows\\System32\\cmd.exe")),
        launcher=xml_escape(_launcher_path(ctx)),
        workdir=xml_escape(ctx.install_dir),
    )


def install(ctx: common.InstallContext) -> None:
    xml_path = _xml_path(ctx)
    launcher = _launcher_path(ctx)
    # The Task executes this launcher, so every future scheduled restart retains
    # the installer-selected port, upstream, interpreter, and proxy path.
    with open(launcher, "w", encoding="utf-8", newline="") as fh:
        fh.write(render_launcher(ctx))
    # Task Scheduler is happiest importing UTF-16 XML.
    with open(xml_path, "w", encoding="utf-16") as fh:
        fh.write(render_task_xml(ctx))

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
