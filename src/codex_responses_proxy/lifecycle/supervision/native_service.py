"""Select the native user-service implementation for this host."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Protocol, cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.service import runtime as service_runtime


class NativeServiceAdapter(Protocol):
    """Complete platform supervision surface selected at the host boundary."""

    __name__: str

    def install(self, ctx: runtime_spec.NativeServiceContext) -> None: ...

    def configured_executable(self, ctx: runtime_spec.NativeServiceContext) -> str | None: ...

    def uninstall(self, ctx: runtime_spec.NativeServiceContext) -> None: ...

    def status(self, ctx: runtime_spec.NativeServiceContext) -> str: ...


def _platform_adapters() -> tuple[tuple[str, ModuleType], ...]:
    """Load every supported adapter through imports visible to bundlers."""

    try:
        from codex_responses_proxy.lifecycle.supervision import linux, macos, windows
    except ImportError as error:
        raise errors.ProductAssemblyError(
            "product installation is incomplete; reinstall the verified release"
        ) from error
    return (("darwin", macos), ("linux", linux), ("win", windows))


def adapter() -> NativeServiceAdapter:
    """Return the statically bundled supervision module for the current platform."""

    for prefix, implementation in _platform_adapters():
        if sys.platform.startswith(prefix):
            return cast("NativeServiceAdapter", implementation)
    if sys.platform == "cygwin":
        try:
            from codex_responses_proxy.lifecycle.supervision import windows
        except ImportError as error:
            raise errors.ProductAssemblyError(
                "product installation is incomplete; reinstall the verified release"
            ) from error
        return cast("NativeServiceAdapter", windows)
    raise errors.UnsupportedPlatform(f"unsupported platform: {sys.platform}")


def install_current() -> None:
    """Install supervision from the exact committed successor executable."""

    context = runtime_spec.service_context(service_runtime.current_executable())
    implementation = adapter()
    implementation.install(context)
    if implementation.configured_executable(context) != context.executable:
        raise errors.InstallError(
            "native supervisor did not bind the committed successor executable"
        )
