"""Remove the product-owned Codex Responses Proxy service and payload."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from typing import cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import command
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import projection
from codex_responses_proxy.lifecycle import state
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.lifecycle.supervision.native_service import adapter
from codex_responses_proxy.runtime import config as runtime_config


class ServiceAdapter(Protocol):
    """Native supervision operations required by uninstall."""

    def uninstall(self, ctx: runtime_context.RuntimeContext) -> None:
        """Remove the exact native service owned by this runtime context."""
        ...

    def status(self, ctx: runtime_context.RuntimeContext) -> str:
        """Return the native service state for this runtime context."""
        ...

    def terminate_runtime(
        self,
        ctx: runtime_context.RuntimeContext,
        *,
        timeout_seconds: float,
    ) -> int:
        """Terminate and prove exit of this generation's runtime processes."""
        ...


def _stop_proxy(service: ServiceAdapter, ctx: runtime_context.RuntimeContext) -> int:
    """Terminate and prove exit of every runtime process owned by this installation."""
    contexts = (*generation.owned_contexts(ctx), ctx)
    unique = {selected.executable: selected for selected in contexts}
    stopped = 0
    for selected_ctx in unique.values():
        stopped += service.terminate_runtime(selected_ctx, timeout_seconds=5.0)
    return stopped


def _remove_service(service: ServiceAdapter, ctx: runtime_context.RuntimeContext) -> None:
    """Deregister supervision and require its read-only status to prove absence."""
    service.uninstall(ctx)
    if (state := service.status(ctx)) != "absent":
        raise errors.InstallError(f"watchdog service remains {state}")


def uninstall_product(
    *, port: int = runtime_config.DEFAULT_PORT, purge: bool = False
) -> dict[str, object]:
    """Remove owned supervision and optionally purge the verified payload."""
    ctx = runtime_context.create(port=port)
    service = cast(ServiceAdapter, adapter())

    transaction_state = state.status(ctx)
    if transaction_state is not None:
        if transaction_state.get("state") == "invalid":
            raise errors.RecoveryStateError(
                "payload transaction evidence is invalid; preserve it for diagnosis"
            )
        raise errors.RecoveryRequiredError("complete payload recovery before uninstalling")
    installed = state.read_installed(ctx)
    command_path = (
        Path(state.require_command(installed)) if installed is not None else Path(ctx.command)
    )
    command_state = command.status(command_path, Path(ctx.executable))
    service_state = service.status(ctx)
    listeners = process.verified_proxy_listener_pids(ctx)
    install_root = Path(ctx.install_dir)
    if (
        installed is None
        and not install_root.exists()
        and not install_root.is_symlink()
        and service_state == "absent"
        and not listeners
        and command_state.get("state") == "absent"
    ):
        return {
            "state": "not_installed",
            "stopped": 0,
            "command_removed": False,
        }

    _remove_service(service, ctx)
    stopped = _stop_proxy(service, ctx)
    command_removed = command.remove(command_path, Path(ctx.executable))

    if purge:
        owned_generations = generation.owned_contexts(ctx)
        selection = generation.read(ctx)
        payload_contexts = owned_generations or (ctx,)
        for owned_ctx in payload_contexts:
            remaining = projection.purge_installed_projection(owned_ctx)
            if remaining:
                raise errors.InstallError(
                    "manifest-owned payload was removed, but unknown install content remains: "
                    + ", ".join(remaining)
                )
        if selection is not None:
            generation.clear(ctx)
        for owned_ctx in owned_generations:
            generation.remove(ctx, Path(owned_ctx.payload_dir).name)
        Path(state.installed_path(ctx)).unlink(missing_ok=True)
        if install_root.is_dir() and not any(install_root.iterdir()):
            install_root.rmdir()
    return {
        "state": "purged" if purge else "uninstalled",
        "stopped": stopped,
        "command_removed": command_removed,
    }
