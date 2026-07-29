"""Platform boundary for released deployment and native user services.

Concrete modules own distinct concerns: ``release_source`` admits exact signed
Git objects after dual-Forge publication proof; ``payload`` owns the sealed
transaction, receipt, manifest, rollback, and recovery hold; ``deployment``
composes source-side lifecycle proof; ``control_handoff`` owns protocol-v2
transport and successor identity; and the OS modules register the watchdog.

``pick_adapter()`` selects only the native service adapter. Installed control
may observe or reload the same payload, but release admission and payload
replacement remain source-side responsibilities.
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
