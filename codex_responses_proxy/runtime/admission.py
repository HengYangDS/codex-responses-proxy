"""Process-local handler, request-admission, and bounded drain state."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections.abc import Buffer
from contextlib import suppress
from typing import SupportsIndex, SupportsInt

from codex_responses_proxy.runtime import config as runtime_config
from codex_responses_proxy.runtime import telemetry

SETTINGS = runtime_config.load()
RESPONSES_MAX_CONCURRENCY = SETTINGS.responses_max_concurrency
RESPONSES_QUEUE_TIMEOUT = SETTINGS.responses_queue_timeout
RESPONSES_MAX_PER_ROUTE = SETTINGS.responses_max_per_route
_MIN_DRAIN_LEASE_SECONDS = 1
_MAX_DRAIN_LEASE_SECONDS = 900
_RESPONSE_SEMAPHORE = threading.BoundedSemaphore(RESPONSES_MAX_CONCURRENCY)
_ROUTE_SEMAPHORES: dict[str, threading.BoundedSemaphore] = {}
_RESPONSE_GATE_LOCK = threading.Lock()
_ACTIVE_RESPONSES = 0
_ACTIVE_HANDLERS = 0
_DRAINING = False
_DRAIN_GENERATION = 0
_DRAIN_DEADLINE: float | None = None
_REQUEST_SEQUENCE = 0


def next_request_id() -> int:
    """Allocate one process-local request sequence number."""
    global _REQUEST_SEQUENCE
    with _RESPONSE_GATE_LOCK:
        _REQUEST_SEQUENCE += 1
        return _REQUEST_SEQUENCE


def bounded_drain_lease_seconds(value: object | None) -> int:
    """Return a bounded lease without making control startup fragile."""
    if isinstance(value, (str, Buffer, SupportsInt, SupportsIndex)):
        with suppress(TypeError, ValueError):
            return min(_MAX_DRAIN_LEASE_SECONDS, max(_MIN_DRAIN_LEASE_SECONDS, int(value)))
    return 30


def _expire_drain_locked() -> None:
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    deadline = _DRAIN_DEADLINE or float("inf")
    if time.monotonic() >= deadline:
        _DRAINING = False
        _DRAIN_DEADLINE = None
        _DRAIN_GENERATION += 1
        telemetry.record_counter("drain_leases_expired")
        telemetry.record_failure("drain_lease_expired")


def _drain_lease_remaining_locked() -> int | None:
    if not _DRAINING or _DRAIN_DEADLINE is None:
        return None
    return max(0, int(_DRAIN_DEADLINE - time.monotonic() + 0.999))


def set_draining(enabled: bool, *, lease_seconds: object | None = None) -> dict[str, object]:
    """Atomically change local Responses admission and return its snapshot."""
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        previous = _DRAINING
        _DRAINING = bool(enabled)
        _DRAIN_GENERATION += previous != _DRAINING
        _DRAIN_DEADLINE = (
            time.monotonic() + bounded_drain_lease_seconds(lease_seconds) if enabled else None
        )
        return {
            "draining": _DRAINING,
            "drain_generation": _DRAIN_GENERATION,
            "active_responses": _ACTIVE_RESPONSES,
            "drain_lease_remaining_seconds": _drain_lease_remaining_locked(),
        }


def snapshot() -> dict[str, object]:
    """Return one admission-consistent runtime status projection."""
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        return {
            "active_responses": _ACTIVE_RESPONSES,
            "draining": _DRAINING,
            "drain_generation": _DRAIN_GENERATION,
            "drain_lease_remaining_seconds": _drain_lease_remaining_locked(),
        }


def drain_snapshot() -> tuple[bool, int, int]:
    """Return one admission-consistent drain and active-request snapshot."""
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        return _DRAINING, _DRAIN_GENERATION, _ACTIVE_RESPONSES


def response_gate_lock() -> threading.Lock:
    """Return the lock shared with handoff identity sampling."""
    return _RESPONSE_GATE_LOCK


def is_draining() -> bool:
    """Return the current drain latch while the caller holds the gate lock."""
    return _DRAINING


def active_responses() -> int:
    """Return the current active Responses count under the caller's gate lock."""
    return _ACTIVE_RESPONSES


def active_handlers() -> int:
    """Return the current HTTP handler count under the caller's gate lock."""
    return _ACTIVE_HANDLERS


def begin_handler() -> int:
    """Account for one HTTP handler and return the current total."""
    global _ACTIVE_HANDLERS
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_HANDLERS += 1
        return _ACTIVE_HANDLERS


def end_handler() -> int:
    """Release one HTTP handler count and return the current total."""
    global _ACTIVE_HANDLERS
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_HANDLERS = max(0, _ACTIVE_HANDLERS - 1)
        return _ACTIVE_HANDLERS


def _route_semaphore(route: str) -> threading.BoundedSemaphore:
    """Return the process-local single-flight gate for one provider route."""
    with _RESPONSE_GATE_LOCK:
        return _ROUTE_SEMAPHORES.setdefault(
            route, threading.BoundedSemaphore(RESPONSES_MAX_PER_ROUTE)
        )


def _remaining_timeout(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def admit_response(route: str, *, timeout: float | None = None) -> tuple[str, int]:
    """Acquire route and global capacity, or return a bounded verdict."""
    global _ACTIVE_RESPONSES
    wait = RESPONSES_QUEUE_TIMEOUT if timeout is None else timeout
    deadline = time.monotonic() + wait
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if _DRAINING:
            return "draining", _ACTIVE_RESPONSES
    route_semaphore = _route_semaphore(route)
    if not route_semaphore.acquire(timeout=_remaining_timeout(deadline)):
        return "timeout", active_responses()
    if not _RESPONSE_SEMAPHORE.acquire(timeout=_remaining_timeout(deadline)):
        route_semaphore.release()
        return "timeout", active_responses()
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if _DRAINING:
            _RESPONSE_SEMAPHORE.release()
            route_semaphore.release()
            return "draining", _ACTIVE_RESPONSES
        _ACTIVE_RESPONSES += 1
        return "acquired", _ACTIVE_RESPONSES


def release_response_slot(route: str) -> int:
    """Release global and provider-route capacity for one active response."""
    global _ACTIVE_RESPONSES
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_RESPONSES = max(0, _ACTIVE_RESPONSES - 1)
        active = _ACTIVE_RESPONSES
        route_semaphore = _ROUTE_SEMAPHORES[route]
    _RESPONSE_SEMAPHORE.release()
    route_semaphore.release()
    return active


def is_loopback_client(address: str) -> bool:
    """Require lifecycle control surfaces to remain local."""
    with suppress(ValueError):
        return ipaddress.ip_address(address).is_loopback
    return False


def reset_for_test() -> None:
    """Reset admission state for deterministic unit tests."""
    global _ACTIVE_RESPONSES, _ACTIVE_HANDLERS, _DRAINING
    global _DRAIN_GENERATION, _DRAIN_DEADLINE, _REQUEST_SEQUENCE, _RESPONSE_SEMAPHORE
    global _ROUTE_SEMAPHORES
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_RESPONSES = 0
        _ACTIVE_HANDLERS = 0
        _DRAINING = False
        _DRAIN_GENERATION = 0
        _DRAIN_DEADLINE = None
        _REQUEST_SEQUENCE = 0
        _RESPONSE_SEMAPHORE = threading.BoundedSemaphore(RESPONSES_MAX_CONCURRENCY)
        _ROUTE_SEMAPHORES = {}
