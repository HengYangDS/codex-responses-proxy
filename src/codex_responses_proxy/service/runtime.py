"""Private executable roles and process identity owned by the service domain."""

from __future__ import annotations

import os
import shutil
import sys

EXECUTABLE_NAME = "codex-responses-proxy.exe" if os.name == "nt" else "codex-responses-proxy"
LISTENER_MODE = "--internal-listener"
WATCHDOG_MODE = "--internal-watchdog"
HANDOFF_CHILD_MODE = "--internal-handoff-child"


def current_executable() -> str:
    """Return the running product executable without consulting a source checkout."""

    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    if command := shutil.which(EXECUTABLE_NAME):
        return os.path.abspath(command)
    return os.path.abspath(sys.argv[0])
