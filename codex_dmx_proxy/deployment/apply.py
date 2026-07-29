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
from typing import Any, Protocol

from codex_dmx_proxy.deployment import handoff
from codex_dmx_proxy import installation
from codex_dmx_proxy import errors
from codex_dmx_proxy import process
from codex_dmx_proxy.release import projection, transaction


QUIET_SECONDS = 5.0
RuntimeReader = Callable[[installation.InstallContext], dict[str, object] | None]


class ServiceAdapter(Protocol):
    """Minimal service-registration surface required by fresh installation."""

    def install(self, ctx: installation.InstallContext) -> None:
        """Register and start the platform watchdog service."""


class UnknownDeploymentOutcome(errors.InstallError):
    """Report a committed handoff whose final live outcome cannot be proved."""


def install(
    ctx: installation.InstallContext,
    transaction: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
    allow_legacy_bootstrap: bool = False,
    force_legacy_bootstrap: bool = False,
) -> dict[str, object]:
    """Apply one admitted release through fresh, handoff, or legacy lifecycle."""

    current = runtime_reader(ctx)
    if current is None and not process.verified_proxy_listener_pids(ctx):
        return _fresh_install(
            ctx,
            transaction,
            adapter=adapter,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    if handoff.runtime_supports_handoff(current):
        assert current is not None
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
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        force=force_legacy_bootstrap,
    )


def _fresh_install(
    ctx: installation.InstallContext,
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
    ctx: installation.InstallContext,
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
    ctx: installation.InstallContext,
    transaction: transaction.PayloadTransaction,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    force: bool,
) -> dict[str, object]:
    old_pid = prove_legacy_quiet_window(
        ctx,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
        force=force,
    )
    transaction.commit_projection()
    try:
        if not process.terminate_pid(old_pid, expected_path=ctx.proxy_script):
            raise errors.InstallError("verified legacy listener did not terminate")
        runtime = wait_for_serving_runtime(
            ctx,
            transaction.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
            old_pid=old_pid,
        )
    except BaseException:
        transaction.rollback()
        raise
    transaction.finalize(runtime)
    return {"mode": "legacy-bootstrap", "runtime": runtime, "old_pid": old_pid}


def request_handoff(
    ctx: installation.InstallContext,
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
    ctx: installation.InstallContext,
    *,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
    force: bool = False,
) -> int:
    """Prove one verified legacy listener is idle, unless interruption is authorized."""

    ok, detail = projection.verify_payload_manifest(ctx)
    if not ok:
        raise errors.InstallError(f"payload integrity check failed: {detail}")
    listeners = process.verified_proxy_listener_pids(ctx)
    if len(listeners) != 1:
        raise errors.InstallError(
            f"expected exactly one verified proxy listener on {ctx.port}; found {listeners}"
        )
    old_pid = listeners[0]
    if force:
        return old_pid
    deadline = time.monotonic() + timeout_seconds
    quiet_started: float | None = None
    while time.monotonic() < deadline:
        if process.verified_proxy_listener_pids(ctx) != [old_pid]:
            raise errors.InstallError("verified legacy listener changed during quiet-window proof")
        runtime = runtime_reader(ctx)
        active = runtime.get("active_responses") if isinstance(runtime, dict) else None
        if isinstance(active, int) and not isinstance(active, bool) and active == 0:
            now = time.monotonic()
            if quiet_started is None:
                quiet_started = now
            elif now - quiet_started >= QUIET_SECONDS:
                return old_pid
        else:
            quiet_started = None
        time.sleep(0.1)
    raise errors.InstallError(
        f"legacy listener did not remain idle for {QUIET_SECONDS:g}s; payload was not changed"
    )


def wait_for_serving_runtime(
    ctx: installation.InstallContext,
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


def _runtime_matches(runtime: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    return (
        runtime.get("release") == expected.get("release")
        and runtime.get("serving_payload_sha256") == expected.get("serving_payload_sha256")
        and runtime.get("payload_manifest_sha256") == expected.get("manifest_sha256")
        and runtime.get("release_receipt_sha256") == expected.get("release_receipt_sha256")
        and runtime.get("accepting") is True
        and runtime.get("draining") is not True
    )


def read_runtime(ctx: installation.InstallContext) -> dict[str, object] | None:
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
