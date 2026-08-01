"""Source-side orchestration for one released payload transaction.

Only the released checkout imports this module to compose payload mutation with
service lifecycle proof.  Installed ``control.py`` is deliberately excluded:
it may observe or reload the already-installed payload, but it cannot admit or
install a different release.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace
from typing import Any, Protocol

from codex_responses_proxy.deployment import handoff
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy import errors
from codex_responses_proxy.supervision import process
from codex_responses_proxy.payload import projection, transaction


QUIET_SECONDS = 5.0
RuntimeReader = Callable[[runtime_context.RuntimeContext], dict[str, object] | None]


class ServiceAdapter(Protocol):
    """Native supervision surface required by installation and migration."""

    def install(self, ctx: runtime_context.RuntimeContext) -> None:
        """Register or replace and start the platform watchdog service."""


class UnknownDeploymentOutcome(errors.InstallError):
    """Report a committed handoff whose final live outcome cannot be proved."""


@dataclass(frozen=True)
class LegacyListener:
    """Historical projection and the exact listener process serving it."""

    projection: projection.HistoricalProjection
    process: process.OwnedProcess


def install(
    ctx: runtime_context.RuntimeContext,
    transaction: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
    force_v2_bootstrap: bool = False,
) -> dict[str, object]:
    """Apply one admitted release through fresh, handoff, or legacy lifecycle."""

    current = runtime_reader(ctx)
    if current is None and not process.listener_pids(ctx.port):
        return _fresh_install(
            ctx,
            transaction,
            adapter=adapter,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    if handoff.runtime_supports_handoff(current):
        assert current is not None
        if force_v2_bootstrap:
            return _v2_bootstrap(
                ctx,
                transaction,
                current=current,
                adapter=adapter,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
            )
        return _protocol_v2_upgrade(
            ctx,
            transaction,
            current=current,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    if not allow_legacy_bootstrap:
        raise errors.InstallError(
            "installed listener requires an explicitly authorized legacy bootstrap"
        )
    return _legacy_upgrade(
        ctx,
        transaction,
        adapter=adapter,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        force=force_legacy_bootstrap,
    )


def _v2_bootstrap(
    ctx: runtime_context.RuntimeContext,
    transaction: transaction.PayloadTransaction,
    *,
    current: dict[str, object],
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    """Replace one verified v2 listener whose upgrade protocol cannot advance."""

    old = prove_v2_listener(ctx, current)
    transaction.commit_projection()
    terminated = False
    try:
        if not process.terminate_pid(old.pid, expected_path=old.script):
            raise errors.InstallError("verified protocol-v2 listener did not terminate")
        terminated = True
        adapter.install(ctx)
        runtime = wait_for_serving_runtime(
            ctx,
            transaction.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            old_pid=old.pid,
        )
    except BaseException as exc:
        try:
            transaction.rollback()
            if terminated:
                adapter.install(ctx)
                wait_for_legacy_runtime(
                    ctx,
                    release=str(current["release"]),
                    runtime_reader=runtime_reader,
                    timeout_seconds=timeout_seconds,
                )
        except BaseException as rollback_exc:
            raise errors.InstallError(
                f"protocol-v2 bootstrap failed and runtime rollback failed: {rollback_exc}"
            ) from exc
        raise
    transaction.finalize(runtime)
    return {"mode": "protocol-v2-bootstrap", "runtime": runtime, "old_pid": old.pid}


def prove_v2_listener(
    ctx: runtime_context.RuntimeContext,
    runtime: dict[str, object],
) -> process.OwnedProcess:
    """Bind one idle accepting v2 runtime to its exact installed entrypoint."""

    listeners = process.verified_proxy_listener_pids(ctx)
    pid = runtime.get("pid")
    if type(pid) is not int or listeners != [pid]:
        raise errors.InstallError("protocol-v2 bootstrap requires one verified listener")
    if runtime.get("accepting") is not True or runtime.get("handoff_state") != "idle":
        raise errors.InstallError("protocol-v2 bootstrap requires one idle accepting listener")
    return process.OwnedProcess(pid, ctx.proxy_script)


def _fresh_install(
    ctx: runtime_context.RuntimeContext,
    transaction: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    transaction.commit_projection()
    try:
        adapter.install(ctx)
        runtime = wait_for_serving_runtime(
            ctx,
            transaction.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    except BaseException:
        transaction.rollback()
        raise
    transaction.finalize(runtime)
    return {"mode": "fresh-install", "runtime": runtime}


def _protocol_v2_upgrade(
    ctx: runtime_context.RuntimeContext,
    transaction: transaction.PayloadTransaction,
    *,
    current: dict[str, object],
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    transaction.commit_projection()
    try:
        runtime = request_handoff(
            ctx,
            transaction.expected,
            current=current,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    except UnknownDeploymentOutcome as exc:
        transaction.preserve_for_recovery(str(exc))
        raise
    except BaseException:
        transaction.rollback()
        raise
    transaction.finalize(runtime)
    return {"mode": "protocol-v2-upgrade", "runtime": runtime}


def _legacy_upgrade(
    ctx: runtime_context.RuntimeContext,
    transaction: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    force: bool,
) -> dict[str, object]:
    old_listener = prove_legacy_quiet_window(
        ctx,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        force=force,
    )
    transaction.commit_projection()
    old_terminated = False
    try:
        if not process.terminate_pid(
            old_listener.process.pid, expected_path=old_listener.process.script
        ):
            raise errors.InstallError("verified legacy listener did not terminate")
        old_terminated = True
        adapter.install(ctx)
        runtime = wait_for_serving_runtime(
            ctx,
            transaction.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            old_pid=old_listener.process.pid,
        )
    except BaseException as exc:
        try:
            transaction.rollback()
            if old_terminated:
                legacy_ctx = replace(ctx, proxy_script=old_listener.projection.entrypoint)
                adapter.install(legacy_ctx)
                wait_for_legacy_runtime(
                    legacy_ctx,
                    release=old_listener.projection.release,
                    runtime_reader=runtime_reader,
                    timeout_seconds=timeout_seconds,
                )
        except BaseException as rollback_exc:
            raise errors.InstallError(
                f"legacy bootstrap failed and runtime rollback failed: {rollback_exc}"
            ) from exc
        raise
    transaction.finalize(runtime)
    return {
        "mode": "legacy-bootstrap",
        "runtime": runtime,
        "old_pid": old_listener.process.pid,
    }


def request_handoff(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    current: dict[str, object],
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    """Request the installed listener's public handoff endpoint from source side."""

    try:
        result = handoff.request(
            ctx,
            dict(expected),
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            lease_seconds=max(1.0, timeout_seconds),
        )
        runtime = result.get("runtime")
        if not isinstance(runtime, dict):
            raise errors.InstallError("handoff did not return successor runtime proof")
        return runtime
    except BaseException as error:
        try:
            resolution, runtime = handoff.resolve_after_controller_failure(
                ctx,
                current,
                dict(expected),
                runtime_reader=runtime_reader,
                timeout_seconds=timeout_seconds,
                lease_seconds=max(1.0, timeout_seconds),
            )
        except BaseException:
            resolution, runtime = "unknown", None
        if resolution == "finalized" and isinstance(runtime, dict):
            return runtime
        if resolution == "unknown":
            raise UnknownDeploymentOutcome(
                "handoff outcome is unconfirmed; transaction preserved for recovery"
            ) from error
        raise


