"""windows — register the watchdog as a per-user Scheduled Task.

Standard user, no admin: a task in the user's own context that starts the watchdog
at logon and self-heals the watchdog itself. Key correctness points (from research
and confirmed on a real Windows host):
  * <ExecutionTimeLimit>PT0S</ExecutionTimeLimit> — else Task Scheduler kills the
    long-lived watchdog after the 72h default.
  * A repeating TimeTrigger (past StartBoundary + PT1M repetition), with
    MultipleInstancesPolicy IgnoreNew, re-launches the watchdog if the watchdog
    process itself dies. <RestartOnFailure> only reacts to a failed task *launch*,
    not to the launched process being killed later, so on a real host it never
    brought the watchdog back. A LogonTrigger <Repetition> is not enough either:
    its repetition only arms at an actual logon, so a mid-session death is not
    healed. The time-based repetition fires regardless of logon.
  * pythonw.exe runs the generated .pyw bootstrap directly, so no cmd.exe console
    window is ever allocated (a cmd /c wrapper keeps a visible console for the
    whole watchdog lifetime because it waits on the windowless child).
  * InteractiveToken + LeastPrivilege — runs admin-free and password-free.
  * schtasks command line cannot combine ONLOGON + these settings, so we import XML.
"""

from __future__ import annotations

import os
import subprocess
import getpass
from xml.sax.saxutils import escape as xml_escape

from . import common

TASK_NAME = "CodexDmxWatchdog"

# A fixed past boundary so the repeating time trigger is always active; the
# repetition, not this date, drives every self-heal relaunch.
_SELF_HEAL_START_BOUNDARY = "2020-01-01T00:00:00"

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
      <Command>{pythonw}</Command>
      <Arguments>"{launcher}"</Arguments>
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
    # A .pyw bootstrap run by pythonw.exe: GUI subsystem, so Windows allocates no
    # console. (The former cmd /c wrapper kept a visible console for the whole
    # watchdog lifetime because cmd waits on the windowless pythonw child.)
    return os.path.join(ctx.install_dir, "run-watchdog.pyw")


def render_launcher(ctx: common.InstallContext) -> str:
    """Render the only process entry point that carries watchdog configuration.

    A tiny windowless Python bootstrap: it pins the installer-selected environment
    and then runs the installed watchdog in-process as ``__main__`` so every future
    scheduled (re)launch keeps the same port, upstream, interpreter, proxy path, and
    log retention.
    """
    settings = {
        "DMX_PROXY_PORT": str(ctx.port),
        "DMX_UPSTREAM": ctx.upstream,
        "DMX_PROXY_PYTHON": ctx.python,
        "DMX_PROXY_SCRIPT": ctx.proxy_script,
        "DMX_PROXY_LOG_MAX_BYTES": str(ctx.proxy_log_max_bytes),
        "DMX_PROXY_LOG_BACKUP_COUNT": str(ctx.proxy_log_backup_count),
        "DMX_WATCHDOG_LOG_MAX_BYTES": str(ctx.watchdog_log_max_bytes),
        "DMX_WATCHDOG_LOG_BACKUP_COUNT": str(ctx.watchdog_log_backup_count),
    }
    lines = [
        "# Auto-generated windowless watchdog bootstrap. Do not edit.",
        "import os",
        "import runpy",
    ]
    for key, value in settings.items():
        lines.append(f"os.environ[{key!r}] = {value!r}")
    lines.append(f"runpy.run_path({ctx.watchdog_script!r}, run_name='__main__')")
    return "\r\n".join(lines) + "\r\n"


def render_task_xml(ctx: common.InstallContext) -> str:
    return TASK_XML_TEMPLATE.format(
        user=xml_escape(_current_user()),
        pythonw=xml_escape(common.windows_pythonw(ctx.python)),
        launcher=xml_escape(_launcher_path(ctx)),
        workdir=xml_escape(ctx.install_dir),
        start_boundary=_SELF_HEAL_START_BOUNDARY,
    )


def install(ctx: common.InstallContext) -> None:
    xml_path = _xml_path(ctx)
    launcher = _launcher_path(ctx)
    # The Task executes this launcher, so every future scheduled (re)launch retains
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


def _running_watchdog_pids(ctx: common.InstallContext) -> list[int]:
    """Return PIDs of watchdog processes launched from THIS install directory.

    Matched against the absolute generated launcher and installed watchdog script
    so an unrelated Python process is never terminated. schtasks /delete removes
    only the task definition, not an already-running instance, so uninstall must
    end the live watchdog itself or it immediately respawns the proxy.
    """
    markers = (
        os.path.abspath(_launcher_path(ctx)).lower(),
        os.path.abspath(ctx.watchdog_script).lower(),
    )
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine } | "
        "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
    )
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, check=False,
        ).stdout
    except Exception:
        return []
    pids: list[int] = []
    for line in output.splitlines():
        pid_str, _, cmdline = line.partition("\t")
        lowered = cmdline.lower()
        if any(marker in lowered for marker in markers):
            try:
                pids.append(int(pid_str.strip()))
            except ValueError:
                pass
    return pids


def uninstall(ctx: common.InstallContext) -> None:
    subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Deleting the task does not stop a running instance; end this install's
    # watchdog so it cannot respawn the proxy after the caller stops it.
    for pid in _running_watchdog_pids(ctx):
        common.terminate_pid(pid)


def status(ctx: common.InstallContext) -> str:
    r = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "list"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "absent"
    if "Running" in r.stdout:
        return "running"
    return "installed"
