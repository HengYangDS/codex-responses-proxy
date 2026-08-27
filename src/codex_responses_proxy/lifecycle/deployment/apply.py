"""Apply one admitted release to a fresh or current native runtime."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from collections.abc import Mapping
from typing import Protocol

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import transaction
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import runtime as service_runtime

RuntimeReader = Callable[[runtime_context.RuntimeContext], dict[str, object] | None]
type UpgradeStrategy = handoff.DeploymentStrategy


class ServiceAdapter(Protocol):
    """Native supervision operations required by payload deployment."""

    def install(self, ctx: runtime_context.RuntimeContext) -> None:
        """Install or replace the native service for this runtime context."""
        ...

    def uninstall(self, ctx: runtime_context.RuntimeContext) -> None:
        """Remove the exact native service owned by this runtime context."""
        ...

    def terminate_runtime(
        self,
        ctx: runtime_context.RuntimeContext,
        *,
        timeout_seconds: float,
    ) -> int:
        """Terminate and prove exit of this generation's native runtime processes."""
        ...

    def configured_executable(self, ctx: runtime_context.RuntimeContext) -> str | None:
        """Return the executable configured in the native service definition."""
        ...


class UnknownDeploymentOutcome(errors.InstallError):
    """The deployment controller cannot prove whether the successor committed."""


