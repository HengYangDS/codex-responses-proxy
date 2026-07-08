"""platform_adapters — per-OS service registration for the dmx watchdog.

Each adapter exposes the same three functions so the installer is platform-agnostic:

    install(ctx)    -> register + start the watchdog as a login service
    uninstall(ctx)  -> stop + deregister the service (idempotent)
    status(ctx)     -> "running" | "installed" | "absent"

``ctx`` is an InstallContext (see common.py) carrying resolved absolute paths.
``pick_adapter()`` returns the right module for the current OS.
"""

from __future__ import annotations

import sys

from . import common


def pick_adapter():
    """Return the platform adapter module for the current OS."""
    plat = sys.platform
    if plat == "darwin":
        from . import macos
        return macos
    if plat.startswith("linux"):
        from . import linux
        return linux
    if plat in ("win32", "cygwin"):
        from . import windows
        return windows
    raise common.UnsupportedPlatform(f"unsupported platform: {plat}")


__all__ = ["pick_adapter", "common"]
