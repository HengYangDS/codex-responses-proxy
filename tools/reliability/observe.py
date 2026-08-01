#!/usr/bin/env python3
"""Evaluate one secret-free Codex Responses Proxy runtime observation.

This tool consumes the JSON produced by ``python3 -m codex_responses_proxy.commands.control status --json``.  It does
not contact a listener, read configuration, retain request data, or change the
proxy lifecycle.  A caller may opt into a small local baseline with ``--state``
to compute deltas across comparable observations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from typing import TypeGuard


SCHEMA_VERSION = 1
EMPTY_RESPONSE_INCIDENT_THRESHOLD = 3
UPSTREAM_5XX_INCIDENT_THRESHOLD = 3
RESPONSE_FAILED_INCIDENT_THRESHOLD = 3
INPUT_VARIANT_VALIDATION_INCIDENT_THRESHOLD = 3
_UPSTREAM_5XX = re.compile(r"^http_(?:500|502|503|504|524)_full$")
_INPUT_VARIANT_VALIDATION_CLASS = "input_variant_validation_error"
_COUNTER_NAMES = (
    "responses_rejected_while_draining",
    "responses_local_queue_timeouts",
    "streams_failed",
    "streams_incomplete",
    "streams_pre_content_exhausted",
)


class ObservationError(ValueError):
    """Raised for an invalid or unsafe observation contract."""


def _is_object(value: object) -> TypeGuard[dict[str, Any]]:
    """Narrow a decoded JSON value to a string-keyed object."""

    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObservationError(f"{label} must be a non-negative integer")
    return value


def _count_map(value: object, *, label: str) -> dict[str, int]:
    if not _is_object(value):
        raise ObservationError(f"{label} must be an object")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key or len(key) > 96:
            raise ObservationError(f"{label} contains an invalid class name")
        result[key] = _integer(count, label=f"{label}.{key}")
    return result


def _runtime_identity(status: dict[str, Any]) -> dict[str, str | None]:
    runtime = status.get("runtime")
    if not _is_object(runtime):
        raise ObservationError("runtime must be an object")
    release = runtime.get("release")
    serving_payload_sha256 = runtime.get("serving_payload_sha256")
    if not isinstance(release, str) or not release:
        raise ObservationError("runtime.release must be a non-empty string")
    if serving_payload_sha256 is not None and (
        not isinstance(serving_payload_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", serving_payload_sha256)
    ):
        raise ObservationError("runtime.serving_payload_sha256 must be a SHA-256 digest or null")
    return {"release": release, "serving_payload_sha256": serving_payload_sha256}


def normalize_status(value: object) -> dict[str, Any]:
    """Extract the small, secret-free status contract used by this observer."""
    if not _is_object(value):
        raise ObservationError("status snapshot must be a JSON object")
    runtime = value.get("runtime")
    if not _is_object(runtime):
        raise ObservationError("status snapshot has no runtime object")
    payload_integrity = value.get("payload_integrity")
    if not _is_object(payload_integrity) or not isinstance(payload_integrity.get("ok"), bool):
        raise ObservationError("payload_integrity.ok must be boolean")
    service = value.get("service")
    if service is not None and not isinstance(service, str):
        raise ObservationError("service must be a string or null")
    listener_pids = value.get("listener_pids")
    if not isinstance(listener_pids, list) or any(
        isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 for pid in listener_pids
    ):
        raise ObservationError("listener_pids must be a list of positive integers")
    draining = runtime.get("draining")
    if not isinstance(draining, bool):
        raise ObservationError("runtime.draining must be boolean")
    active = _integer(runtime.get("active_responses"), label="runtime.active_responses")
    uptime = _integer(runtime.get("uptime_seconds"), label="runtime.uptime_seconds")
    last_failure = runtime.get("last_failure")
    last_failure_classification = (
        last_failure.get("classification")
        if _is_object(last_failure) and isinstance(last_failure.get("classification"), str)
        else None
    )
    return {
        "identity": _runtime_identity(value),
        "payload_integrity_ok": payload_integrity["ok"],
        "service": service,
        "listener_count": len(listener_pids),
        "draining": draining,
        "active_responses": active,
        "uptime_seconds": uptime,
        "counters": _count_map(runtime.get("counters"), label="runtime.counters"),
        "upstream_classifications": _count_map(
            runtime.get("upstream_classifications"), label="runtime.upstream_classifications"
        ),
        # Retain a stable class as context only.  It is intentionally excluded
        # from policy decisions: it may describe an old event in this process.
        "last_failure_classification": last_failure_classification,
    }


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ObservationError("state path must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationError(f"state file is unreadable: {exc}") from exc
    if not _is_object(value) or value.get("schema_version") != SCHEMA_VERSION:
        raise ObservationError("state file has an unsupported schema")
    baseline = value.get("baseline")
    if not _is_object(baseline):
        raise ObservationError("state file has no baseline")
    return baseline


def _write_state(path: Path, baseline: dict[str, Any]) -> None:
    """Atomically persist only the normalized, non-sensitive baseline."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ObservationError("state path must not be a symlink")
    payload = (
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "baseline": baseline},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _baseline(current: dict[str, Any], observed_at_unix: int) -> dict[str, Any]:
    return {
        "observed_at_unix": observed_at_unix,
        "identity": current["identity"],
        "uptime_seconds": current["uptime_seconds"],
        "counters": current["counters"],
        "upstream_classifications": current["upstream_classifications"],
    }


