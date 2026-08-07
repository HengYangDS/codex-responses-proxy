"""Apply one admitted release to a fresh or current native runtime."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Protocol

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import transaction
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.runtime import config as runtime_config

RuntimeReader = Callable[[runtime_context.RuntimeContext], dict[str, object] | None]


class ServiceAdapter(Protocol):
    """Native supervision operation required by a fresh install."""

    def install(self, ctx: runtime_context.RuntimeContext) -> None: ...


class UnknownDeploymentOutcome(errors.InstallError):
    """The handoff controller cannot prove whether the successor committed."""


def install(
    ctx: runtime_context.RuntimeContext,
    payload: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Install fresh bytes or hand off one verified current native runtime."""

    current = runtime_reader(ctx)
    if current is None and not process.listener_pids(ctx.port):
        return _fresh_install(
            ctx,
            payload,
            adapter=adapter,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    if current is None or type(current.get("pid")) is not int:
        raise errors.InstallError("installed runtime identity is not verified")
    if not handoff.runtime_supports_handoff(current):
        raise errors.InstallError(
            "installed runtime is incompatible; remove it before installing this release"
        )
    assert current is not None
    pid = current["pid"]
    if process.verified_proxy_listener_pids(ctx) != [pid]:
        raise errors.InstallError("installed runtime identity is not verified")
    return _upgrade(
        ctx,
        payload,
        current=current,
        runtime_reader=runtime_reader,
        timeout_seconds=timeout_seconds,
    )


def _fresh_install(
    ctx: runtime_context.RuntimeContext,
    payload: transaction.PayloadTransaction,
    *,
    adapter: ServiceAdapter,
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    payload.commit_projection()
    try:
        adapter.install(ctx)
        runtime = wait_for_serving_runtime(
            ctx,
            payload.expected,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    except BaseException:
        payload.rollback()
        raise
    payload.finalize(runtime)
    return {"mode": "fresh-install", "runtime": runtime}


def _upgrade(
    ctx: runtime_context.RuntimeContext,
    payload: transaction.PayloadTransaction,
    *,
    current: dict[str, object],
    runtime_reader: RuntimeReader,
    timeout_seconds: float,
) -> dict[str, object]:
    payload.commit_projection()
    try:
        runtime = request_handoff(
            ctx,
            payload.expected,
            current=current,
            runtime_reader=runtime_reader,
            timeout_seconds=timeout_seconds,
        )
    except UnknownDeploymentOutcome as exc:
        payload.preserve_for_recovery(str(exc))
        raise
    except BaseException:
        payload.rollback()
        raise
    payload.finalize(runtime)
    return {"mode": "upgrade", "runtime": runtime}


def request_handoff(
    ctx: runtime_context.RuntimeContext,
    expected: Mapping[str, object],
    *,
    current: dict[str, object],
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
            if (
                type(pid) is int
                and pid > 0
                and process.verified_proxy_listener_pids(ctx) == [pid]
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


def read_runtime(ctx: runtime_context.RuntimeContext) -> dict[str, object] | None:
    """Read the secret-free listener health snapshot over loopback."""

    request = urllib.request.Request(
        runtime_config.loopback_url(ctx.port, "/healthz"),
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read())
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return value if isinstance(value, dict) else None
