"""Minimal cross-platform kernel for installation and service lifecycle.

Route state belongs to :mod:`platform_adapters.route_state`; executable payload
transactions belong to :mod:`platform_adapters.payload`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


LABEL = "com.user.codex-dmx-watchdog"  # launchd/systemd/task identifier
DEFAULT_PORT = 8791
DEFAULT_UPSTREAM = "https://www.dmxapi.cn"
DEFAULT_PROXY_LOG_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_PROXY_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_LOG_MAX_BYTES = 512 * 1024
DEFAULT_WATCHDOG_LOG_BACKUP_COUNT = 2
INSTALL_DIRNAME = os.path.join(".codex", "dmx-proxy")  # under $HOME


class UnsupportedPlatform(RuntimeError):
    """Report that no service adapter exists for the current operating system."""

    pass


class InstallError(RuntimeError):
    """Report a fail-closed installation, route, or lifecycle contract violation."""

    pass


class ManualStartRequired(RuntimeError):
    """Report that durable service persistence could not be established.

    A session-only watchdog is not an accepted installation. The deployment
    transaction rolls the payload back and the CLI exits unsuccessfully.
    """

    pass


@dataclass
class InstallContext:
    """Everything the adapters need, resolved to absolute paths at install time."""

    home: str
    install_dir: str  # ~/.codex/dmx-proxy
    proxy_script: str  # <install_dir>/proxy/dmx_responses_proxy.py
    watchdog_script: str  # <install_dir>/watchdog/watchdog.py
    python: str  # ABSOLUTE interpreter path (never bare "python3")
    codex_config: str  # ~/.codex/config.toml
    log_dir: str  # ~/.codex/log
    port: int = DEFAULT_PORT
    upstream: str = DEFAULT_UPSTREAM
    proxy_log_max_bytes: int = DEFAULT_PROXY_LOG_MAX_BYTES
    proxy_log_backup_count: int = DEFAULT_PROXY_LOG_BACKUP_COUNT
    watchdog_log_max_bytes: int = DEFAULT_WATCHDOG_LOG_MAX_BYTES
    watchdog_log_backup_count: int = DEFAULT_WATCHDOG_LOG_BACKUP_COUNT
    env: dict = field(default_factory=dict)


def home_dir() -> str:
    """Return the active user's expanded home directory."""
    return os.path.expanduser("~")


def codex_home() -> str:
    """Codex root: $CODEX_HOME or ~/.codex (same convention on all three OSes)."""
    return os.environ.get("CODEX_HOME", os.path.join(home_dir(), ".codex"))


def codex_config_path() -> str:
    """Return the Codex configuration path for the active profile root."""
    return os.path.join(codex_home(), "config.toml")


def resolve_python() -> str:
    """Return an ABSOLUTE python interpreter path safe for a service context.

    A service (launchd/systemd/Task Scheduler) runs with a minimal PATH that does
    NOT include Homebrew/pyenv/venv shims, so a bare ``python3`` will not resolve.
    We record an absolute path at install time.

    Order:
      1. sys.executable — the interpreter running the installer (most reliable).
      2. Windows: the ``py`` launcher (``py -3``) resolved to its real exe, since
         the bare ``python.exe`` on PATH is often the 0-byte WindowsApps Store stub.
      3. shutil.which fallbacks.
    """
    exe = sys.executable
    if exe and os.path.isabs(exe) and os.path.exists(exe):
        # Guard against the Windows Store stub (0-byte redirector under WindowsApps).
        if not _is_windows_store_stub(exe):
            return exe

    if os.name == "nt":
        # Ask the py launcher for the real interpreter path.
        for launcher in ("py", "py.exe"):
            found = shutil.which(launcher)
            if found:
                try:
                    out = subprocess.check_output(
                        [found, "-3", "-c", "import sys;print(sys.executable)"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    ).strip()
                    if out and os.path.exists(out) and not _is_windows_store_stub(out):
                        return out
                except Exception:
                    pass
        for name in ("python.exe", "python3.exe", "python"):
            found = shutil.which(name)
            if found and not _is_windows_store_stub(found):
                return found
    else:
        for name in ("python3", "python"):
            found = shutil.which(name)
            if found:
                return found

    if exe:
        return exe
    raise InstallError("could not resolve an absolute python interpreter path")


def _is_windows_store_stub(path: str) -> bool:
    """The Microsoft Store app-execution-alias stub is a ~0-byte file under
    ...\\WindowsApps\\ that opens the Store instead of running Python."""
    if os.name != "nt":
        return False
    if "windowsapps" in path.lower():
        try:
            return os.path.getsize(path) < 1024
        except OSError:
            return True
    return False


def windows_pythonw(python_exe: str) -> str:
    """Return the matching ``pythonw.exe`` for a resolved ``python.exe`` so the
    watchdog runs without a console window flashing at logon. Falls back to the
    console exe if the windowless variant is absent."""
    if os.name != "nt":
        return python_exe
    cand = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    return cand if os.path.exists(cand) else python_exe


def validate_port(port: int) -> int:
    """Accept only a real TCP port before it reaches service definitions."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise InstallError("port must be an integer in 1..65535")
    return port


def validate_log_retention(value: int, *, name: str, minimum: int, maximum: int) -> int:
    """Accept one bounded runtime-log retention setting for service rendering."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InstallError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def listener_pids(port: int) -> list[int]:
    """Return PIDs listening on ``port``; identity verification is separate."""
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            pids = []
            for line in output.splitlines():
                fields = line.split()
                if (
                    len(fields) >= 5
                    and fields[1].endswith(f":{port}")
                    and fields[3].upper() == "LISTENING"
                ):
                    try:
                        pids.append(int(fields[-1]))
                    except ValueError:
                        pass
            return pids
        output = subprocess.run(
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return [int(value) for value in output.split() if value.isdigit()]
    except Exception:
        return []


def process_command(pid: int) -> str:
    """Return a process command line for identity proof, or an empty string."""
    try:
        if os.name == "nt":
            command = (
                '$p=Get-CimInstance Win32_Process -Filter "ProcessId=' + str(pid) + '";'
                "if ($p) {$p.CommandLine}"
            )
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except Exception:
        return ""


def verified_proxy_listener_pids(ctx: InstallContext) -> list[int]:
    """Return only listeners whose command line names this installed proxy script."""
    expected = os.path.abspath(ctx.proxy_script)
    return [
        pid for pid in listener_pids(ctx.port) if expected in os.path.abspath(process_command(pid))
    ]


def terminate_pid(pid: int) -> None:
    """Request termination of one already-verified listener PID."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/pid", str(pid), "/f"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["kill", "-TERM", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
