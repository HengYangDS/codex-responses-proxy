"""Verify and transactionally install one signed native release asset."""

from __future__ import annotations

from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import runtime_spec
from codex_responses_proxy.lifecycle import state
from codex_responses_proxy.lifecycle import transaction
from codex_responses_proxy.lifecycle.deployment import apply


def install_asset(
    ctx: runtime_context.RuntimeContext,
    asset: Path,
    *,
    trust_anchor: Path,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Install one verified native asset through the platform service adapter."""
    from codex_responses_proxy.lifecycle.supervision import native_service

    try:
        released = artifact.admit(asset, trust_anchor=trust_anchor)
    except errors.InstallError as exc:
        raise errors.InstallInputError(str(exc)) from exc
    previous = state.read_installed(ctx)
    if previous is not None and previous.get("version") == released.version:
        if state.status(ctx) is not None:
            raise errors.RecoveryRequiredError("complete payload recovery before installing")
        observed = control.status(ctx, include_rollback=False)
        runtime = observed.get("runtime")
        control_ctx = generation.control_context(ctx)
        configured = native_service.adapter().configured_executable(control_ctx)
        if (
            observed.get("state") == "running"
            and isinstance(runtime, dict)
            and runtime.get("release_receipt_sha256") == released.receipt_sha256
            and runtime.get("serving_payload_sha256") == released.serving_payload_sha256
            and configured is not None
            and runtime_spec.normalized_path(configured)
            == runtime_spec.normalized_path(control_ctx.executable)
        ):
            return {"state": "unchanged", "release": released.version}
        raise errors.InstallError("requested artifact is not the verified active installation")
    payload_transaction = transaction.begin_transaction(ctx, released)
    try:
        return apply.install(
            ctx,
            payload_transaction,
            adapter=native_service.adapter(),
            runtime_reader=control.read_runtime,
            timeout_seconds=timeout_seconds,
        )
    except BaseException:
        payload_transaction.rollback_if_prepared()
        raise
