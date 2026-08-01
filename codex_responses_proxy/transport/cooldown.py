"""Provider-neutral bounded cooldown for repeated upstream failures."""

from __future__ import annotations

import threading
import time

_FAILURES_LOCK = threading.Lock()
_FAILURES: dict[str, float] = {}


def _purge_expired_locked(now: float, cooldown_seconds: int) -> None:
    expired = tuple(
        key for key, recorded_at in _FAILURES.items() if recorded_at + cooldown_seconds <= now
    )
    for key in expired:
        del _FAILURES[key]


def remember_failure(
    key: str,
    *,
    capacity: int = 1024,
    cooldown_seconds: int = 30,
    now: float | None = None,
) -> None:
    """Record one failure in a bounded monotonic cooldown cache."""
    moment = time.monotonic() if now is None else now
    with _FAILURES_LOCK:
        _purge_expired_locked(moment, cooldown_seconds)
        _FAILURES[key] = moment
        oldest = sorted(_FAILURES, key=_FAILURES.__getitem__)
        for oldest_key in oldest[: -max(1, capacity)]:
            del _FAILURES[oldest_key]


def remaining(
    key: str,
    *,
    cooldown_seconds: int = 30,
    now: float | None = None,
) -> float:
    """Return remaining cooldown seconds, purging expired entries first."""
    moment = time.monotonic() if now is None else now
    with _FAILURES_LOCK:
        _purge_expired_locked(moment, cooldown_seconds)
        recorded = _FAILURES.get(key)
    return 0 if recorded is None else max(0, recorded + cooldown_seconds - moment)


def failure_count_for_test() -> int:
    """Expose only cache cardinality for bounded-state tests."""
    with _FAILURES_LOCK:
        return len(_FAILURES)


def has_failure_for_test(key: str) -> bool:
    """Report cooldown-key membership without exposing mutable state."""
    with _FAILURES_LOCK:
        return key in _FAILURES


def reset_for_test() -> None:
    """Reset cooldown state for deterministic unit tests."""
    with _FAILURES_LOCK:
        _FAILURES.clear()