def install(
    ctx: runtime_context.RuntimeContext,
    payload: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
    upgrade_strategy: UpgradeStrategy | None = None,
) -> dict[str, object]:
    """Install fresh bytes or hand off one verified current native runtime."""
    current = runtime_reader(ctx)
    if current is None and not process.listener_pids(ctx.port):
        return _fresh_install(
            payload,
            adapter=adapter,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    if current is None:
        raise errors.InstallError("installed runtime identity is not verified")
    pid = current.get("pid")
    if type(pid) is not int:
        raise errors.InstallError("installed runtime identity is not verified")
    observed_strategy = handoff.deployment_strategy(current)
    if observed_strategy == "unsupported":
        raise errors.InstallError(
            "installed runtime is incompatible; remove it before installing this release"
        )
    strategy = upgrade_strategy or observed_strategy
    source_listener = handoff.capture_source_listener(ctx, current)
    if not _same_executable(adapter.configured_executable(ctx), ctx.executable):
        raise errors.InstallError("native supervisor is not bound to the canonical executable")
    return _upgrade(
        ctx,
        payload,
        adapter=adapter,
        current=current,
        source_listener=source_listener,
        native_generation=strategy == "native_generation",
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
    )


def rollback(
    ctx: runtime_context.RuntimeContext,
    retained: payload_rollback.RetainedRollback,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Apply one retained predecessor through the ordinary upgrade machinery."""
    payload = transaction.begin_rollback_transaction(ctx, retained)
    result = install(
        ctx,
        payload,
        adapter=adapter,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        upgrade_strategy="native_generation",
    )
    if result.get("state") != "upgraded":
        raise errors.InstallError("rollback requires a verified running successor")
    return {
        "state": "rolled_back",
        "from_release": retained.successor.release,
        "to_release": retained.predecessor.release,
        "runtime": result["runtime"],
    }


def _fresh_install(
    payload: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    payload.commit_projection()
    candidate = payload.context
    try:
        adapter.install(candidate)
        payload.activate()
        runtime = wait_for_serving_runtime(
            candidate,
            payload.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    except BaseException:
        try:
            _remove_candidate_runtime(
                candidate,
                adapter=adapter,
                timeout_seconds=timeout_seconds,
            )
        except UnknownDeploymentOutcome as cleanup_error:
            payload.preserve_for_recovery(str(cleanup_error))
            raise
        payload.rollback()
        raise
    payload.finalize(runtime)
    return {"state": "installed", "runtime": runtime}


def _upgrade(
    ctx: runtime_context.RuntimeContext,
    payload: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    current: dict[str, object],
    source_listener: process.OwnedProcess,
    native_generation: bool,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    payload.commit_projection()
    candidate = payload.context
    supervisor_replaced = False
    admission_may_be_closed = False
    try:
        if native_generation:
            admission_may_be_closed = True
            handoff.drain_responses(
                candidate,
                source_listener=source_listener,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
            )
        _replace_supervisor(
            adapter,
            ctx,
            candidate,
            timeout_seconds=timeout_seconds,
        )
        supervisor_replaced = True
        payload.activate()
        admission_may_be_closed = True
        runtime = (
            _replace_native_generation(
                candidate,
                payload.expected,
                source_listener=source_listener,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
            )
            if native_generation
            else request_handoff(
                candidate,
                payload.expected,
                current=current,
                source_listener=source_listener,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
            )
        )
    except UnknownDeploymentOutcome as exc:
        payload.preserve_for_recovery(str(exc))
        raise
    except BaseException:
        if supervisor_replaced:
            try:
                _restore_predecessor(
                    adapter,
                    current=ctx,
                    candidate=candidate,
                    timeout_seconds=timeout_seconds,
                )
            except UnknownDeploymentOutcome as restore_error:
                payload.preserve_for_recovery(str(restore_error))
                raise
            except BaseException as restore_error:
                unknown = UnknownDeploymentOutcome(
                    "native supervisor rollback could not restore the predecessor"
                )
                payload.preserve_for_recovery(str(unknown))
                raise unknown from restore_error
        if admission_may_be_closed:
            try:
                if native_generation and not process.owned_process_alive(source_listener):
                    wait_for_serving_runtime(
                        ctx,
                        current,
                        runtime_reader=runtime_reader,
                        timeout_seconds=timeout_seconds,
                        old_pid=source_listener.pid,
                    )
                elif not handoff.resume_responses(ctx, source_listener=source_listener):
                    raise errors.InstallError(
                        "predecessor listener no longer owns Responses admission"
                    )
            except BaseException as restore_error:
                unknown = UnknownDeploymentOutcome(
                    "native supervisor rollback could not restore predecessor admission"
                )
                payload.preserve_for_recovery(str(unknown))
                raise unknown from restore_error
        payload.rollback()
        raise
    payload.finalize(runtime)
    return {"state": "upgraded", "runtime": runtime}


def _replace_supervisor(
    adapter: ServiceAdapter,
    current: runtime_context.RuntimeContext,
    candidate: runtime_context.RuntimeContext,
    *,
    timeout_seconds: float,
) -> None:
    """Replace one proved native supervisor and restore it if binding fails."""
    try:
        adapter.uninstall(current)
    except BaseException:
        try:
            _install_supervisor(adapter, current, role="predecessor")
        except BaseException as restore_error:
            raise UnknownDeploymentOutcome(
                "native supervisor removal could not restore the predecessor"
            ) from restore_error
        raise
    try:
        _install_supervisor(adapter, candidate, role="successor")
    except BaseException:
        try:
            _remove_candidate_runtime(
                candidate,
                adapter=adapter,
                timeout_seconds=timeout_seconds,
            )
            _install_supervisor(adapter, current, role="predecessor")
        except BaseException as restore_error:
            raise UnknownDeploymentOutcome(
                "native supervisor replacement could not restore the predecessor"
            ) from restore_error
        raise


def _restore_predecessor(
    adapter: ServiceAdapter,
    *,
    current: runtime_context.RuntimeContext,
    candidate: runtime_context.RuntimeContext,
    timeout_seconds: float,
) -> None:
    """Stop every candidate-owned process before restoring old supervision."""
    try:
        _remove_candidate_runtime(
            candidate,
            adapter=adapter,
            timeout_seconds=timeout_seconds,
        )
        _install_supervisor(adapter, current, role="predecessor")
    except BaseException as restore_error:
        raise UnknownDeploymentOutcome(
            "native supervisor rollback could not restore the predecessor"
        ) from restore_error


def _install_supervisor(
    adapter: ServiceAdapter,
    ctx: runtime_context.RuntimeContext,
    *,
    role: str,
) -> None:
    """Install and prove one native supervisor binding."""
    adapter.install(ctx)
    if not _same_executable(adapter.configured_executable(ctx), ctx.executable):
        raise errors.InstallError(f"native supervisor did not bind the committed {role} executable")


def _remove_candidate_runtime(
    candidate: runtime_context.RuntimeContext,
    *,
    adapter: ServiceAdapter,
    timeout_seconds: float,
) -> None:
    """Remove candidate supervision and processes before payload rollback."""
    try:
        adapter.uninstall(candidate)
        adapter.terminate_runtime(candidate, timeout_seconds=timeout_seconds)
    except BaseException as cleanup_error:
        raise UnknownDeploymentOutcome(
            "candidate runtime cleanup is unconfirmed; transaction preserved for recovery"
        ) from cleanup_error


def _replace_native_generation(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    source_listener: process.OwnedProcess,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    """Cross the exact predecessor exit barrier and prove its successor."""
    if not process.terminate_owned_process(source_listener, timeout_seconds=timeout_seconds):
        raise UnknownDeploymentOutcome("native generation replacement outcome is unconfirmed")
    return wait_for_serving_runtime(
        ctx,
        expected,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        old_pid=source_listener.pid,
    )


def request_handoff(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    current: dict[str, object],
    source_listener: process.OwnedProcess,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    """Request handoff and resolve controller failure from runtime evidence."""
    try:
        result = handoff.request(
            ctx,
            dict(expected),
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            lease_seconds=max(1.0, timeout_seconds),
            source_listener=source_listener,
        )
        runtime = result.get("runtime")
        if not isinstance(runtime, dict) or not all(isinstance(key, str) for key in runtime):
            raise errors.InstallError("handoff did not return successor runtime proof")
        return {key: value for key, value in runtime.items() if isinstance(key, str)}
    except BaseException as error:
        try:
            resolution, runtime = handoff.resolve_after_controller_failure(
                ctx,
                current,
                dict(expected),
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
                lease_seconds=max(1.0, timeout_seconds),
                source_listener=source_listener,
            )
        except (OSError, errors.InstallError):
            resolution, runtime = "unknown", None
        if (
            resolution == "finalized"
            and isinstance(runtime, dict)
            and all(isinstance(key, str) for key in runtime)
        ):
            return {key: value for key, value in runtime.items() if isinstance(key, str)}
        if resolution == "unknown":
            raise UnknownDeploymentOutcome(
                "handoff outcome is unconfirmed; transaction preserved for recovery"
            ) from error
        raise


def wait_for_serving_runtime(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    old_pid: int | None = None,
) -> dict[str, object]:
    """Wait for one accepting listener with the exact release identity."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        runtime = runtime_reader(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            runtime_process = (
                process.capture_executable(
                    pid,
                    ctx.executable,
                    roles={service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE},
                )
                if type(pid) is int
                else None
            )
            if (
                type(pid) is int
                and pid > 0
                and (
                    process.verified_proxy_listener_pids(ctx) == [pid]
                    or runtime_process is not None
                )
                and pid != old_pid
                and _runtime_matches(runtime, expected)
            ):
                return runtime
        time.sleep(0.1)
    raise errors.InstallError("released successor did not prove SERVING identity")


def _runtime_matches(runtime: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    return (
        identity.runtime_payload_matches(runtime, expected)
        and runtime.get("accepting") is True
        and runtime.get("draining") is not True
    )


def _same_executable(configured: str | None, expected: str) -> bool:
    """Compare declared executable paths using platform path semantics."""
    if configured is None:
        return False
    return os.path.normcase(os.path.abspath(configured)) == os.path.normcase(
        os.path.abspath(expected)
    )
