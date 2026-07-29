"""Process-local logging, metrics, admission, drain, and cooldown state.

The proxy entrypoint owns HTTP and upstream behavior. This module owns only
mutable state that is intentionally discarded when a replacement process
starts. It never persists request or response content.
"""

from __future__ import annotations

import ipaddress
import os
import re
import stat
import sys
import threading
import time
import urllib.parse
from collections.abc import Buffer
from pathlib import Path
from typing import Mapping, SupportsInt, SupportsIndex


def bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read one bounded integer setting without making startup fragile."""
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, value))


LOG_PATH = os.environ.get(
    "DMX_PROXY_LOG",
    os.path.expanduser("~/.codex/log/dmx-responses-proxy.log"),
)
LOG_MAX_BYTES = bounded_env_int(
    "DMX_PROXY_LOG_MAX_BYTES",
    4 * 1024 * 1024,
    4 * 1024,
    64 * 1024 * 1024,
)
LOG_BACKUP_COUNT = bounded_env_int("DMX_PROXY_LOG_BACKUP_COUNT", 3, 0, 10)
LOG_LINE_MAX_BYTES = 1024
_LOG_LOCK = threading.Lock()
_LOG_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:authorization|api[_-]?key|bearer)\s*[:=]?\s*"
        r"(?:bearer\s+)?[^\s,;]+"
    ),
    re.compile(r"\bgAAAA[A-Za-z0-9_-]+"),
)

RESPONSES_MAX_CONCURRENCY = max(
    1,
    int(os.environ.get("DMX_RESPONSES_MAX_CONCURRENCY", "64")),
)
RESPONSES_QUEUE_TIMEOUT = float(os.environ.get("DMX_RESPONSES_QUEUE_TIMEOUT", "120"))
_MIN_DRAIN_LEASE_SECONDS = 1
_MAX_DRAIN_LEASE_SECONDS = 900
_RESPONSE_SEMAPHORE = threading.BoundedSemaphore(RESPONSES_MAX_CONCURRENCY)
_RESPONSE_GATE_LOCK = threading.Lock()
_ACTIVE_RESPONSES = 0
_ACTIVE_HANDLERS = 0
_DRAINING = False
_DRAIN_GENERATION = 0
_DRAIN_DEADLINE: float | None = None
_REQUEST_SEQUENCE = 0

_STARTED_AT = time.time()
_METRICS_LOCK = threading.Lock()
_COUNTERS = {
    "responses_received": 0,
    "responses_completed": 0,
    "responses_rejected_while_draining": 0,
    "drain_leases_expired": 0,
    "responses_local_queue_timeouts": 0,
    "streams_completed": 0,
    "streams_incomplete": 0,
    "streams_failed": 0,
    "streams_pre_content_reconnect_attempts": 0,
    "streams_pre_content_exhausted": 0,
    "response_failed_compaction_attempts": 0,
    "response_failed_compaction_accepted": 0,
    "response_failed_dialogue_recovery_attempts": 0,
    "response_failed_dialogue_recovery_accepted": 0,
    "response_failed_recovery_exhausted": 0,
    "input_variant_dialogue_recovery_attempts": 0,
    "input_variant_dialogue_recovery_accepted": 0,
    "input_variant_dialogue_recovery_exhausted": 0,
    "encrypted_replayed_reasoning_items_stripped": 0,
    "encrypted_malformed_blocks_stripped": 0,
    "encrypted_sse_keys_stripped": 0,
    "unreplayable_images_stripped": 0,
    "empty_response_fallback_attempts": 0,
    "empty_response_fallback_accepted": 0,
    "empty_response_fallback_rejected": 0,
    "empty_response_recovery_exhausted": 0,
    "empty_response_cooldown_hits": 0,
}
_UPSTREAM_CLASSIFICATIONS: dict[str, int] = {}
_LAST_FAILURE: dict[str, object] | None = None

_EMPTY_RESPONSE_FAILURES_LOCK = threading.Lock()
_EMPTY_RESPONSE_FAILURES: dict[str, float] = {}


def safe_request_path(value: str) -> str:
    """Return a bounded request path without query values or caller text."""
    try:
        path = urllib.parse.urlsplit(value).path
    except (TypeError, ValueError):
        return "/invalid-path"
    if not isinstance(path, str) or not path.startswith("/"):
        return "/invalid-path"
    normalized = re.sub(r"[^A-Za-z0-9._~/-]", "_", path)
    return normalized[:192] or "/"


def safe_exception_label(exc: BaseException | None) -> str:
    """Expose only the stable exception class, never an exception message."""
    return exc.__class__.__name__ if exc is not None else "UnknownError"


def _redact_log_message(message: str) -> str:
    value = str(message).replace("\r", " ").replace("\n", " ")
    for pattern in _LOG_SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    encoded = value.encode("utf-8", "replace")
    if len(encoded) > LOG_LINE_MAX_BYTES:
        value = encoded[:LOG_LINE_MAX_BYTES].decode("utf-8", "ignore") + " [truncated]"
    return value


def _rotate_log_if_needed(path: Path, incoming_bytes: int) -> int:
    """Enforce bounded local retention and return discarded legacy bytes."""
    try:
        metadata = path.lstat()
    except OSError:
        return 0
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("proxy log path is not a regular file")
    current_size = metadata.st_size
    if current_size + incoming_bytes <= LOG_MAX_BYTES:
        return 0

    discarded = 0
    if current_size > LOG_MAX_BYTES:
        path.unlink(missing_ok=True)
        discarded += current_size
    elif LOG_BACKUP_COUNT <= 0:
        path.unlink(missing_ok=True)
    else:
        path.with_name(f"{path.name}.{LOG_BACKUP_COUNT}").unlink(missing_ok=True)
        for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                if source.stat().st_size > LOG_MAX_BYTES:
                    discarded += source.stat().st_size
                    source.unlink(missing_ok=True)
                else:
                    source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))

    for index in range(1, LOG_BACKUP_COUNT + 1):
        segment = path.with_name(f"{path.name}.{index}")
        try:
            if segment.stat().st_size > LOG_MAX_BYTES:
                discarded += segment.stat().st_size
                segment.unlink()
        except OSError:
            continue
    return discarded


def log(message: str) -> None:
    """Write one bounded secret-safe operational line to disk and stderr."""
    safe_message = _redact_log_message(message)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {safe_message}\n"
    try:
        path = Path(LOG_PATH)
        with _LOG_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            discarded = _rotate_log_if_needed(path, len(line.encode("utf-8", "replace")))
            if discarded:
                line = (
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"log_retention_discarded_oversized_bytes={discarded} {safe_message}\n"
                )
            with path.open("a", encoding="utf-8") as handle:
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
                handle.write(line)
    except OSError:
        pass
    try:
        sys.stderr.write(line)
    except Exception:
        pass


def next_request_id() -> int:
    """Allocate one process-local request sequence number."""
    global _REQUEST_SEQUENCE
    with _RESPONSE_GATE_LOCK:
        _REQUEST_SEQUENCE += 1
        return _REQUEST_SEQUENCE


def record_counter(name: str, amount: int = 1) -> None:
    """Record one secret-free runtime counter."""
    if amount <= 0:
        return
    with _METRICS_LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + amount


def record_upstream_classification(name: str) -> None:
    """Record a bounded outcome class, never an upstream payload."""
    with _METRICS_LOCK:
        _UPSTREAM_CLASSIFICATIONS[name] = _UPSTREAM_CLASSIFICATIONS.get(name, 0) + 1


def record_failure(classification: str) -> None:
    """Retain only the latest failure class and time, never request data."""
    global _LAST_FAILURE
    with _METRICS_LOCK:
        _LAST_FAILURE = {"classification": classification, "at_unix": int(time.time())}


def status(
    *,
    release: str,
    serving_payload_sha256: str | None,
    release_receipt_sha256: str | None,
    runtime_identity: Mapping[str, object],
) -> dict[str, object]:
    """Return the secret-free state snapshot plus injected process identity."""
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        active_responses = _ACTIVE_RESPONSES
        draining = _DRAINING
        drain_generation = _DRAIN_GENERATION
        drain_lease_remaining_seconds = _drain_lease_remaining_locked()
    with _METRICS_LOCK:
        counters = dict(sorted(_COUNTERS.items()))
        upstream = dict(sorted(_UPSTREAM_CLASSIFICATIONS.items()))
        last_failure = dict(_LAST_FAILURE) if _LAST_FAILURE else None
    snapshot: dict[str, object] = {
        "release": release,
        "serving_payload_sha256": serving_payload_sha256,
        "release_receipt_sha256": release_receipt_sha256,
        "uptime_seconds": max(0, int(time.time() - _STARTED_AT)),
        "active_responses": active_responses,
        "draining": draining,
        "drain_generation": drain_generation,
        "drain_lease_remaining_seconds": drain_lease_remaining_seconds,
        "counters": counters,
        "upstream_classifications": upstream,
        "last_failure": last_failure,
    }
    snapshot.update(runtime_identity)
    return snapshot


def reset_for_test() -> None:
    """Reset process-local state for deterministic unit tests."""
    global _ACTIVE_RESPONSES, _ACTIVE_HANDLERS, _DRAINING
    global _DRAIN_GENERATION, _DRAIN_DEADLINE, _LAST_FAILURE, _REQUEST_SEQUENCE
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_RESPONSES = 0
        _ACTIVE_HANDLERS = 0
        _DRAINING = False
        _DRAIN_GENERATION = 0
        _DRAIN_DEADLINE = None
        _REQUEST_SEQUENCE = 0
    with _METRICS_LOCK:
        for name in _COUNTERS:
            _COUNTERS[name] = 0
        _UPSTREAM_CLASSIFICATIONS.clear()
        _LAST_FAILURE = None
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _EMPTY_RESPONSE_FAILURES.clear()


def bounded_drain_lease_seconds(value: object | None) -> int:
    """Return a bounded lease without making control startup fragile."""
    try:
        if isinstance(value, (str, Buffer, SupportsInt, SupportsIndex)):
            seconds = int(value)
        else:
            return 30
    except (TypeError, ValueError):
        return 30
    return min(_MAX_DRAIN_LEASE_SECONDS, max(_MIN_DRAIN_LEASE_SECONDS, seconds))


def _expire_drain_locked() -> None:
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    if _DRAINING and _DRAIN_DEADLINE is not None and time.monotonic() >= _DRAIN_DEADLINE:
        _DRAINING = False
        _DRAIN_DEADLINE = None
        _DRAIN_GENERATION += 1
        record_counter("drain_leases_expired")
        record_failure("drain_lease_expired")


def _drain_lease_remaining_locked() -> int | None:
    if not _DRAINING or _DRAIN_DEADLINE is None:
        return None
    return max(0, int(_DRAIN_DEADLINE - time.monotonic() + 0.999))


def set_draining(enabled: bool, *, lease_seconds: object | None = None) -> dict[str, object]:
    """Atomically change local Responses admission and return its snapshot."""
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if enabled:
            if not _DRAINING:
                _DRAIN_GENERATION += 1
            _DRAINING = True
            _DRAIN_DEADLINE = time.monotonic() + bounded_drain_lease_seconds(lease_seconds)
        elif _DRAINING:
            _DRAINING = False
            _DRAIN_DEADLINE = None
            _DRAIN_GENERATION += 1
        return {
            "draining": _DRAINING,
            "drain_generation": _DRAIN_GENERATION,
            "active_responses": _ACTIVE_RESPONSES,
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


def admit_response(*, timeout: float | None = None) -> tuple[str, int]:
    """Return ``acquired``, ``draining``, or ``timeout`` with active count."""
    global _ACTIVE_RESPONSES
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if _DRAINING:
            return "draining", _ACTIVE_RESPONSES
    acquired = _RESPONSE_SEMAPHORE.acquire(
        timeout=RESPONSES_QUEUE_TIMEOUT if timeout is None else timeout,
    )
    if not acquired:
        return "timeout", active_responses()
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if _DRAINING:
            _RESPONSE_SEMAPHORE.release()
            return "draining", _ACTIVE_RESPONSES
        _ACTIVE_RESPONSES += 1
        return "acquired", _ACTIVE_RESPONSES


def release_response_slot() -> int:
    """Release one active Responses slot and return the current active count."""
    global _ACTIVE_RESPONSES
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_RESPONSES = max(0, _ACTIVE_RESPONSES - 1)
        active = _ACTIVE_RESPONSES
    _RESPONSE_SEMAPHORE.release()
    return active


def is_loopback_client(address: str) -> bool:
    """Require lifecycle control surfaces to remain local."""
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def sanitization_count(note: str, field: str) -> int:
    """Read one non-negative aggregate count from a sanitizer note."""
    marker = f"{field}="
    start = note.find(marker)
    if start < 0:
        return 0
    value = note[start + len(marker) :].split(" ", 1)[0]
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def record_sanitization(note: str) -> None:
    """Account for sanitized fields without retaining their contents."""
    record_counter(
        "encrypted_replayed_reasoning_items_stripped",
        sanitization_count(note, "reasoning_items"),
    )
    record_counter(
        "encrypted_malformed_blocks_stripped",
        sanitization_count(note, "malformed_encrypted_blocks"),
    )
    record_counter(
        "unreplayable_images_stripped",
        sanitization_count(note, "local_image_items"),
    )


def _purge_expired_empty_response_failures_locked(now: float, cooldown_seconds: int) -> None:
    expired = [
        key
        for key, recorded_at in _EMPTY_RESPONSE_FAILURES.items()
        if recorded_at + cooldown_seconds <= now
    ]
    for key in expired:
        del _EMPTY_RESPONSE_FAILURES[key]


def remember_empty_response_failure(
    key: str,
    *,
    capacity: int = 1024,
    cooldown_seconds: int = 30,
    now: float | None = None,
) -> None:
    """Record one exhaustion in a bounded monotonic cooldown cache."""
    moment = time.monotonic() if now is None else now
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _purge_expired_empty_response_failures_locked(moment, cooldown_seconds)
        _EMPTY_RESPONSE_FAILURES[key] = moment
        while len(_EMPTY_RESPONSE_FAILURES) > capacity:
            oldest_key = min(
                _EMPTY_RESPONSE_FAILURES,
                key=lambda candidate: _EMPTY_RESPONSE_FAILURES[candidate],
            )
            del _EMPTY_RESPONSE_FAILURES[oldest_key]


def empty_response_cooldown_remaining(
    key: str,
    *,
    cooldown_seconds: int = 30,
    now: float | None = None,
) -> float:
    """Return remaining cooldown seconds, purging expired entries first."""
    moment = time.monotonic() if now is None else now
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _purge_expired_empty_response_failures_locked(moment, cooldown_seconds)
        recorded = _EMPTY_RESPONSE_FAILURES.get(key)
    if recorded is None:
        return 0
    remaining = recorded + cooldown_seconds - moment
    return remaining if remaining > 0 else 0


def empty_response_failure_count_for_test() -> int:
    """Expose only cache cardinality for bounded-state tests."""
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        return len(_EMPTY_RESPONSE_FAILURES)


def has_empty_response_failure_for_test(key: str) -> bool:
    """Report cooldown-key membership without exposing the mutable cache."""
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        return key in _EMPTY_RESPONSE_FAILURES
