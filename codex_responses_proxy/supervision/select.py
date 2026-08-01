"""Select the native user-service implementation for this host."""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

from codex_responses_proxy import errors


def adapter() -> ModuleType:
    """Return the native supervision module for the current platform."""

    for prefix, name in (("darwin", "macos"), ("linux", "linux"), ("win", "windows")):
        if sys.platform.startswith(prefix):
            return import_module(f"codex_responses_proxy.supervision.{name}")
    if sys.platform == "cygwin":
        return import_module("codex_responses_proxy.supervision.windows")
    raise errors.UnsupportedPlatform(f"unsupported platform: {sys.platform}")
