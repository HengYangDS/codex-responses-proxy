"""Select the native user-service implementation for this host."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Protocol, cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context


class NativeServiceAdapter(Protocol):
    """Complete platform supervision surface selected at the host boundary."""

    __name__: str

    def install(self, ctx: runtime_context.RuntimeContext) -> None: ...

    def uninstall(self, ctx: runtime_context.RuntimeContext) -> None: ...

    def status(self, ctx: runtime_context.RuntimeContext) -> str: ...


def adapter() -> NativeServiceAdapter:
    """Return the native supervision module for the current platform."""

    for prefix, name in (("darwin", "macos"), ("linux", "linux"), ("win", "windows")):
        if sys.platform.startswith(prefix):
            return cast(
                "NativeServiceAdapter",
                import_module(f"codex_responses_proxy.lifecycle.supervision.{name}"),
            )
    if sys.platform == "cygwin":
        return cast(
            "NativeServiceAdapter",
            import_module("codex_responses_proxy.lifecycle.supervision.windows"),
        )
    raise errors.UnsupportedPlatform(f"unsupported platform: {sys.platform}")