def prove_legacy_quiet_window(
    ctx: runtime_context.RuntimeContext,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    force: bool = False,
) -> LegacyListener:
    """Bind verified historical bytes to one listener and prove it is idle."""

    try:
        historical = projection.verify_historical_projection(ctx)
    except errors.InstallError as exc:
        raise errors.InstallError(f"payload integrity check failed: {exc}") from exc
    legacy_script = historical.entrypoint
    listeners = process.verified_listener_pids(ctx.port, legacy_script)
    if len(listeners) != 1:
        raise errors.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    listener = LegacyListener(historical, process.OwnedProcess(listeners[0], legacy_script))
    if force:
        return listener
    deadline = time.monotonic() + timeout_seconds
    quiet_started: float | None = None
    while time.monotonic() < deadline:
        if process.verified_listener_pids(ctx.port, legacy_script) != [listener.process.pid]:
            raise errors.InstallError("verified legacy listener changed during quiet-window proof")
        runtime = runtime_reader(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        if isinstance(active, int) and not isinstance(active, bool) and active == 0:
            now = time.monotonic()
            if quiet_started is None:
                quiet_started = now
            elif now - quiet_started >= QUIET_SECONDS:
                return listener
        else:
            quiet_started = None
        time.sleep(0.1)
    raise errors.InstallError(
        f"legacy listener did not remain idle for {QUIET_SECONDS:g}s; payload was not changed"
    )


def wait_for_serving_runtime(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    old_pid: int | None = None,
) -> dict[str, object]:
    """Wait for exactly one accepting successor matching released aggregate identity."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        listeners = process.verified_proxy_listener_pids(ctx)
        runtime = runtime_reader(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            if (
                isinstance(pid, int)
                and not isinstance(pid, bool)
                and pid > 0
                and listeners == [pid]
                and pid != old_pid
                and _runtime_matches(runtime, expected)
            ):
                return runtime
        time.sleep(0.1)
    raise errors.InstallError("released successor did not prove SERVING identity")


def wait_for_legacy_runtime(
    ctx: runtime_context.RuntimeContext,
    *,
    release: str,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    """Prove rollback restored one accepting historical listener."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        listeners = process.verified_listener_pids(ctx.port, ctx.proxy_script)
        runtime = runtime_reader(ctx)
        if isinstance(runtime, dict):
            pid = runtime.get("pid")
            if (
                isinstance(pid, int)
                and not isinstance(pid, bool)
                and pid > 0
                and listeners == [pid]
                and runtime.get("release") == release
                and runtime.get("accepting") is True
            ):
                return runtime
        time.sleep(0.1)
    raise errors.InstallError("historical listener rollback did not prove SERVING identity")


def _runtime_matches(runtime: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    return (
        runtime.get("release") == expected.get("release")
        and runtime.get("serving_payload_sha256") == expected.get("serving_payload_sha256")
        and runtime.get("payload_manifest_sha256") == expected.get("manifest_sha256")
        and runtime.get("release_receipt_sha256") == expected.get("release_receipt_sha256")
        and runtime.get("accepting") is True
        and runtime.get("draining") is not True
    )


def read_runtime(ctx: runtime_context.RuntimeContext) -> dict[str, object] | None:
    """Read the secret-free installed listener health snapshot over loopback."""

    request = urllib.request.Request(
        f"http://127.0.0.1:{ctx.port}/healthz",
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                return None
            import json

            value: Any = json.loads(response.read())
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return value if isinstance(value, dict) else None