def _comparable(baseline: object, current: dict[str, Any]) -> tuple[bool, str]:
    if not _is_object(baseline):
        return False, "baseline_absent"
    if baseline.get("identity") != current["identity"]:
        return False, "runtime_identity_changed"
    old_uptime = baseline.get("uptime_seconds")
    if isinstance(old_uptime, bool) or not isinstance(old_uptime, int) or old_uptime < 0:
        return False, "baseline_invalid"
    if current["uptime_seconds"] < old_uptime:
        return False, "runtime_restarted"
    for field in ("counters", "upstream_classifications"):
        if not _is_object(baseline.get(field)):
            return False, "baseline_invalid"
    return True, "same_runtime"


def _delta(current: dict[str, int], baseline: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in current.items():
        old = baseline.get(key, 0)
        if isinstance(old, bool) or not isinstance(old, int) or old < 0:
            raise ObservationError("baseline contains an invalid counter")
        if value < old:
            raise ObservationError("comparable runtime counters moved backwards")
        if value > old:
            result[key] = value - old
    return dict(sorted(result.items()))


def _reason(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _append_runtime_reasons(current: dict[str, Any], add: Any) -> None:
    """Append classifications visible in the current runtime snapshot."""

    if not current["payload_integrity_ok"]:
        add(
            "payload_integrity_failed", "incident", "The installed payload manifest did not verify."
        )
    if current["service"] != "running":
        severity = "observe" if current["service"] in (None, "unknown") else "incident"
        add("service_not_running", severity, "The service is not confirmed as running.")
    if current["listener_count"] != 1:
        add(
            "listener_cardinality",
            "incident",
            "The status snapshot does not show exactly one verified listener.",
        )
    if current["draining"]:
        add(
            "drain_active",
            "observe",
            "The listener is in its bounded maintenance admission barrier.",
        )


def _append_delta_reasons(
    counter_deltas: dict[str, int],
    upstream_deltas: dict[str, int],
    add: Any,
    *,
    allow_drain: bool,
) -> None:
    """Append classifications measured inside one comparable window."""

    draining = counter_deltas.get("responses_rejected_while_draining", 0)
    if draining:
        add(
            "proxy_drain_rejections",
            "observe" if allow_drain else "incident",
            f"{draining} locally rejected Responses request(s) while drain was active.",
        )
    for name, code, detail in (
        (
            "responses_local_queue_timeouts",
            "local_queue_timeouts",
            "local admission queue timeout(s) occurred.",
        ),
        (
            "streams_incomplete",
            "local_stream_incomplete",
            "stream(s) ended with response.incomplete.",
        ),
        (
            "streams_pre_content_exhausted",
            "local_stream_pre_content_exhausted",
            "stream(s) exhausted pre-content reconnects.",
        ),
        ("streams_failed", "local_stream_failed", "stream failure(s) occurred after admission."),
    ):
        count = counter_deltas.get(name, 0)
        if count:
            add(code, "incident", f"{count} {detail}")
    bursts = (
        (
            upstream_deltas.get("empty_response", 0),
            EMPTY_RESPONSE_INCIDENT_THRESHOLD,
            "upstream_empty_response_burst",
            "classified upstream empty-response event(s) occurred in this window.",
        ),
        (
            sum(count for name, count in upstream_deltas.items() if _UPSTREAM_5XX.fullmatch(name)),
            UPSTREAM_5XX_INCIDENT_THRESHOLD,
            "upstream_5xx_burst",
            "classified retryable upstream 5xx event(s) occurred in this window.",
        ),
        (
            upstream_deltas.get("response_failed", 0),
            RESPONSE_FAILED_INCIDENT_THRESHOLD,
            "upstream_response_failed_burst",
            "classified upstream response_failed event(s) occurred in this window.",
        ),
        (
            upstream_deltas.get(_INPUT_VARIANT_VALIDATION_CLASS, 0),
            INPUT_VARIANT_VALIDATION_INCIDENT_THRESHOLD,
            "upstream_input_variant_validation_burst",
            "exact input-variant validation event(s) occurred in this window.",
        ),
    )
    for count, threshold, code, detail in bursts:
        if count:
            add(code, "incident" if count >= threshold else "observe", f"{count} {detail}")


def _window_deltas(
    current: dict[str, Any], baseline: object, now: int
) -> tuple[dict[str, Any], dict[str, int], dict[str, int]]:
    """Return comparison metadata plus counter deltas for one runtime window."""

    comparable, comparison = _comparable(baseline, current)
    window: dict[str, Any] = {"comparison": comparison, "comparable": comparable}
    if not comparable:
        return window, {}, {}
    if not _is_object(baseline):
        raise AssertionError("comparable baseline must be an object")
    counters = baseline.get("counters")
    upstream = baseline.get("upstream_classifications")
    if not _is_object(counters) or not _is_object(upstream):
        raise AssertionError("comparable baseline maps must be objects")
    old_observed = baseline.get("observed_at_unix")
    if (
        isinstance(old_observed, int)
        and not isinstance(old_observed, bool)
        and 0 <= old_observed <= now
    ):
        window["seconds"] = now - old_observed
    return (
        window,
        _delta(current["counters"], counters),
        _delta(current["upstream_classifications"], upstream),
    )


def evaluate(
    status: object,
    baseline: object | None = None,
    *,
    allow_drain: bool = False,
    observed_at_unix: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate one snapshot and return ``(report, next_baseline)``."""

    current = normalize_status(status)
    now = (
        int(time.time())
        if observed_at_unix is None
        else _integer(observed_at_unix, label="observed_at_unix")
    )
    reasons: list[dict[str, str]] = []

    def add(code: str, severity: str, detail: str) -> None:
        reasons.append(_reason(code, severity, detail))

    _append_runtime_reasons(current, add)
    window, counter_deltas, upstream_deltas = _window_deltas(current, baseline, now)
    if window["comparable"]:
        _append_delta_reasons(counter_deltas, upstream_deltas, add, allow_drain=allow_drain)
    else:
        add(
            "baseline_required",
            "observe",
            "No comparable prior snapshot exists; counters were not interpreted as a new incident.",
        )
    severities = {item["severity"] for item in reasons}
    state = (
        "incident"
        if "incident" in severities
        else ("observe" if "observe" in severities else "healthy")
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "observed_at_unix": now,
        "runtime": current["identity"],
        "window": window,
        "deltas": {"counters": counter_deltas, "upstream_classifications": upstream_deltas},
        "reasons": reasons,
        "limits": [
            "The observer reads one supplied secret-free status snapshot; it does not prove client-visible recovery.",
            "A changed release, aggregate serving-payload digest, or restarted process starts a new observation window rather than fabricating deltas.",
            "last_failure is context only because it can predate this window.",
            "Upstream empty_response, retryable 5xx, response_failed, and exact input-variant validation become incidents at three events per comparable window; lower counts remain observations.",
            "A deliberate drain can be classified with --allow-drain; the tool never starts, stops, reloads, or drains the listener.",
        ],
    }
    return report, _baseline(current, now)


def _read_status(path: str) -> object:
    try:
        if path == "-":
            return json.load(sys.stdin)
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationError(f"status snapshot is unreadable: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a secret-free Codex Responses Proxy reliability snapshot."
    )
    parser.add_argument(
        "--status-file",
        default="-",
        help=("codex_responses_proxy.commands.control status --json output, or - for stdin"),
    )
    parser.add_argument("--state", help="explicit optional path for a normalized local baseline")
    parser.add_argument(
        "--allow-drain",
        action="store_true",
        help="classify new local drain rejections as observe during approved maintenance",
    )
    args = parser.parse_args(argv)
    try:
        baseline = _load_state(Path(args.state)) if args.state else None
        report, next_baseline = evaluate(
            _read_status(args.status_file), baseline, allow_drain=args.allow_drain
        )
        if args.state:
            _write_state(Path(args.state), next_baseline)
    except ObservationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
