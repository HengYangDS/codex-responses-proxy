"""Remove the product-owned Codex Responses Proxy service and payload."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import command, projection, state
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.lifecycle.supervision.native_service import adapter
from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.service import runtime as service_runtime


class ServiceAdapter(Protocol):
    """Native supervision operations required by uninstall."""

    def uninstall(self, ctx: runtime_context.RuntimeContext) -> None: ...

    def status(self, ctx: runtime_context.RuntimeContext) -> str: ...


def _stop_proxy(ctx: runtime_context.RuntimeContext) -> int:
    """Terminate and prove exit of each listener owned by this installation."""

    pids = process.verified_proxy_listener_pids(ctx)
    for pid in pids:
        if not process.terminate_executable(
            pid,
            ctx.executable,
            roles={service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE},
        ):
            raise errors.InstallError(f"verified proxy listener {pid} did not exit")
    if remaining := process.verified_proxy_listener_pids(ctx):
        raise errors.InstallError(f"verified proxy listeners remain: {remaining}")
    return len(pids)


def _remove_service(service: ServiceAdapter, ctx: runtime_context.RuntimeContext) -> None:
    """Deregister supervision and require its read-only status to prove absence."""

    service.uninstall(ctx)
    if (state := service.status(ctx)) != "absent":
        raise errors.InstallError(f"watchdog service remains {state}")


def uninstall_product(
    *, port: int = runtime_config.DEFAULT_PORT, purge: bool = False
) -> dict[str, object]:
    """Remove owned supervision and optionally purge the verified payload."""

    try:
        ctx = runtime_context.create(port=port)
        service = cast(ServiceAdapter, adapter())
    except (errors.InstallError, errors.UnsupportedPlatform) as exc:
        raise errors.InstallError(str(exc)) from exc

    _remove_service(service, ctx)
    stopped = _stop_proxy(ctx)
    installed = state.read_installed(ctx)
    command_path = (
        Path(state.require_command(installed)) if installed is not None else Path(ctx.command)
    )
    command_removed = command.remove(command_path, Path(ctx.executable))

    if purge:
        remaining = projection.purge_installed_projection(ctx)
        if remaining:
            raise errors.InstallError(
                "manifest-owned payload was removed, but unknown install content remains: "
                + ", ".join(remaining)
            )
    return {"stopped": stopped, "command_removed": command_removed, "purged": purge}
