"""Resolve service-safe Python executables across supported host platforms."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import TypeGuard

from codex_dmx_proxy import errors


def resolve_python() -> str:
    """Return an absolute interpreter path safe for a background service."""

    candidates = [sys.executable]
    if os.name == "nt":
        candidates.extend(_launcher_python(name) for name in ("py", "py.exe"))
        names = ("python.exe", "python3.exe", "python")
    else:
        names = ("python3", "python")
    for path in candidates:
        if _service_safe(path):
            return path
    for name in names:
        path = shutil.which(name)
        if _service_safe(path):
            return path
    raise errors.InstallError("could not resolve an absolute python interpreter path")


def _launcher_python(name: str) -> str | None:
    if not (found := shutil.which(name)):
        return None
    try:
        return subprocess.check_output(
            [found, "-3", "-c", "import sys;print(sys.executable)"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _service_safe(path: str | None) -> TypeGuard[str]:
    """Accept only an existing absolute interpreter, never a Store alias stub."""

    executable = bool(
        path
        and (
            os.path.splitext(path)[1].lower() == ".exe"
            if os.name == "nt"
            else os.access(path, os.X_OK)
        )
    )
    return bool(
        path
        and os.path.isabs(path)
        and os.path.isfile(path)
        and executable
        and not is_windows_store_stub(path)
    )


def is_windows_store_stub(path: str) -> bool:
    """Return whether ``path`` is a Microsoft Store execution-alias stub."""

    if os.name != "nt" or "windowsapps" not in path.lower():
        return False
    try:
        return os.path.getsize(path) < 1024
    except OSError:
        return True


def windows_pythonw(python_executable: str) -> str:
    """Return the matching windowless interpreter when it exists."""

    if os.name != "nt":
        return python_executable
    candidate = os.path.join(os.path.dirname(python_executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else python_executable
