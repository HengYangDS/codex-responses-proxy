#!/usr/bin/env python3
"""dmx-responses-proxy — strip un-verifiable encrypted reasoning from Codex → dmxapi.

Why this exists
---------------
Codex CLI (closed binary) uses the OpenAI *Responses* wire API. Each turn the model
returns a ``reasoning`` item carrying ``encrypted_content`` (a provider-encrypted
``gAAAAAB...`` Fernet blob). Codex persists these and *replays* them on every later
turn. dmxapi (https://www.dmxapi.cn) encrypts those blobs with its own key and, after
key rotation / backend routing, can no longer decrypt a blob it is handed back →

    HTTP 400 "The encrypted content gAAA... could not be verified.
    Reason: Encrypted content could not be decrypted or parsed."  (invalid_encrypted_content)

Codex has no config switch to stop the replay (verified against the v0.142.5 config
schema), and it is a compiled binary we cannot patch. So we sit a tiny local proxy
between Codex and dmxapi and remove the replayed blobs from each outbound request.
The model still reasons every turn; it just isn't handed stale replayed reasoning
items that the third-party endpoint cannot verify. Typed encrypted-content blocks in
agent messages are preserved because their schema requires the payload. This mirrors
the compatible network-edge approach without rewriting local conversation history.

Design guarantees
-----------------
* Transparent: forwards method, path, query, headers (incl. ``Authorization``) and
  body to the real upstream. Codex's keychain Bearer token passes through untouched.
* Surgical: only mutates JSON bodies of POSTs whose path contains ``/responses``.
  For those it drops (a) top-level replayed ``reasoning`` input items, (b) historical
  ``input_image`` items whose URL cannot be fetched remotely, and (c)
  ``reasoning.encrypted_content`` from the ``include[]`` list. Other typed
  ``encrypted_content`` blocks stay intact because their schema requires the payload.
  SSE output is still stripped before Codex persists it as later history.
* Fail-open: any parse/transform error → the *original* bytes are forwarded unchanged.
  Worst case equals today's behavior; it can never harden into a new failure mode.
* Streaming: the upstream SSE response is streamed back chunk-by-chunk unbuffered.
* Stdlib only: no third-party deps, no build step.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import queue
import re
import subprocess
import stat
import sys
import time
import socket
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("DMX_UPSTREAM", "https://www.dmxapi.cn").rstrip("/")
HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
LOG_PATH = os.environ.get("DMX_PROXY_LOG", os.path.expanduser("~/.codex/log/dmx-responses-proxy.log"))


def _loaded_source_sha256() -> str | None:
    """Capture the proxy payload identity once at import time."""
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return None


LOADED_SOURCE_SHA256 = _loaded_source_sha256()


def source_sha256() -> str | None:
    """Return the payload hash captured when this process loaded the proxy."""
    return LOADED_SOURCE_SHA256


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read one bounded integer setting without making startup fragile."""
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, value))


# Logs are operational breadcrumbs, not a transcript store. Retain a small bounded
# ring so an outage cannot consume the host's disk or preserve historical request
# material indefinitely. The max includes one timestamped diagnostic line.
LOG_MAX_BYTES = _bounded_env_int("DMX_PROXY_LOG_MAX_BYTES", 4 * 1024 * 1024, 4 * 1024, 64 * 1024 * 1024)
LOG_BACKUP_COUNT = _bounded_env_int("DMX_PROXY_LOG_BACKUP_COUNT", 3, 0, 10)
_LOG_LINE_MAX_BYTES = 1024
_LOG_LOCK = threading.Lock()
RESPONSES_MAX_CONCURRENCY = int(os.environ.get("DMX_RESPONSES_MAX_CONCURRENCY", "64"))
RESPONSES_QUEUE_TIMEOUT = float(os.environ.get("DMX_RESPONSES_QUEUE_TIMEOUT", "120"))
UPSTREAM_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_TIMEOUT", "900"))
UPSTREAM_READ_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_READ_TIMEOUT", "240"))
# DMX rejects deterministic large replay payloads with an HTTP 400
# ``response_failed`` result. This limit is deliberately conservative: live probes
# on 2026-07-14 accepted pair-valid payloads in the 482--513 KiB range.
RESPONSE_FAILED_COMPACTION_BUDGET = int(
    os.environ.get("DMX_RESPONSE_FAILED_COMPACTION_BUDGET", str(512 * 1024))
)
# Each fallback stage must make a material reduction. A small replay trim often
# remains inside the upstream failure regime, while a half-window suffix was
# accepted by live probes.
RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR = 2
RESPONSE_FAILED_MAX_STAGES = max(0, int(os.environ.get("DMX_RESPONSE_FAILED_MAX_STAGES", "3")))
# HTTP 477 ``empty_response`` gets exactly one dedicated, semantics-preserving
# fallback slot instead of the ordinary identical-bytes retry budget. The
# compat policy version is folded into the cooldown key so a future change to
# the projection rules below cannot collide with an older cached cooldown.
EMPTY_RESPONSE_COMPAT_POLICY_VERSION = "empty-response-fallback-v1"
EMPTY_RESPONSE_OPAQUE_REASONING_MARKER = (
    "[reasoning omitted: opaque provider state cannot be replayed]"
)
EMPTY_RESPONSE_FALLBACK_BUDGET = _bounded_env_int(
    "DMX_EMPTY_RESPONSE_FALLBACK_BUDGET", 4 * 1024 * 1024, 4 * 1024, 4 * 1024 * 1024,
)
EMPTY_RESPONSE_COOLDOWN_SECONDS = _bounded_env_int(
    "DMX_EMPTY_RESPONSE_COOLDOWN_SECONDS", 30, 1, 300,
)
# Fixed, not env-configurable: this is a bounded local safety cap, not a tunable.
EMPTY_RESPONSE_COOLDOWN_CAPACITY = 1024
# Fixed, not env-configurable: the classified-477 fallback is dispatched as
# its own immediate, nested upstream request (see the 477 branch below), not
# as another iteration of the outer retry loop. It therefore never consumes
# or depends on a slot in that loop's range and fires exactly once whenever a
# 477 is classified -- even when that classification arrives on the outer
# loop's very last iteration. This constant documents that dedicated,
# always-available attempt.
EMPTY_RESPONSE_DEDICATED_SLOTS = 1
# One dedicated outer-loop slot for the ``response_failed`` dialogue-only
# recovery continuation below. This is distinct from, and must not borrow
# capacity from, the (separately bounded, independently disable-able)
# ``response_failed`` pair-safe compaction stage budget: setting
# ``DMX_RESPONSE_FAILED_MAX_STAGES=0`` must not silently remove the one spare
# loop iteration the dialogue-only recovery needs to make its own attempt.
RESPONSE_FAILED_DIALOGUE_SLOTS = 1
_RESPONSES_SEM = threading.BoundedSemaphore(max(1, RESPONSES_MAX_CONCURRENCY))
# The admission gate and active counter deliberately share one lock.  A drain
# transition must be atomic with admission: after ``draining`` becomes true,
# no later request may increment ``active_responses``.  Merely sampling an
# active counter before a reload leaves a window for a new SSE request to enter.
_RESPONSE_GATE_LOCK = threading.Lock()
_ACTIVE_RESPONSES = 0
_ACTIVE_HANDLERS = 0
_DRAINING = False
_DRAIN_GENERATION = 0
_DRAIN_DEADLINE = None
_MIN_DRAIN_LEASE_SECONDS = 1
_MAX_DRAIN_LEASE_SECONDS = 900
_REQUEST_SEQ = 0
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
_UPSTREAM_CLASSIFICATIONS = {}
_LAST_FAILURE = None
# Bounded local cooldown for classified empty-response exhaustion: keyed by
# ``_empty_response_policy_fingerprint``, capped at EMPTY_RESPONSE_COOLDOWN_CAPACITY
# entries so a hostile or buggy client fan-out cannot grow this without bound.
_EMPTY_RESPONSE_FAILURES_LOCK = threading.Lock()
_EMPTY_RESPONSE_FAILURES: dict[str, float] = {}

# Rolling handoff is a process-local transaction.  The listener socket remains
# open throughout; only the process allowed to call ``accept()`` changes at the
# COMMIT barrier.  Keep this state independent from the Responses drain gate:
# a prepared child is not yet accepting even though it is not draining.
HANDOFF_PROTOCOL_VERSION = 2
HANDOFF_CONTROL_MAX_BYTES = 32 * 1024
HANDOFF_READY_TIMEOUT_SECONDS = 10.0
HANDOFF_SERVING_TIMEOUT_SECONDS = 10.0
HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS = 5.0
HANDOFF_DEFAULT_LEASE_SECONDS = 30.0


class HandoffError(RuntimeError):
    """A bounded rolling-handoff transaction could not be completed safely."""


class HandoffConflict(HandoffError):
    """Another process-local handoff already owns the single-flight session."""


_HANDOFF_TRANSITIONS = {
    "idle": frozenset(("preparing",)),
    "preparing": frozenset(("ready", "aborting")),
    "ready": frozenset(("committing", "aborting")),
    "committing": frozenset(("serving", "aborting")),
    "serving": frozenset(("finalizing", "aborting")),
    "finalizing": frozenset(("finalized", "aborting")),
    "finalized": frozenset(("idle",)),
    "aborting": frozenset(("rolled_back",)),
    "rolled_back": frozenset(("idle",)),
}
_HANDOFF_LOCK = threading.RLock()
_HANDOFF_SESSION: dict[str, object] = {}
_SERVER_INSTANCE = None


def _validate_handoff_transition(current_state: str, target_state: str) -> bool:
    """Return whether one explicit protocol-v2 state transition is legal."""
    return target_state in _HANDOFF_TRANSITIONS.get(current_state, frozenset())


def _reset_handoff_session_to_idle() -> None:
    """Reset the process-local transaction only after child cleanup is complete."""
    with _HANDOFF_LOCK:
        _HANDOFF_SESSION.clear()
        _HANDOFF_SESSION.update({
            "state": "idle",
            "transaction_id": None,
            "child_pid": None,
            "outcome": None,
            "outcome_ready": threading.Event(),
            "lease_seconds": HANDOFF_DEFAULT_LEASE_SECONDS,
            "drain_deadline": None,
        })


def _transition_handoff(target_state: str) -> None:
    """Advance the locked session through the declared transition table."""
    with _HANDOFF_LOCK:
        current = str(_HANDOFF_SESSION.get("state", "idle"))
        if not _validate_handoff_transition(current, target_state):
            raise HandoffError(f"illegal handoff transition {current}->{target_state}")
        _HANDOFF_SESSION["state"] = target_state


def _payload_manifest_sha256() -> str | None:
    """Hash the current payload manifest without exposing its contents."""
    candidate = Path(__file__).resolve().parents[1] / "payload-manifest.json"
    try:
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return None


def _disk_payload_matches_handoff_expected(expected: dict) -> bool:
    """Verify the payload that a replacement child would load from disk."""
    try:
        proxy_path = Path(__file__).resolve()
        disk_source = hashlib.sha256(proxy_path.read_bytes()).hexdigest()
    except OSError:
        return False
    return (
        expected.get("release") == release_version()
        and expected.get("source_sha256") == disk_source
        and expected.get("manifest_sha256") == _payload_manifest_sha256()
    )


def _handoff_runtime_identity() -> dict[str, object]:
    """Return secret-free process and transaction identity for health proofs."""
    with _HANDOFF_LOCK, _RESPONSE_GATE_LOCK:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        accepting = not _DRAINING and state in {"idle", "serving", "finalized"}
        return {
            "pid": os.getpid(),
            "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
            "handoff_transaction_id": _HANDOFF_SESSION.get("transaction_id"),
            "handoff_state": state,
            "payload_manifest_sha256": _payload_manifest_sha256(),
            "accepting": accepting,
            "active_handlers": _ACTIVE_HANDLERS,
        }


def _handoff_popen_kwargs(listener_fd: int | None, *, is_windows: bool) -> dict:
    """Return platform-specific, pipe-only child process settings."""
    kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if is_windows:
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        if listener_fd is None:
            raise HandoffError("POSIX handoff requires a listener fd")
        kwargs["pass_fds"] = (listener_fd,)
        kwargs["start_new_session"] = True
    return kwargs


class _HandoffChild:
    """One bounded structured control channel to a prepared replacement."""

    def __init__(self, process: subprocess.Popen):
        if process.stdin is None or process.stdout is None:
            raise HandoffError("handoff child pipes are unavailable")
        self.process = process
        self._send_lock = threading.Lock()
        self._events: queue.Queue = queue.Queue()
        self._reader_started = False
        self._reader_lock = threading.Lock()

    def send_message(self, message: dict) -> None:
        if not isinstance(message, dict):
            raise HandoffError("handoff message must be an object")
        encoded = json.dumps(
            message, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii") + b"\n"
        if len(encoded) > HANDOFF_CONTROL_MAX_BYTES:
            raise HandoffError("handoff message exceeds the control limit")
        with self._send_lock:
            try:
                self.process.stdin.write(encoded)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise HandoffError("handoff control pipe write failed") from exc

    def _start_reader(self) -> None:
        with self._reader_lock:
            if self._reader_started:
                return
            self._reader_started = True

            def read_events() -> None:
                try:
                    while True:
                        line = self.process.stdout.readline(HANDOFF_CONTROL_MAX_BYTES + 1)
                        if not line:
                            self._events.put(HandoffError("handoff child control pipe closed"))
                            return
                        if len(line) > HANDOFF_CONTROL_MAX_BYTES or not line.endswith(b"\n"):
                            self._events.put(HandoffError("handoff child message exceeds the control limit"))
                            return
                        try:
                            message = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            self._events.put(HandoffError("handoff child emitted invalid JSON"))
                            return
                        if not isinstance(message, dict):
                            self._events.put(HandoffError("handoff child message must be an object"))
                            return
                        self._events.put(message)
                except (OSError, ValueError) as exc:
                    self._events.put(HandoffError("handoff child control pipe read failed"))

            threading.Thread(target=read_events, daemon=True, name="dmx-handoff-reader").start()

    def recv_message(self, timeout: float) -> dict:
        self._start_reader()
        try:
            item = self._events.get(timeout=max(0.01, float(timeout)))
        except queue.Empty as exc:
            raise HandoffError("handoff child response timed out") from exc
        if isinstance(item, Exception):
            raise item
        return item

    def terminate_bounded(self, timeout: float) -> bool:
        if self.process.poll() is not None:
            return True
        try:
            self.process.terminate()
            self.process.wait(timeout=max(0.01, float(timeout)))
            return True
        except (OSError, subprocess.TimeoutExpired):
            return self.process.poll() is not None

    def kill_bounded(self, timeout: float) -> bool:
        if self.process.poll() is not None:
            return True
        try:
            self.process.kill()
            self.process.wait(timeout=max(0.01, float(timeout)))
            return True
        except (OSError, subprocess.TimeoutExpired):
            return self.process.poll() is not None


def _spawn_handoff_child(
    listener: socket.socket, expected: dict, *, is_windows: bool | None = None
) -> _HandoffChild:
    """Spawn a non-accepting replacement and send its bounded PREPARE message."""
    windows = os.name == "nt" if is_windows is None else bool(is_windows)
    listener_fd = None if windows else listener.fileno()
    kwargs = _handoff_popen_kwargs(listener_fd, is_windows=windows)
    env = os.environ.copy()
    env["DMX_HANDOFF_CHILD"] = "1"
    kwargs["env"] = env
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--handoff-child"],
        **kwargs,
    )
    child = _HandoffChild(process)
    message = {
        "type": "prepare",
        "protocol_version": HANDOFF_PROTOCOL_VERSION,
        "transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "source_sha256": expected["source_sha256"],
        "manifest_sha256": expected["manifest_sha256"],
    }
    if windows:
        try:
            shared = listener.share(process.pid)
        except Exception as exc:
            child.terminate_bounded(HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS)
            raise HandoffError("Windows listener sharing failed") from exc
        message["listener_share_b64"] = base64.b64encode(shared).decode("ascii")
    else:
        message["listener_fd"] = listener_fd
    try:
        child.send_message(message)
    except Exception:
        if not child.terminate_bounded(HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS):
            child.kill_bounded(HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS)
        raise
    return child


def _listener_from_handoff_prepare(message: dict) -> socket.socket:
    """Reconstruct the already-listening socket from a validated PREPARE."""
    if "listener_share_b64" in message:
        encoded = message.get("listener_share_b64")
        if not isinstance(encoded, str) or len(encoded) > HANDOFF_CONTROL_MAX_BYTES:
            raise HandoffError("invalid Windows listener share")
        try:
            shared = base64.b64decode(encoded.encode("ascii"), validate=True)
            return socket.fromshare(shared)
        except Exception as exc:
            raise HandoffError("Windows listener reconstruction failed") from exc
    listener_fd = message.get("listener_fd")
    if not isinstance(listener_fd, int) or listener_fd < 0:
        raise HandoffError("invalid inherited listener fd")
    return socket.socket(fileno=listener_fd)


def _handoff_message_matches(message: object, expected: dict, message_type: str) -> bool:
    """Validate one child event against the complete transaction identity."""
    if not isinstance(message, dict) or message.get("type") != message_type:
        return False
    common = {
        "type": message_type,
        "pid": expected["pid"],
        "transaction_id": expected["transaction_id"],
    }
    if message_type == "ready":
        common.update({
            "protocol_version": HANDOFF_PROTOCOL_VERSION,
            "release": expected["release"],
            "source_sha256": expected["source_sha256"],
            "manifest_sha256": expected["manifest_sha256"],
        })
    return set(message) == set(common) and all(message.get(key) == value for key, value in common.items())


def _health_matches_handoff(health: object, expected: dict) -> bool:
    """Require the exact serving proof before FINALIZE."""
    if not isinstance(health, dict):
        return False
    required = {
        "pid": expected["pid"],
        "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
        "handoff_transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "source_sha256": expected["source_sha256"],
        "payload_manifest_sha256": expected["manifest_sha256"],
        "handoff_state": "serving",
        "accepting": True,
    }
    return all(health.get(key) == value for key, value in required.items())


def _probe_handoff_health(port: int, *, timeout_seconds: float) -> dict:
    """Read one loopback-only child health proof through the shared listener."""
    url = f"http://127.0.0.1:{int(port)}/healthz"
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=max(0.1, float(timeout_seconds))) as response:
        payload = response.read(HANDOFF_CONTROL_MAX_BYTES + 1)
    if len(payload) > HANDOFF_CONTROL_MAX_BYTES:
        raise HandoffError("handoff health response exceeds the control limit")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff health response is invalid") from exc
    if not isinstance(decoded, dict):
        raise HandoffError("handoff health response must be an object")
    return decoded


def _rollback_handoff_without_child() -> None:
    """Return a failed PREPARE to idle when no process survived creation."""
    with _HANDOFF_LOCK:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        if state in {"preparing", "ready", "committing", "serving", "finalizing"}:
            _transition_handoff("aborting")
            _transition_handoff("rolled_back")
        if _HANDOFF_SESSION.get("state") == "rolled_back":
            _transition_handoff("idle")
        _HANDOFF_SESSION["transaction_id"] = None
        _HANDOFF_SESSION["child_pid"] = None


def _abort_handoff(child: _HandoffChild) -> None:
    """Abort one child and confirm its exit before exposing rollback."""
    with _HANDOFF_LOCK:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        if state not in {"aborting", "rolled_back", "idle"}:
            _transition_handoff("aborting")
    try:
        child.send_message({"type": "abort"})
    except Exception:
        pass
    terminated = False
    try:
        terminated = bool(child.terminate_bounded(HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS))
    except Exception:
        terminated = False
    if not terminated:
        try:
            terminated = bool(child.kill_bounded(HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS))
        except Exception:
            terminated = False
    if not terminated:
        raise HandoffError("handoff child could not be confirmed exited")
    with _HANDOFF_LOCK:
        if _HANDOFF_SESSION.get("state") == "aborting":
            _transition_handoff("rolled_back")


def _prepare_handoff(
    server: ThreadingHTTPServer,
    expected: dict,
    *,
    timeout_seconds: float = HANDOFF_READY_TIMEOUT_SECONDS,
    lease_seconds: float = HANDOFF_DEFAULT_LEASE_SECONDS,
) -> dict:
    """Prepare and validate a non-accepting replacement without closing admission."""
    required = ("transaction_id", "release", "source_sha256", "manifest_sha256")
    if not isinstance(expected, dict) or any(
        not isinstance(expected.get(key), str) or not expected.get(key) for key in required
    ):
        raise HandoffError("handoff request identity is incomplete")
    with _HANDOFF_LOCK:
        if _HANDOFF_SESSION.get("state") == "finalized":
            _reset_handoff_session_to_idle()
        if _HANDOFF_SESSION.get("state") != "idle":
            raise HandoffConflict("handoff is already in progress")
        _transition_handoff("preparing")
        _HANDOFF_SESSION.update({
            "transaction_id": expected["transaction_id"],
            "child_pid": None,
            "outcome": None,
            "outcome_ready": threading.Event(),
            "lease_seconds": _bounded_drain_lease_seconds(lease_seconds),
            "timeout_seconds": max(0.1, float(timeout_seconds)),
        })
    child = None
    try:
        child = _spawn_handoff_child(server.socket, expected)
        child_expected = {**expected, "pid": child.process.pid}
        ready = child.recv_message(max(0.1, float(timeout_seconds)))
        if not _handoff_message_matches(ready, child_expected, "ready"):
            raise HandoffError("handoff child READY identity mismatch")
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION.update({
                "child_pid": child.process.pid,
                "child": child,
                "expected": dict(expected),
            })
            _transition_handoff("ready")
        return {
            "child": child,
            "expected": dict(expected),
            "timeout_seconds": max(0.1, float(timeout_seconds)),
            "lease_seconds": _bounded_drain_lease_seconds(lease_seconds),
        }
    except Exception as exc:
        if child is not None:
            try:
                _abort_handoff(child)
            finally:
                with _HANDOFF_LOCK:
                    if _HANDOFF_SESSION.get("state") == "rolled_back":
                        _transition_handoff("idle")
                    _HANDOFF_SESSION["transaction_id"] = None
                    _HANDOFF_SESSION["child_pid"] = None
        else:
            _rollback_handoff_without_child()
        if isinstance(exc, HandoffError):
            raise
        raise HandoffError("handoff child preparation failed") from exc


def _set_handoff_outcome(outcome: str) -> None:
    with _HANDOFF_LOCK:
        _HANDOFF_SESSION["outcome"] = outcome
        event = _HANDOFF_SESSION.get("outcome_ready")
        if isinstance(event, threading.Event):
            event.set()


def _commit_prepared_handoff(server: ThreadingHTTPServer, prepared: dict) -> str:
    """Cross the accept barrier and either finalize or expose a resumable rollback."""
    child = prepared["child"]
    expected = prepared["expected"]
    child_expected = {**expected, "pid": child.process.pid}
    timeout_seconds = prepared["timeout_seconds"]
    accept_stopped = False
    try:
        _transition_handoff("committing")
        drain = _set_draining(True, lease_seconds=prepared["lease_seconds"])
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION["drain_deadline"] = time.monotonic() + prepared["lease_seconds"]
            _HANDOFF_SESSION["drain_generation"] = drain["drain_generation"]
        server.shutdown()
        accept_stopped = True
        child.send_message({"type": "commit"})
        serving = child.recv_message(timeout_seconds)
        if not _handoff_message_matches(serving, child_expected, "serving"):
            raise HandoffError("handoff child SERVING identity mismatch")
        _transition_handoff("serving")
        address = getattr(server, "server_address", None)
        health_port = address[1] if isinstance(address, (tuple, list)) and len(address) > 1 else PORT
        health = _probe_handoff_health(health_port, timeout_seconds=timeout_seconds)
        if not _health_matches_handoff(health, child_expected):
            raise HandoffError("handoff child health identity mismatch")
        _transition_handoff("finalizing")
        child.send_message({"type": "finalize"})
        finalized = child.recv_message(timeout_seconds)
        if not _handoff_message_matches(finalized, child_expected, "finalized"):
            raise HandoffError("handoff child FINALIZED identity mismatch")
        _transition_handoff("finalized")
        _set_handoff_outcome("finalized")
        return "finalized"
    except Exception:
        abort_confirmed = False
        try:
            _abort_handoff(child)
            abort_confirmed = True
        except Exception:
            _set_handoff_outcome("abort_unconfirmed")
        if abort_confirmed:
            _set_handoff_outcome("rolled_back")
        if not accept_stopped:
            try:
                server.shutdown()
            except Exception:
                pass
        return "rolled_back" if abort_confirmed else "abort_unconfirmed"


_reset_handoff_session_to_idle()

# Cross-platform hardening: never route upstream calls through a system/registry/env
# HTTP proxy. On macOS and Windows, urllib.request.getproxies() consults the OS proxy
# settings (System Configuration / registry), so a host behind a corporate proxy could
# silently tunnel our upstream calls. We open every upstream request through an opener
# with an EMPTY ProxyHandler, forcing a direct connection regardless of host config.
# (Same effect on Linux, which only reads env vars — this just makes it explicit.)
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def release_version() -> str:
    """Read the packaged release identity without making startup depend on CWD."""
    candidates = (
        Path(__file__).resolve().parents[1] / "VERSION",
        Path(__file__).resolve().parents[2] / "VERSION",
    )
    for candidate in candidates:
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "0+unknown"


def _urlopen(req, timeout):
    """urlopen that always bypasses any system/env HTTP proxy (see _OPENER)."""
    return _OPENER.open(req, timeout=timeout)

# Headers that belong to *this* hop and must not be relayed verbatim.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "accept-encoding",  # force identity so upstream doesn't gzip past our stream copy
}


class _ResilientProxyServer(ThreadingHTTPServer):
    """Threading HTTP server hardened for subagent fan-out.

    Codex subagents fan out into many concurrent /v1/responses SSE streams. The
    stdlib default listen backlog (``request_queue_size = 5``) means the 6th+
    simultaneous connection can be RST by the OS before ``accept()`` runs — the
    ``ConnectionResetError: [Errno 54] Connection reset by peer`` seen in the log.
    Raise the backlog well above any realistic fan-out, reuse the address for clean
    restarts, and run handler threads as daemons so a dropped client never leaks a
    thread. This addresses the LOCAL connection-stability failure (distinct from
    upstream dmxapi stream flakiness, which the reconnect logic handles).
    """
    request_queue_size = 256
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self):
        # Disable Nagle so SSE chunks flush promptly to the local client.
        super().server_bind()
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

    def get_request(self):
        request, address = super().get_request()
        try:
            request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        return request, address

    def process_request_thread(self, request, client_address):
        global _ACTIVE_HANDLERS
        with _RESPONSE_GATE_LOCK:
            _ACTIVE_HANDLERS += 1
        try:
            super().process_request_thread(request, client_address)
        finally:
            with _RESPONSE_GATE_LOCK:
                _ACTIVE_HANDLERS = max(0, _ACTIVE_HANDLERS - 1)

    def handle_error(self, request, client_address):
        # A client that resets/closes mid-stream is normal at subagent turn end;
        # log quietly instead of dumping a full traceback to stderr.
        import sys as _sys
        exc = _sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            _log(f"client_closed_mid_request exception={_safe_exception_label(exc)}")
            return
        super().handle_error(request, client_address)


_LOG_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|bearer)\s*[:=]?\s*(?:bearer\s+)?[^\s,;]+"),
    re.compile(r"\bgAAAA[A-Za-z0-9_-]+"),
)


def _safe_request_path(value: str) -> str:
    """Return a bounded request path without query values or client-provided text."""
    try:
        path = urllib.parse.urlsplit(value).path
    except (TypeError, ValueError):
        return "/invalid-path"
    if not isinstance(path, str) or not path.startswith("/"):
        return "/invalid-path"
    normalized = re.sub(r"[^A-Za-z0-9._~/-]", "_", path)
    return normalized[:192] or "/"


def _safe_exception_label(exc: BaseException | None) -> str:
    """Expose only the stable exception class, never an upstream message."""
    return exc.__class__.__name__ if exc is not None else "UnknownError"


def _redact_log_message(msg: str) -> str:
    """Provide a defensive last line of protection for operational log messages."""
    value = str(msg).replace("\r", " ").replace("\n", " ")
    for pattern in _LOG_SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    encoded = value.encode("utf-8", "replace")
    if len(encoded) > _LOG_LINE_MAX_BYTES:
        value = encoded[:_LOG_LINE_MAX_BYTES].decode("utf-8", "ignore") + " [truncated]"
    return value


def _rotate_log_if_needed(path: Path, incoming_bytes: int) -> int:
    """Enforce bounded local retention and return discarded oversized bytes."""
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
        # An oversized legacy segment cannot be retained without violating the
        # configured cap. Delete it without reading or copying its content.
        path.unlink(missing_ok=True)
        discarded += current_size
    elif LOG_BACKUP_COUNT <= 0:
        path.unlink(missing_ok=True)
    else:
        oldest = path.with_name(f"{path.name}.{LOG_BACKUP_COUNT}")
        oldest.unlink(missing_ok=True)
        for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                if source.stat().st_size > LOG_MAX_BYTES:
                    discarded += source.stat().st_size
                    source.unlink(missing_ok=True)
                else:
                    source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))

    # Older deployments predate the cap. Prune any such segment immediately
    # rather than preserving an unbounded legacy file for a full rotation cycle.
    for index in range(1, LOG_BACKUP_COUNT + 1):
        segment = path.with_name(f"{path.name}.{index}")
        try:
            if segment.stat().st_size > LOG_MAX_BYTES:
                discarded += segment.stat().st_size
                segment.unlink()
        except OSError:
            continue
    return discarded


def _log(msg: str) -> None:
    message = _redact_log_message(msg)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n"
    encoded_line = line.encode("utf-8", "replace")
    try:
        path = Path(LOG_PATH)
        with _LOG_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            discarded = _rotate_log_if_needed(path, len(encoded_line))
            if discarded:
                line = (
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"log_retention_discarded_oversized_bytes={discarded} {message}\n"
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


def _next_request_id() -> int:
    global _REQUEST_SEQ
    with _RESPONSE_GATE_LOCK:
        _REQUEST_SEQ += 1
        return _REQUEST_SEQ


def _record_counter(name: str, amount: int = 1) -> None:
    """Record one secret-free runtime counter."""
    if amount <= 0:
        return
    with _METRICS_LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + amount


def _record_upstream_classification(name: str) -> None:
    """Record a bounded upstream outcome class, never an upstream payload."""
    with _METRICS_LOCK:
        _UPSTREAM_CLASSIFICATIONS[name] = _UPSTREAM_CLASSIFICATIONS.get(name, 0) + 1


def _record_failure(classification: str) -> None:
    """Retain only the latest failure class and time, never request data."""
    global _LAST_FAILURE
    with _METRICS_LOCK:
        _LAST_FAILURE = {
            "classification": classification,
            "at_unix": int(time.time()),
        }


def runtime_status() -> dict:
    """Return a machine-readable, secret-free local reliability snapshot."""
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
    status = {
        "release": release_version(),
        "source_sha256": source_sha256(),
        "uptime_seconds": max(0, int(time.time() - _STARTED_AT)),
        "active_responses": active_responses,
        "draining": draining,
        "drain_generation": drain_generation,
        "drain_lease_remaining_seconds": drain_lease_remaining_seconds,
        "counters": counters,
        "upstream_classifications": upstream,
        "last_failure": last_failure,
    }
    status.update(_handoff_runtime_identity())
    return status


def _reset_runtime_metrics_for_test() -> None:
    """Reset process-local observability state for deterministic unit tests."""
    global _ACTIVE_RESPONSES, _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE, _LAST_FAILURE
    with _RESPONSE_GATE_LOCK:
        _ACTIVE_RESPONSES = 0
        _DRAINING = False
        _DRAIN_GENERATION = 0
        _DRAIN_DEADLINE = None
    with _METRICS_LOCK:
        for name in _COUNTERS:
            _COUNTERS[name] = 0
        _UPSTREAM_CLASSIFICATIONS.clear()
        _LAST_FAILURE = None
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _EMPTY_RESPONSE_FAILURES.clear()


def _bounded_drain_lease_seconds(value: object | None) -> int:
    """Return a bounded admission lease without making control startup fragile."""
    try:
        seconds = int(value) if value is not None else 30
    except (TypeError, ValueError):
        return 30
    return min(_MAX_DRAIN_LEASE_SECONDS, max(_MIN_DRAIN_LEASE_SECONDS, seconds))


def _expire_drain_locked() -> None:
    """Fail open after an abandoned lifecycle operation's bounded lease."""
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    if _DRAINING and _DRAIN_DEADLINE is not None and time.monotonic() >= _DRAIN_DEADLINE:
        _DRAINING = False
        _DRAIN_DEADLINE = None
        _DRAIN_GENERATION += 1
        _record_counter("drain_leases_expired")
        _record_failure("drain_lease_expired")


def _drain_lease_remaining_locked() -> int | None:
    """Return a rounded-up lease horizon for operational inspection."""
    if not _DRAINING or _DRAIN_DEADLINE is None:
        return None
    return max(0, int(_DRAIN_DEADLINE - time.monotonic() + 0.999))


def _set_draining(enabled: bool, *, lease_seconds: object | None = None) -> dict:
    """Atomically change local Responses admission and return its snapshot.

    This is intentionally process-local.  A replacement listener starts in the
    serving state, so a successful reload cannot accidentally retain a stale
    drain latch from the prior process.
    """
    global _DRAINING, _DRAIN_GENERATION, _DRAIN_DEADLINE
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        if enabled:
            if not _DRAINING:
                _DRAIN_GENERATION += 1
            _DRAINING = True
            _DRAIN_DEADLINE = time.monotonic() + _bounded_drain_lease_seconds(lease_seconds)
        elif _DRAINING:
            _DRAINING = enabled
            _DRAIN_DEADLINE = None
            _DRAIN_GENERATION += 1
        return {
            "draining": _DRAINING,
            "drain_generation": _DRAIN_GENERATION,
            "active_responses": _ACTIVE_RESPONSES,
            "drain_lease_remaining_seconds": _drain_lease_remaining_locked(),
        }


def _drain_snapshot() -> tuple[bool, int, int]:
    """Return an admission-consistent drain/active snapshot."""
    with _RESPONSE_GATE_LOCK:
        _expire_drain_locked()
        return _DRAINING, _DRAIN_GENERATION, _ACTIVE_RESPONSES


def _is_loopback_client(address: str) -> bool:
    """Require the lifecycle control surface to remain local even if hosted wider."""
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _sanitization_count(note: str, field: str) -> int:
    marker = f"{field}="
    start = note.find(marker)
    if start < 0:
        return 0
    value = note[start + len(marker):].split(" ", 1)[0]
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def _record_sanitization(note: str) -> None:
    """Account for sanitized request fields without retaining their contents."""
    _record_counter(
        "encrypted_replayed_reasoning_items_stripped",
        _sanitization_count(note, "reasoning_items"),
    )
    _record_counter(
        "encrypted_malformed_blocks_stripped",
        _sanitization_count(note, "malformed_encrypted_blocks"),
    )
    _record_counter(
        "unreplayable_images_stripped",
        _sanitization_count(note, "local_image_items"),
    )


def _is_transient_upstream(code: int, err_body: bytes) -> str:
    """Classify an upstream failure's retry disposition.

    Returns one of:
      "full"    — genuine transient (429/5xx or a classified upstream empty
                  response); retry up to the full budget.
      "once"    — a transient validation failure (``invalid_payload`` or a
                  schema mismatch). The request body is preserved and retried
                  once after a bounded delay.
      "full"    — an explicit upstream Responses ``response_failed`` execution
                  error. HTTP 400 proves that this request was not accepted as a
                  response; it can use the ordinary bounded retry budget.
      ""        — not retryable (encrypted-content complaint or other genuine 4xx).
    """
    if code in (429, 500, 502, 503, 504, 524):
        return "full"
    if code == 477:
        try:
            payload = json.loads(err_body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        # DMX uses non-standard HTTP 477 when its selected upstream returns no
        # output. It is not a client validation failure: the same preserved
        # request may succeed when retried, so treat only the explicit
        # ``empty_response`` contract as a bounded transient. Other unknown
        # 477 responses remain visible to the caller unchanged.
        error = payload.get("error") if isinstance(payload, dict) else None
        if (
            isinstance(error, dict)
            and error.get("type") == "dmx_api_error"
            and error.get("code") == "empty_response"
        ):
            return "full"
        return ""
    if code == 400:
        try:
            low = err_body.lower()
        except Exception:
            return ""
        if b"invalid_encrypted_content" in low or b"could not be verified" in low:
            return ""
        # Some upstream gateways collapse a failed Responses execution into
        # HTTP 400 even when the request has passed validation. The exact
        # ``response_failed`` payload was observed on 2026-07-14. HTTP 400 means
        # the request was rejected before a response was accepted, so it may use
        # the same bounded retry budget as other upstream execution failures.
        if b"response_failed" in low or b"openai responses stream failed" in low:
            return "full"
        if b"invalid_payload" in low or b"does not match the expected schema" in low:
            return "once"
    return ""


def _dmx_empty_response_exhausted(attempts: int) -> bytes:
    """Return a stable local 503 after DMX exhausts empty-response retries.

    HTTP 477 is an upstream-specific extension. Once the proxy has classified
    it and exhausted its bounded recovery budget, preserve the retryable
    semantics with standard HTTP 503 rather than exposing an unknown status to
    the client. The response contains no upstream payload or request content.
    """
    return json.dumps({
        "error": {
            "message": "DMX upstream returned empty responses after bounded retries",
            "type": "upstream_unavailable",
            "code": "dmx_empty_response_exhausted",
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()


def _send_empty_response_exhausted(handler, attempts: int) -> None:
    """Emit the bounded classified-empty-response failure as standard HTTP JSON.

    Unlike other bounded recoveries, this path always answers with a standard
    HTTP 503 even for a streaming request. The one dedicated fallback attempt
    (if any) never reached upstream SSE bytes, so there is no in-progress
    downstream stream that needs a synthetic terminal SSE event; sending a
    plain JSON error here keeps this failure mode uniform and easy for a
    client to retry regardless of ``stream``.
    """
    msg = _dmx_empty_response_exhausted(attempts)
    handler.send_response(503)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Retry-After", "3")
    handler.send_header("Content-Length", str(len(msg)))
    handler.end_headers()
    handler.wfile.write(msg)


def _empty_response_policy_fingerprint(raw: bytes) -> str:
    """Bind a cooldown key to both the compat policy and the exact request bytes.

    Two requests that differ only in top-level provider state (for example a
    different ``previous_response_id``) must cool down independently even when
    the fallback bodies they would build turn out identical, so the key is
    derived from the caller's own bytes rather than from the projected
    fallback. Folding in the policy version means a future change to the
    projection rules cannot collide with an older cached cooldown entry.
    """
    return hashlib.sha256(EMPTY_RESPONSE_COMPAT_POLICY_VERSION.encode("utf-8") + raw).hexdigest()


def _purge_expired_empty_response_failures_locked(now: float) -> None:
    """Drop every cooldown entry whose TTL has elapsed. Caller holds the lock.

    This makes the TTL an actual eviction, not merely an ``is it still within
    its window`` read-time check: an expired entry is removed from the dict
    itself, so it neither lingers in memory nor counts against the fixed
    ``EMPTY_RESPONSE_COOLDOWN_CAPACITY`` for unrelated later keys.
    """
    expired = [
        recorded_key
        for recorded_key, recorded_at in _EMPTY_RESPONSE_FAILURES.items()
        if recorded_at + EMPTY_RESPONSE_COOLDOWN_SECONDS <= now
    ]
    for recorded_key in expired:
        del _EMPTY_RESPONSE_FAILURES[recorded_key]


def _remember_empty_response_failure(key: str, now: float | None = None) -> None:
    """Record one classified empty-response exhaustion for bounded local cooldown.

    Uses ``time.monotonic()`` by default so the cooldown cannot be perturbed by
    a wall-clock adjustment. Expired entries are purged before insertion, then
    the cache is capped at ``EMPTY_RESPONSE_COOLDOWN_CAPACITY`` entries; when
    still full after that purge, the single oldest-recorded entry is evicted so
    an unbounded stream of distinct requests can never grow this beyond its
    fixed capacity.
    """
    moment = time.monotonic() if now is None else now
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _purge_expired_empty_response_failures_locked(moment)
        _EMPTY_RESPONSE_FAILURES[key] = moment
        while len(_EMPTY_RESPONSE_FAILURES) > EMPTY_RESPONSE_COOLDOWN_CAPACITY:
            oldest_key = min(_EMPTY_RESPONSE_FAILURES, key=_EMPTY_RESPONSE_FAILURES.get)
            del _EMPTY_RESPONSE_FAILURES[oldest_key]


def _empty_response_cooldown_remaining(key: str, now: float | None = None) -> float:
    """Return the remaining cooldown seconds for ``key``, or ``0`` when clear.

    Uses ``time.monotonic()`` by default, matching ``_remember_empty_response_failure``.
    Purges expired entries before the read so a stale entry can never report a
    false-positive remaining cooldown, and never exposes any recorded key.
    """
    moment = time.monotonic() if now is None else now
    with _EMPTY_RESPONSE_FAILURES_LOCK:
        _purge_expired_empty_response_failures_locked(moment)
        recorded = _EMPTY_RESPONSE_FAILURES.get(key)
    if recorded is None:
        return 0
    remaining = recorded + EMPTY_RESPONSE_COOLDOWN_SECONDS - moment
    return remaining if remaining > 0 else 0


_EMPTY_RESPONSE_VALID_ROLES = frozenset(("user", "assistant", "developer", "system"))
# Fixed, closed enum: any phase this proxy has not itself observed and vetted
# is rejected rather than passed through, since an unknown phase value cannot
# be shown to be safe to replay.
_EMPTY_RESPONSE_VALID_PHASES = frozenset(("commentary", "final_answer"))
_EMPTY_RESPONSE_MESSAGE_FIELDS = frozenset(("type", "id", "status", "role", "content", "phase"))
_EMPTY_RESPONSE_AGENT_MESSAGE_FIELDS = frozenset(
    ("type", "id", "status", "author", "recipient", "phase", "content")
)
_EMPTY_RESPONSE_CALL_ARG_FIELD = {"function_call": "arguments", "custom_tool_call": "input"}
_EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT = {
    "function_call_output": "function_call",
    "custom_tool_call_output": "custom_tool_call",
}
_EMPTY_RESPONSE_CALL_FIELDS = {
    call_type: frozenset(("type", "id", "status", "call_id", "name", arg_field, "namespace", "caller"))
    for call_type, arg_field in _EMPTY_RESPONSE_CALL_ARG_FIELD.items()
}
_EMPTY_RESPONSE_OUTPUT_FIELDS = frozenset(("type", "id", "status", "call_id", "output", "caller"))
_EMPTY_RESPONSE_REASONING_FIELDS = frozenset(("type", "id", "status", "encrypted_content", "summary", "content"))


def _is_empty_response_text_only(value) -> bool:
    """True for a plain string or a list of only well-formed ``input_text`` blocks.

    Each block must carry *exactly* ``type`` and ``text`` -- any additional
    block field is unrepresentable in this projection and rejects the block,
    rather than being silently dropped.
    """
    if isinstance(value, str):
        return True
    if isinstance(value, list):
        for block in value:
            if not isinstance(block, dict):
                return False
            if set(block.keys()) != {"type", "text"}:
                return False
            if block.get("type") != "input_text" or not isinstance(block.get("text"), str):
                return False
        return True
    return False


def _empty_response_valid_caller(caller) -> bool:
    """A caller marker must be omitted, ``{"type":"direct"}``, or a well-formed program caller.

    Only these two closed shapes can be shown to be losslessly representable:
    ``{"type": "direct"}`` with no other keys, or
    ``{"type": "program", "caller_id": <non-empty str>}`` with no other keys.
    Any other ``type`` value, a ``program`` caller missing or with an empty
    ``caller_id``, or any extra key is rejected rather than copied through
    unexamined.
    """
    if caller is None:
        return True
    if not isinstance(caller, dict):
        return False
    caller_type = caller.get("type")
    if caller_type == "direct":
        return set(caller.keys()) == {"type"}
    if caller_type == "program":
        return (
            set(caller.keys()) == {"type", "caller_id"}
            and isinstance(caller.get("caller_id"), str)
            and caller["caller_id"] != ""
        )
    return False


def _empty_response_valid_namespace(namespace) -> bool:
    """A namespace marker must be omitted or a non-empty string."""
    return namespace is None or (isinstance(namespace, str) and namespace != "")


def _build_empty_response_fallback(raw: bytes, budget: int | None = None):
    """Build the single bounded, text-only fallback for a classified 477.

    This is a fail-closed projector, not a general history rewriter: every
    item type is matched against an explicit allow-list of semantic fields --
    never copied through with an exclude-list -- so an unknown or additional
    field on an otherwise-known item rejects the whole fallback instead of
    being silently forwarded or silently dropped. The same applies to any
    unknown item, invalid role/phase, malformed call/output/caller/namespace,
    non-text content, orphaned/mismatched/duplicate tool output, or otherwise
    unrepresentable shape: the caller stays free to expose the original
    upstream response rather than receive a guessed projection. Only known
    provider-owned state is removed: top-level ``previous_response_id`` /
    ``conversation`` / ``prompt_cache_key``, the ``reasoning.encrypted_content``
    include hint, and each known item's own ``id`` and ``status``. A string
    ``input`` (rather than a list of items) is preserved losslessly since it
    carries no items to project. A ``reasoning`` item maps to a fixed opaque
    marker only when its own visible ``summary``/``content`` is empty -- a
    reasoning item that also carries visible summary or content text cannot
    be losslessly represented by the fixed marker and is rejected instead of
    silently discarding that text. An ``agent_message`` maps to a plain
    assistant message with a deterministic, JSON-escaped author/recipient
    header so that quoted or newline-bearing values can never break the fixed
    envelope; both keep their position in ``input``. Returns ``(raw, detail)``
    unchanged when no projection is needed at all, so a caller can retry the
    identical bytes exactly once. Returns ``(None, detail)`` when the request
    cannot be safely projected, with ``detail["status"] == "rejected"``.
    """
    if budget is None:
        budget = EMPTY_RESPONSE_FALLBACK_BUDGET
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        return None, {"status": "rejected", "reason": "invalid_budget"}
    try:
        payload = json.loads(raw)
    except Exception:
        return None, {"status": "rejected", "reason": "invalid_json"}
    if not isinstance(payload, dict):
        return None, {"status": "rejected", "reason": "not_object"}

    original_input = payload.get("input", [])
    if isinstance(original_input, str):
        original_items = None
    elif isinstance(original_input, list):
        original_items = original_input
    else:
        return None, {"status": "rejected", "reason": "invalid_input"}

    changed = False
    new_payload = dict(payload)
    for field in ("previous_response_id", "conversation", "prompt_cache_key"):
        if field in new_payload:
            del new_payload[field]
            changed = True

    if "include" in new_payload:
        include = new_payload["include"]
        if not isinstance(include, list) or any(not isinstance(value, str) for value in include):
            return None, {"status": "rejected", "reason": "invalid_include"}
        trimmed_include = [value for value in include if value != "reasoning.encrypted_content"]
        if len(trimmed_include) != len(include):
            new_payload["include"] = trimmed_include
            changed = True

    if original_items is None:
        # A string ``input`` carries no items to project; only the top-level
        # provider bindings stripped above could have required any change.
        projected_input = original_input
    else:
        calls: dict[str, str] = {}
        outputs_seen: set[str] = set()
        projected_items = []

        for item in original_items:
            if not isinstance(item, dict):
                return None, {"status": "rejected", "reason": "invalid_item"}
            item_type = item.get("type")

            if item_type == "reasoning":
                if set(item.keys()) - _EMPTY_RESPONSE_REASONING_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_reasoning_field"}
                if item.get("summary") not in (None, []):
                    return None, {"status": "rejected", "reason": "malformed_reasoning"}
                if item.get("content") not in (None, []):
                    return None, {"status": "rejected", "reason": "malformed_reasoning"}
                projected_items.append({
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [
                        {"type": "input_text", "text": EMPTY_RESPONSE_OPAQUE_REASONING_MARKER},
                    ],
                })
                changed = True
                continue

            if item_type == "agent_message":
                if set(item.keys()) - _EMPTY_RESPONSE_AGENT_MESSAGE_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_agent_message_field"}
                author = item.get("author")
                recipient = item.get("recipient")
                content = item.get("content")
                phase = item.get("phase", "commentary")
                if not isinstance(author, str) or author == "":
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                if not isinstance(recipient, str) or recipient == "":
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                if phase not in _EMPTY_RESPONSE_VALID_PHASES:
                    return None, {"status": "rejected", "reason": "invalid_phase"}
                if not isinstance(content, list):
                    return None, {"status": "rejected", "reason": "malformed_agent_message"}
                if not _is_empty_response_text_only(content):
                    return None, {"status": "rejected", "reason": "non_text_agent_content"}
                header_text = json.dumps(
                    {"type": "agent_message", "author": author, "recipient": recipient},
                    ensure_ascii=False, separators=(",", ":"),
                )
                header = {"type": "input_text", "text": header_text}
                projected_items.append({
                    "type": "message",
                    "role": "assistant",
                    "phase": phase,
                    "content": [header, *content],
                })
                changed = True
                continue

            if item_type == "message":
                if set(item.keys()) - _EMPTY_RESPONSE_MESSAGE_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_message_field"}
                role = item.get("role")
                if role not in _EMPTY_RESPONSE_VALID_ROLES:
                    return None, {"status": "rejected", "reason": "invalid_role"}
                phase = item.get("phase")
                if phase is not None and (role != "assistant" or phase not in _EMPTY_RESPONSE_VALID_PHASES):
                    return None, {"status": "rejected", "reason": "invalid_phase"}
                content = item.get("content")
                if not _is_empty_response_text_only(content):
                    return None, {"status": "rejected", "reason": "non_text_message_content"}
                kept = {"type": "message", "role": role, "content": content}
                if phase is not None:
                    kept["phase"] = phase
                if kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            if item_type in _EMPTY_RESPONSE_CALL_ARG_FIELD:
                if set(item.keys()) - _EMPTY_RESPONSE_CALL_FIELDS[item_type]:
                    return None, {"status": "rejected", "reason": "unknown_call_field"}
                call_id = item.get("call_id")
                name = item.get("name")
                arg_field = _EMPTY_RESPONSE_CALL_ARG_FIELD[item_type]
                arguments = item.get(arg_field)
                namespace = item.get("namespace")
                caller = item.get("caller")
                if not isinstance(call_id, str) or call_id == "" or call_id in calls:
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not isinstance(name, str) or name == "":
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not isinstance(arguments, str):
                    return None, {"status": "rejected", "reason": "malformed_call"}
                if not _empty_response_valid_namespace(namespace):
                    return None, {"status": "rejected", "reason": "malformed_namespace"}
                if not _empty_response_valid_caller(caller):
                    return None, {"status": "rejected", "reason": "malformed_caller"}
                calls[call_id] = item_type
                kept = {"type": item_type, "call_id": call_id, "name": name, arg_field: arguments}
                if namespace is not None:
                    kept["namespace"] = namespace
                if caller is not None:
                    kept["caller"] = caller
                if kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            if item_type in _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT:
                if set(item.keys()) - _EMPTY_RESPONSE_OUTPUT_FIELDS:
                    return None, {"status": "rejected", "reason": "unknown_output_field"}
                call_id = item.get("call_id")
                output = item.get("output")
                caller = item.get("caller")
                if not isinstance(call_id, str) or call_id == "" or call_id not in calls:
                    return None, {"status": "rejected", "reason": "orphan_output"}
                if calls[call_id] != _EMPTY_RESPONSE_CALL_TYPE_FOR_OUTPUT[item_type]:
                    return None, {"status": "rejected", "reason": "mismatched_output"}
                if call_id in outputs_seen:
                    return None, {"status": "rejected", "reason": "duplicate_output"}
                if not _is_empty_response_text_only(output):
                    return None, {"status": "rejected", "reason": "non_text_output"}
                if not _empty_response_valid_caller(caller):
                    return None, {"status": "rejected", "reason": "malformed_caller"}
                outputs_seen.add(call_id)
                kept = {"type": item_type, "call_id": call_id, "output": output}
                if caller is not None:
                    kept["caller"] = caller
                if kept != item:
                    changed = True
                projected_items.append(kept)
                continue

            return None, {"status": "rejected", "reason": "unknown_item_type"}

        projected_input = projected_items

    if not changed:
        return raw, {"projected": False, "status": "accepted"}

    new_payload["input"] = projected_input
    try:
        fallback = json.dumps(new_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except Exception:
        return None, {"status": "rejected", "reason": "serialize_failed"}

    if len(fallback) > budget:
        return None, {"status": "rejected", "reason": "budget_exceeded"}

    return fallback, {
        "projected": True,
        "status": "accepted",
        "original_bytes": len(raw),
        "fallback_bytes": len(fallback),
    }


def send_terminal_failure(handler, request_body: bytes, *, code: str, message: str, attempts: int) -> str:
    """Emit a bounded terminal failure in the response mode selected by the caller.

    A streaming Responses request receives a terminal SSE error instead of an
    HTTP JSON error after stream selection, preventing clients from retaining a
    permanently in-progress turn.  The synthetic event is secret-free and never
    exposes upstream bytes or request contents.
    """
    try:
        decoded = json.loads(request_body)
        streaming = isinstance(decoded, dict) and decoded.get("stream") is True
    except (TypeError, ValueError, json.JSONDecodeError):
        streaming = False
    payload = json.dumps({
        "error": {
            "message": message,
            "type": "upstream_unavailable",
            "code": code,
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()
    if streaming:
        event = b"event: error\n" + b"data: " + payload + b"\n\n"
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Content-Length", str(len(event)))
        handler.end_headers()
        handler.wfile.write(event)
        return "sse_error"
    handler.send_response(503)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Retry-After", "3")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)
    return "json_error"


def _stream_pre_content_exhausted(attempts: int) -> bytes:
    """Return a retryable local failure when an SSE stream never reaches content."""
    return json.dumps({
        "error": {
            "message": "DMX upstream stream ended before content after bounded reconnects; retry the turn",
            "type": "upstream_unavailable",
            "code": "stream_pre_content_exhausted",
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()


def _response_failed_recovery_exhausted(attempts: int) -> bytes:
    """Return a retryable local failure after bounded response recovery.

    An upstream ``response_failed`` is an execution failure, not a client-side
    schema rejection.  Returning the original HTTP 400 teaches Codex to treat
    the failed turn as an invalid request and prevents its own retry loop from
    taking over.  Once the proxy has exhausted its deliberately bounded,
    semantics-preserving recovery options, expose a standard retryable status
    instead.  Do not include the upstream body or request content.
    """
    return json.dumps({
        "error": {
            "message": "DMX upstream rejected bounded Responses recovery; retry the turn",
            "type": "upstream_unavailable",
            "code": "response_failed_recovery_exhausted",
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()


def _strip_reasoning_encrypted_content_from_sse_event(obj):
    """Remove only reasoning replay state from a streamed provider response.

    The Responses schema uses ``encrypted_content`` in more than one typed item.
    It is safe to remove from a ``reasoning`` output item because the next request
    drops that top-level item. It is *not* safe to remove from a typed
    ``encrypted_content`` block inside an agent message: that field is required
    when the block is replayed. Traverse the event but mutate only reasoning items.
    """
    removed = 0
    if isinstance(obj, dict):
        if obj.get("type") == "reasoning" and "encrypted_content" in obj:
            del obj["encrypted_content"]
            removed += 1
        for value in obj.values():
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    elif isinstance(obj, list):
        for value in obj:
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    return removed


def _drop_malformed_encrypted_content_blocks(obj):
    """Drop only legacy typed blocks missing their required payload.

    Earlier proxy builds recursively erased encrypted payloads from streamed agent
    messages, leaving ``{"type": "encrypted_content"}`` in local history. The
    upstream rightfully rejects that invalid schema. Repair the replay at the
    network boundary by removing just blocks *without* an ``encrypted_content``
    field; valid typed blocks remain byte-for-byte represented in the JSON object.
    """
    dropped = 0
    if isinstance(obj, dict):
        for field in ("content", "output"):
            items = obj.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "encrypted_content"
                    and "encrypted_content" not in item
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                obj[field] = kept
        for value in obj.values():
            dropped += _drop_malformed_encrypted_content_blocks(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _drop_malformed_encrypted_content_blocks(value)
    return dropped


def _strip_replayed_reasoning_items(payload):
    """Remove replayable reasoning items without touching typed message content.

    ``encrypted_content`` is overloaded in the Responses schema. It is stale
    provider-owned replay state on a top-level ``reasoning`` input item, but it is
    a *required payload field* for ``{"type": "encrypted_content"}`` blocks in
    ``agent_message.content``. A generic recursive deletion destroys the latter
    and turns a valid agent message into an invalid one. Drop the whole top-level
    reasoning item instead; retain every other encrypted-content block verbatim.
    """
    dropped_items = 0
    preserved_agent_blocks = 0
    inp = payload.get("input")
    if not isinstance(inp, list):
        return dropped_items, preserved_agent_blocks

    kept = []
    for item in inp:
        if isinstance(item, dict) and item.get("type") == "reasoning":
            dropped_items += 1
            continue
        if isinstance(item, dict) and item.get("type") == "agent_message":
            content = item.get("content")
            if isinstance(content, list):
                preserved_agent_blocks += sum(
                    1
                    for block in content
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "encrypted_content"
                        and "encrypted_content" in block
                    )
                )
        kept.append(item)
    if dropped_items:
        payload["input"] = kept
    return dropped_items, preserved_agent_blocks


_TOOL_CALL_TYPES = frozenset(("custom_tool_call", "function_call"))
_TOOL_OUTPUT_TYPES = frozenset(("custom_tool_call_output", "function_call_output"))


def _tool_pair_boundary_is_safe(items, start):
    """True if a retained input suffix has no orphaned tool-call relationship.

    Responses inputs encode custom/function tool calls and their outputs as
    separate adjacent history items. A raw byte or item-count suffix can retain an
    output whose call was discarded, which the upstream correctly rejects. We only
    remove a contiguous oldest prefix, and admit a suffix when every retained
    call/output pair is internally complete. A call with no output is allowed: it
    may be the live continuation of a pending call, but a retained output without
    its call is never valid.
    """
    calls = set()
    for item in items[start:]:
        if not isinstance(item, dict):
            continue
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        item_type = item.get("type")
        if item_type in _TOOL_CALL_TYPES:
            calls.add(call_id)
        elif item_type in _TOOL_OUTPUT_TYPES:
            # A Responses replay output is meaningful only after its matching
            # call. Checking ordering, not just set membership, also rules out a
            # malformed retained suffix that happens to repeat a call id later.
            if call_id not in calls:
                return False
    return True


def _compact_response_failed_request(raw: bytes, budget: int | None = None):
    """Build one pair-safe compact fallback after an explicit upstream failure.

    This is intentionally not a general context-window implementation. It runs
    only in the HTTP-400 ``response_failed`` branch, keeps the newest contiguous
    input suffix, and removes *only* the oldest prefix. The compact copy removes
    ``prompt_cache_key`` because it refers to the full historical prompt. The
    original request bytes remain untouched for the primary attempt and for every
    other error type.

    ``budget`` is an internal retry-stage ceiling. Each successive stage must be
    no larger than half the preceding request, preventing no-op fallbacks such as
    a one-item trim of an already sub-512-KiB failed replay.

    Return ``(compact_bytes, metrics)`` only when a pair-valid suffix including
    the final input item fits the requested full-request budget. Otherwise return
    ``(None, None)`` and let the original upstream response pass through.
    """
    if budget is None:
        budget = RESPONSE_FAILED_COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    # A fallback must reduce the request materially even when it is already below
    # the normal ceiling. Without this gate an explicit response_failed at 485 KiB
    # would only drop one ancient item and reproduce the same upstream failure.
    budget = min(budget, max(1, len(raw) // RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR))
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or len(original_items) < 2:
        return None, None

    # The fallback must retain the latest user context, even when later tool
    # plumbing consumes most of the budget. If it cannot, the safe answer is no
    # fallback rather than silently changing the user's current request.
    latest_user_index = max(
        (
            index
            for index, item in enumerate(original_items)
            if (
                isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    # Begin with the oldest safe boundary that meets the full JSON-byte budget.
    # Moving the boundary right removes more *oldest* state and is the only allowed
    # recovery action. A copied dict is used so the original payload object/bytes
    # cannot be mutated by the failed fallback construction.
    smallest = None
    for start in range(1, latest_user_index + 1):
        if not _tool_pair_boundary_is_safe(original_items, start):
            continue
        candidate = dict(payload)
        candidate["input"] = original_items[start:]
        candidate.pop("prompt_cache_key", None)
        try:
            compact = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
        except Exception:
            return None, None
        metrics = {
                "original_bytes": len(raw),
                "budget_bytes": budget,
                "compact_bytes": len(compact),
                "removed_inputs": start,
                "retained_inputs": len(original_items) - start,
                "prompt_cache_key_removed": "prompt_cache_key" in payload,
        }
        if len(compact) <= budget:
            return compact, metrics
        # A trailing sequence of complete tool outputs can itself exceed the
        # desired byte target. It is still safer and more useful to send the
        # smallest pair-valid suffix than to repeat a known rejected request.
        # We retain the candidate only after confirming it is an actual reduction.
        if len(compact) < len(raw) and (smallest is None or len(compact) < len(smallest[0])):
            smallest = (compact, metrics)
    if smallest is not None:
        compact, metrics = smallest
        metrics["budget_met"] = False
        return compact, metrics
    return None, None


def _recover_response_failed_dialogue(raw: bytes, budget: int | None = None):
    """Build the final, text-only recovery request for ``response_failed``.

    This is intentionally narrower than general context compaction.  It runs
    only after the pair-safe suffix fallback has itself been explicitly rejected
    by the upstream.  It preserves the newest developer/system instruction and
    the latest user request while omitting replayed assistant and tool state.
    The stored Codex history is never changed; this is a one-request network
    fallback for an upstream that rejected both the original and pair-safe
    replay forms.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or not original_items:
        return None, None

    latest_user_index = max(
        (
            index
            for index, item in enumerate(original_items)
            if (
                isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    # Keep only the most recent instruction anchor before the active user
    # request.  Older instructions and all replay/tool state were already
    # rejected by the upstream; retaining them would turn this into an
    # unbounded history rewrite rather than a bounded recovery attempt.
    start = latest_user_index
    for index in range(latest_user_index, -1, -1):
        item = original_items[index]
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") in ("developer", "system")
        ):
            start = index
            break

    # This final fallback is intentionally a two-message envelope, not a
    # shortened transcript.  Keeping intervening user messages would recreate
    # a history replay by another name and would make its semantics harder to
    # reason about.  The instruction anchor is optional because a valid
    # Responses request can consist of the user's current request alone.
    dialogue = []
    if start != latest_user_index:
        dialogue.append(original_items[start])
    dialogue.append(original_items[latest_user_index])

    candidate = dict(payload)
    candidate["input"] = dialogue
    candidate.pop("prompt_cache_key", None)
    try:
        recovery = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
    except Exception:
        return None, None

    if budget is None:
        budget = RESPONSE_FAILED_COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    budget = min(budget, max(1, len(raw) // RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR))
    if len(recovery) > budget or len(recovery) >= len(raw):
        return None, None
    return recovery, {
        "original_bytes": len(raw),
        "recovery_bytes": len(recovery),
        "budget_bytes": budget,
        "retained_messages": len(dialogue),
        "dropped_input_items": len(original_items) - len(dialogue),
        "prompt_cache_key_removed": "prompt_cache_key" in payload,
    }

def _is_replayable_remote_image_url(value):
    """True only for URL schemes the third-party Responses endpoint accepts."""
    if not isinstance(value, str) or not value:
        return False
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        # Accessing .port validates an explicit port and raises ValueError when
        # it is non-numeric or outside the valid TCP range.
        _ = parsed.port
    except ValueError:
        return False
    return True


def _strip_unreplayable_images(obj):
    """Drop historical input images that cannot be replayed to the provider.

    Codex preserves local tool-output images in history. Third-party Responses
    endpoints validate image_url as a remotely fetchable URL, so local paths and
    data URLs reject the whole next turn. Keep only http(s) images and retain all
    neighboring text/tool output.
    """
    dropped = 0
    if isinstance(obj, dict):
        for field in ("output", "content"):
            items = obj.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "input_image"
                    and not _is_replayable_remote_image_url(item.get("image_url"))
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                obj[field] = kept
        for value in obj.values():
            dropped += _strip_unreplayable_images(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _strip_unreplayable_images(value)
    return dropped


def sanitize_responses_body(raw: bytes) -> tuple[bytes, str]:
    """Return (possibly-rewritten body, note). Fail-open: on any error return raw."""
    try:
        payload = json.loads(raw)
    except Exception as exc:  # not JSON we understand → leave untouched
        return raw, f"passthrough (non-json: {exc.__class__.__name__})"

    if not isinstance(payload, dict):
        return raw, "passthrough (json not object)"

    # (a) Drop replayed top-level reasoning items. Do not recursively delete
    # encrypted_content: agent_message encrypted-content blocks require it.
    dropped_items, preserved_agent_blocks = _strip_replayed_reasoning_items(payload)

    # (b) Repair only malformed typed encrypted-content blocks created by old
    # local proxy versions. Valid agent-message blocks remain intact.
    dropped_malformed_encrypted_blocks = _drop_malformed_encrypted_content_blocks(payload)

    # (c) Drop local-path / data-URL image replay items that this third-party
    # endpoint rejects. Valid remote http(s) images stay intact.
    dropped_images = _strip_unreplayable_images(payload)

    # (d) Stop asking the API to return new replayed reasoning state.
    include = payload.get("include")
    include_trimmed = False
    if isinstance(include, list):
        new_inc = [x for x in include if x != "reasoning.encrypted_content"]
        if len(new_inc) != len(include):
            payload["include"] = new_inc
            include_trimmed = True

    if not (
        dropped_items
        or dropped_malformed_encrypted_blocks
        or dropped_images
        or include_trimmed
    ):
        return raw, "clean (nothing to strip)"

    try:
        new_raw = json.dumps(payload).encode("utf-8")
    except Exception as exc:
        return raw, f"passthrough (reserialize failed: {exc.__class__.__name__})"

    return new_raw, (
        f"stripped reasoning_items={dropped_items} "
        f"malformed_encrypted_blocks={dropped_malformed_encrypted_blocks} "
        f"local_image_items={dropped_images} "
        f"agent_message_encrypted={preserved_agent_blocks} "
        f"include_trimmed={include_trimmed}"
    )




def sanitize_sse_event(raw_event: bytes) -> tuple[bytes, int]:
    """Strip encrypted_content from one SSE event block; preserve SSE framing."""
    if b"encrypted_content" not in raw_event:
        return raw_event, 0
    out_lines = []
    removed_total = 0
    for line in raw_event.splitlines(keepends=True):
        if line.startswith(b"data: "):
            prefix = b"data: "
            suffix = b"\n" if line.endswith(b"\n") else b""
            data = line[len(prefix):]
            if suffix:
                data = data[:-1]
            if data.strip() == b"[DONE]":
                out_lines.append(line)
                continue
            try:
                obj = json.loads(data)
                removed = _strip_reasoning_encrypted_content_from_sse_event(obj)
                if removed:
                    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                    line = prefix + data + suffix
                    removed_total += removed
            except Exception:
                pass
        out_lines.append(line)
    return b"".join(out_lines), removed_total


def _read_one_sse_stream(handler, resp, path, request_id, on_first_write):
    """Relay a single upstream SSE stream to the client, stripping encrypted_content.

    Returns a dict describing how the stream ended:
      {"terminal": <event|None>, "events": int, "wrote_downstream": bool,
       "detail": "completed"|"failed"|"incomplete"|"timeout"|"incomplete_read"|"eof",
       "error": <exc|None>}

    Retry-safety strategy: the leading prelude events (response.created /
    response.in_progress) are IDENTICAL for every attempt and carry no content, so
    we BUFFER them and only flush once the stream proves healthy — i.e. once a
    substantive event (anything past the prelude) or a terminal event arrives. If
    the stream dies while still in the prelude, nothing was written downstream
    (`wrote_downstream` stays False) and the caller can safely reconnect without
    the client ever seeing a duplicate response.created. `on_first_write()` fires
    once, right before the first real downstream byte, so headers are sent lazily.
    """
    import http.client
    buf = b""
    stripped_events = 0
    stripped_keys = 0
    event_count = 0
    terminal_event = None
    upstream_incomplete = False
    upstream_timeout = False
    upstream_error = None
    wrote_downstream = False
    prelude = []          # buffered created/in_progress events, not yet flushed
    prelude_flushed = False

    _PRELUDE_TYPES = (b'"type":"response.created"', b'"type": "response.created"',
                      b'"type":"response.in_progress"', b'"type": "response.in_progress"')

    def _raw_write(data: bytes):
        nonlocal wrote_downstream
        if not wrote_downstream:
            on_first_write()
            wrote_downstream = True
        handler.wfile.write(b"%X\r\n%s\r\n" % (len(data), data))

    def _flush_prelude():
        nonlocal prelude_flushed
        if prelude_flushed:
            return
        for e in prelude:
            _raw_write(e)
        prelude.clear()
        prelude_flushed = True

    def _emit(data: bytes):
        # Retry-safety: while the prelude is unflushed we hold back the events that
        # are identical & content-free across attempts — created / in_progress — AND
        # a bare response.failed (dmxapi's transient turn-start failure). Holding
        # failed keeps `wrote_downstream` False so the caller can reconnect. Any
        # SUBSTANTIVE event (delta/output/completed/incomplete/etc.) proves the
        # stream healthy → flush the prelude in order, then write this event.
        if not prelude_flushed:
            held = (any(t in data for t in _PRELUDE_TYPES)
                    or b'"type":"response.failed"' in data
                    or b'"type": "response.failed"' in data)
            if held:
                prelude.append(data)
                return
        _flush_prelude()
        _raw_write(data)

    try:
        resp.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
    except Exception:
        try:
            resp.fp.raw._fp.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
        except Exception:
            pass

    while True:
        try:
            chunk = resp.read(8192)
        except http.client.IncompleteRead as ir:
            chunk = ir.partial
            upstream_incomplete = True
        except socket.timeout as exc:
            upstream_timeout = True
            upstream_error = exc
            break
        except TimeoutError as exc:
            upstream_timeout = True
            upstream_error = exc
            break
        except Exception as exc:
            upstream_error = exc
            break
        if not chunk:
            break
        buf += chunk
        while True:
            idx_lf = buf.find(b"\n\n")
            idx_crlf = buf.find(b"\r\n\r\n")
            candidates = [x for x in (idx_lf, idx_crlf) if x != -1]
            if not candidates:
                break
            idx = min(candidates)
            sep_len = 4 if idx == idx_crlf else 2
            event = buf[:idx + sep_len]
            buf = buf[idx + sep_len:]
            new_event, removed = sanitize_sse_event(event)
            if removed:
                stripped_events += 1
                stripped_keys += removed
            if b"event:" in new_event or b"data:" in new_event:
                event_count += 1
                if b'"type":"response.completed"' in new_event or b'"type": "response.completed"' in new_event:
                    terminal_event = "response.completed"
                elif b'"type":"response.failed"' in new_event or b'"type": "response.failed"' in new_event:
                    terminal_event = "response.failed"
                elif b'"type":"response.incomplete"' in new_event or b'"type": "response.incomplete"' in new_event:
                    terminal_event = "response.incomplete"
            _emit(new_event)
    if buf:
        new_event, removed = sanitize_sse_event(buf)
        if removed:
            stripped_events += 1
            stripped_keys += removed
        if b"event:" in new_event or b"data:" in new_event:
            event_count += 1
            if b'"type":"response.completed"' in new_event or b'"type": "response.completed"' in new_event:
                terminal_event = "response.completed"
            elif b'"type":"response.failed"' in new_event or b'"type": "response.failed"' in new_event:
                terminal_event = "response.failed"
            elif b'"type":"response.incomplete"' in new_event or b'"type": "response.incomplete"' in new_event:
                terminal_event = "response.incomplete"
        _emit(new_event)

    # A legitimate terminal (completed/incomplete) means the prelude belongs to the
    # client — flush it so a created→completed stream isn't dropped. A bare
    # response.failed is left unflushed while the caller retries. If every attempt
    # fails before content, the handler returns a retryable local 503 instead.
    if terminal_event in ("response.completed", "response.incomplete") and not prelude_flushed:
        _flush_prelude()

    if stripped_keys:
        _record_counter("encrypted_sse_keys_stripped", stripped_keys)
        _log(
            f"req={request_id} event=sse_sanitized encrypted_events={stripped_events} "
            f"encrypted_keys={stripped_keys} path={_safe_request_path(path)}"
        )

    detail = (terminal_event.split(".")[-1] if terminal_event
              else ("timeout" if upstream_timeout
                    else ("incomplete_read" if upstream_incomplete else "eof")))
    return {
        "terminal": terminal_event,
        "events": event_count,
        "wrote_downstream": wrote_downstream,
        "detail": detail,
        "error": upstream_error,
    }


def stream_sanitized_sse(handler, resp, path, request_id, reopen=None, send_headers=None):
    """Stream upstream SSE to the client, with reconnect-on-premature-EOF.

    Codex treats an SSE EOF before a terminal Responses event as:

        stream disconnected before completion: stream closed before response.completed

    Root cause is dmxapi tearing the stream at turn start (observed: ~82% of these
    end at events<=4 with zero substantive content). Since nothing has been written
    downstream yet in that window, we can transparently re-issue the identical
    upstream request and start the client stream fresh — Codex only ever sees one
    clean 200 stream. Once any downstream byte is written we can no longer retry
    (headers/events already sent), so we relay whatever we get and stop.

    `send_headers()` sends the HTTP 200 + chunked headers exactly once (lazy, so a
    dead-on-arrival stream stays retryable). `reopen()` returns a fresh upstream
    `resp` for the identical request, or None if it failed.
    """
    headers_sent = {"done": False}

    def _on_first_write():
        if send_headers is not None and not headers_sent["done"]:
            send_headers()
            headers_sent["done"] = True

    # Retry budget applies only to the pre-first-byte window (safe: nothing sent
    # to the client yet). dmxapi tears streams intermittently at turn start and the
    # outage can last ~15-30s (observed req#63 02:31:45→02:32:00 span). Give the
    # reconnect enough attempts + escalating backoff to ride across a short upstream
    # outage instead of giving up after ~4s. This does NOT fix the upstream flakiness
    # (that's dmxapi service quality), only maximizes local recovery.
    max_stream_attempts = 6 if reopen is not None else 1
    stream_backoffs = [1.0, 2.0, 4.0, 6.0, 8.0]

    current = resp
    result = None
    for attempt in range(max_stream_attempts):
        result = _read_one_sse_stream(handler, current, path, request_id, _on_first_write)
        # Stop if the client has already received bytes (can't un-send), or the
        # stream ended in a way that's legitimate to relay: response.completed /
        # response.incomplete. A bare response.failed with ZERO downstream bytes
        # written is dmxapi's transient turn-start failure (99% of observed
        # failures are events<=3, zero content) — since the prelude is still
        # buffered and unseen by the client, it's as safe to retry as a raw EOF.
        committed = result["wrote_downstream"]
        term = result["terminal"]
        clean_end = term in ("response.completed", "response.incomplete")
        retryable = (not committed) and (term is None or term == "response.failed")
        if committed or clean_end or not retryable:
            break
        # Premature/failed end with zero client bytes written → safe to retry fresh.
        if attempt < max_stream_attempts - 1 and reopen is not None:
            _record_counter("streams_pre_content_reconnect_attempts")
            why = term if term else result["detail"]
            _log(
                f"req={request_id} event=sse_pre_content_reconnect reason={why} "
                f"events={result['events']} attempt={attempt + 1}/{max_stream_attempts - 1} "
                f"path={_safe_request_path(path)}"
            )
            time.sleep(stream_backoffs[min(attempt, len(stream_backoffs) - 1)])
            try:
                current = reopen()
            except Exception as exc:
                _log(
                    f"req={request_id} event=sse_reconnect_failed "
                    f"exception={_safe_exception_label(exc)} path={_safe_request_path(path)}"
                )
                current = None
            if current is None:
                break
            continue
        break

    # Nothing has been committed downstream when every attempt ends in the prelude.
    # Do not fabricate an empty HTTP 200: Codex correctly reports that as a broken
    # stream. Return control to the handler so it can send a retryable 503 instead.
    pre_content_exhausted = not headers_sent["done"]
    if headers_sent["done"]:
        handler.wfile.write(b"0\r\n\r\n")

    if result and result["terminal"] == "response.completed":
        _record_counter("streams_completed")
        _record_counter("responses_completed")
    elif result and result["terminal"] == "response.incomplete":
        _record_counter("streams_incomplete")
        _record_failure("stream_response_incomplete")
    else:
        _record_counter("streams_failed")
        detail = result["detail"] if result else "eof"
        if pre_content_exhausted:
            _record_counter("streams_pre_content_exhausted")
            _record_failure("stream_pre_content_exhausted")
        else:
            _record_failure(f"stream_{detail}")

    safe_path = _safe_request_path(path)
    if result and result["terminal"]:
        _log(
            f"req={request_id} event=sse_terminal terminal={result['terminal']} "
            f"events={result['events']} path={safe_path}"
        )
    else:
        detail = result["detail"] if result else "eof"
        err = result["error"] if result else None
        _log(
            f"req={request_id} event=sse_end_without_terminal detail={detail} "
            f"exception={_safe_exception_label(err) if err else 'none'} "
            f"events={result['events'] if result else 0} path={safe_path}"
        )
    return {
        "pre_content_exhausted": pre_content_exhausted,
        "attempts": attempt + 1,
        "result": result,
    }

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"dmx-responses-proxy/{release_version()}"

    def log_message(self, *a):  # silence default stderr spam; we log ourselves
        pass

    def _relay(self, method: str):
        request_id = _next_request_id()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        note = ""
        if body and method == "POST" and "/responses" in self.path:
            body, note = sanitize_responses_body(body)
            _record_sanitization(note)
            # Payloads may contain conversation data and credentials. Keep runtime
            # evidence aggregate-only: this proxy never persists request bodies.
            if len(body) >= 400_000:
                _log(
                    f"req={request_id} event=large_request bytes={len(body)} "
                    f"path={_safe_request_path(self.path)}"
                )

        url = UPSTREAM + self.path
        out_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in _HOP_BY_HOP
        }
        out_headers["Accept-Encoding"] = "identity"

        if note:
            _log(
                f"req={request_id} event=request_sanitized method={method} "
                f"path={_safe_request_path(self.path)} {note}"
            )


        # dmxapi intermittently returns 400 invalid_payload / 5xx / 429 for
        # provably-valid requests (~6% observed; identical replay succeeds).
        # Transparently retry the identical request a few times before giving up,
        # so this server-side flakiness never reaches Codex. An explicit 400
        # ``response_failed`` receives one *additional*, pair-safe compact
        # fallback: some large replay contexts are deterministically rejected.
        # Non-retryable 4xx are relayed immediately.
        is_responses = method == "POST" and "/responses" in self.path
        if is_responses:
            _record_counter("responses_received")
        max_attempts = 4 if is_responses else 1
        backoffs = [0.4, 1.0, 2.0]

        acquired = False
        global _ACTIVE_RESPONSES
        if is_responses:
            # Admission is guarded before semaphore acquisition.  Once drain is
            # enabled this closes the race against a lifecycle controller that
            # has observed zero active requests and is about to replace us.
            with _RESPONSE_GATE_LOCK:
                _expire_drain_locked()
                draining = _DRAINING
            if draining:
                _record_counter("responses_rejected_while_draining")
                _record_failure("draining")
                msg = json.dumps({
                    "error": {
                        "message": "DMX proxy is draining active Responses; retry the turn shortly",
                        "type": "server_busy",
                        "code": "proxy_draining",
                    }
                }, separators=(",", ":")).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "1")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                _log(f"req={request_id} event=responses_rejected_while_draining path={_safe_request_path(self.path)}")
                return
            acquired = _RESPONSES_SEM.acquire(timeout=RESPONSES_QUEUE_TIMEOUT)
            if not acquired:
                _record_counter("responses_local_queue_timeouts")
                _record_failure("local_queue_timeout")
                msg = json.dumps({
                    "error": {
                        "message": (
                            "dmx local proxy overloaded: timed out waiting for "
                            f"responses concurrency slot ({RESPONSES_MAX_CONCURRENCY})"
                        )
                    }
                }).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                _log(f"req={request_id} event=local_queue_timeout path={_safe_request_path(self.path)}")
                return
            # The drain latch may have changed while waiting for a concurrency
            # slot.  Re-check and increment under the same lock; this makes the
            # controller's observed drained snapshot an admission barrier.
            with _RESPONSE_GATE_LOCK:
                _expire_drain_locked()
                if _DRAINING:
                    _RESPONSES_SEM.release()
                    _record_counter("responses_rejected_while_draining")
                    _record_failure("draining")
                    msg = json.dumps({
                        "error": {
                            "message": "DMX proxy is draining active Responses; retry the turn shortly",
                            "type": "server_busy",
                            "code": "proxy_draining",
                        }
                    }, separators=(",", ":")).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Retry-After", "1")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    _log(f"req={request_id} event=responses_rejected_while_draining path={_safe_request_path(self.path)}")
                    return
                _ACTIVE_RESPONSES += 1
                active_now = _ACTIVE_RESPONSES
            _log(
                f"req={request_id} event=responses_slot_acquired "
                f"active={active_now}/{RESPONSES_MAX_CONCURRENCY} path={_safe_request_path(self.path)}"
            )

        try:
            resp = None
            last_err = None
            compact_response_failed_metrics = None
            used_response_failed_compaction = False
            response_failed_stages = 0
            max_response_failed_stages = RESPONSE_FAILED_MAX_STAGES if is_responses else 0
            # Reserved independently of ``max_response_failed_stages`` so the
            # dialogue-only recovery continuation still gets its one bounded
            # attempt even when ``DMX_RESPONSE_FAILED_MAX_STAGES=0``. It never
            # widens the ordinary retry ceiling below, which is computed from
            # ``max_attempts`` alone. The classified-477 fallback itself is
            # dispatched immediately, as an independent nested request (see
            # below), and deliberately does *not* add to this range.
            dialogue_slots = RESPONSE_FAILED_DIALOGUE_SLOTS if is_responses else 0
            attempt_body = body
            used_response_failed_dialogue_recovery = False
            dialogue_recovery_metrics = None
            # A classified 477 gets exactly one dedicated fallback slot per
            # request. Before spending any upstream attempt, honor a bounded
            # local cooldown recorded by a prior exhausted recovery for this
            # exact (policy-versioned) request, so a client that retries an
            # unrecoverable request in a tight loop cannot hammer upstream.
            if is_responses:
                cooldown_fingerprint = _empty_response_policy_fingerprint(body)
                cooldown_remaining = _empty_response_cooldown_remaining(cooldown_fingerprint)
                if cooldown_remaining > 0:
                    _record_counter("empty_response_cooldown_hits")
                    _record_failure("empty_response_cooldown_hit")
                    _send_empty_response_exhausted(self, 0)
                    _log(
                        f"req={request_id} event=empty_response_cooldown_hit "
                        f"remaining_seconds={cooldown_remaining:.1f} path={_safe_request_path(self.path)}"
                    )
                    return
            # Ordinary transient retries retain their previous bounded policy.
            # Explicit ``response_failed`` has its own staged, pair-safe
            # compaction path and must never loop the same bytes.
            for attempt in range(max_attempts + max_response_failed_stages + dialogue_slots):
                req = urllib.request.Request(url, data=attempt_body if attempt_body else None, method=method)
                for k, v in out_headers.items():
                    req.add_header(k, v)
                try:
                    resp = _urlopen(req, timeout=UPSTREAM_TIMEOUT)
                    # The dedicated classified-477 fallback is dispatched as its
                    # own immediate nested request below and never reaches this
                    # normal loop success path, so only the ordinary
                    # ``response_failed`` recovery branches need crediting here.
                    if used_response_failed_dialogue_recovery and dialogue_recovery_metrics:
                        _record_counter("response_failed_dialogue_recovery_accepted")
                        m = dialogue_recovery_metrics
                        _log(
                            f"req={request_id} event=response_failed_dialogue_recovery_accepted "
                            f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                            f"retained_messages={m['retained_messages']} "
                            f"dropped_input_items={m['dropped_input_items']} "
                            f"pair_safe_stages={response_failed_stages} "
                            f"path={_safe_request_path(self.path)}"
                        )
                    elif used_response_failed_compaction and compact_response_failed_metrics:
                        _record_counter("response_failed_compaction_accepted")
                        m = compact_response_failed_metrics
                        _log(
                            f"req={request_id} event=response_failed_compact_recovery_accepted "
                            f"bytes={m['original_bytes']}->{m['compact_bytes']} "
                            f"removed_inputs={m['removed_inputs']} "
                            f"retained_inputs={m['retained_inputs']} "
                            f"path={_safe_request_path(self.path)}"
                        )
                    break
                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read()
                        status_code = e.code
                        error_headers = e.headers
                    finally:
                        e.close()
                    disp = _is_transient_upstream(status_code, err_body)
                    classification = (
                        "response_failed" if status_code == 400 and disp == "full"
                        else ("empty_response" if status_code == 477 and disp == "full"
                              else (f"http_{status_code}_{disp}" if disp else f"http_{status_code}"))
                    )
                    _record_upstream_classification(classification)
                    # A deterministic replay failure cannot be fixed by retrying
                    # the same bytes. After the upstream has *explicitly* named
                    # ``response_failed``, make up to three strictly smaller,
                    # pair-safe suffix attempts. Each retains the latest user
                    # context and complete call/output pairs. This precedes
                    # ordinary retries so users do not wait through known-identical
                    # rejections.
                    if (
                        is_responses
                        and status_code == 400
                        and disp == "full"
                        and response_failed_stages < max_response_failed_stages
                    ):
                        compact, metrics = _compact_response_failed_request(attempt_body)
                        if compact is not None and metrics is not None and len(compact) < len(attempt_body):
                            _record_counter("response_failed_compaction_attempts")
                            response_failed_stages += 1
                            metrics["stage"] = response_failed_stages
                            compact_response_failed_metrics = metrics
                            used_response_failed_compaction = True
                            previous_bytes = len(attempt_body)
                            attempt_body = compact
                            _log(
                                f"req={request_id} event=response_failed_compact_recovery "
                                f"stage={response_failed_stages}/{max_response_failed_stages} "
                                f"bytes={previous_bytes}->{metrics['compact_bytes']} budget={metrics['budget_bytes']} "
                                f"removed_inputs={metrics['removed_inputs']} "
                                f"retained_inputs={metrics['retained_inputs']} "
                                f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                                f"budget_met={metrics.get('budget_met', True)} "
                                f"path={_safe_request_path(self.path)}"
                            )
                            continue
                    # If pair-safe suffixes have exhausted their useful range, make
                    # one final dialogue-only recovery attempt.  This is deliberately
                    # after pair-safe compaction: tool call/output replay is retained
                    # whenever it is accepted, and only an explicitly rejected replay
                    # can reach this bounded last resort.
                    if (
                        is_responses
                        and status_code == 400
                        and disp == "full"
                        and not used_response_failed_dialogue_recovery
                    ):
                        # Recover from the original request rather than the latest
                        # pair-safe suffix: a suffix may already have discarded the
                        # newest developer instruction to preserve a later tool pair.
                        # The dialogue-only recovery can safely retain that current
                        # instruction because it omits the rejected tool replay.
                        recovery, metrics = _recover_response_failed_dialogue(body)
                        if recovery is not None and metrics is not None and len(recovery) < len(attempt_body):
                            _record_counter("response_failed_dialogue_recovery_attempts")
                            used_response_failed_dialogue_recovery = True
                            dialogue_recovery_metrics = metrics
                            previous_bytes = len(attempt_body)
                            attempt_body = recovery
                            _log(
                                f"req={request_id} event=response_failed_dialogue_recovery "
                                f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
                                f"retained_messages={metrics['retained_messages']} "
                                f"dropped_input_items={metrics['dropped_input_items']} "
                                f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                                f"path={_safe_request_path(self.path)}"
                            )
                            continue
                    # ``invalid_payload`` is a classified upstream transient, not a
                    # body rewrite signal. Retry the exact sanitized bytes once with a
                    # bounded delay; 429 and 5xx retain the full retry budget.
                    # ``response_failed`` has already consumed this response in
                    # the staged compaction branch above. Never let it fall
                    # through to the ordinary transient retry policy.
                    if is_responses and status_code == 400 and disp == "full":
                        _record_counter("response_failed_recovery_exhausted")
                        _record_failure("response_failed_recovery_exhausted")
                        attempts = response_failed_stages + int(used_response_failed_dialogue_recovery) + 1
                        msg = _response_failed_recovery_exhausted(attempts)
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Retry-After", "3")
                        self.send_header("Content-Length", str(len(msg)))
                        self.end_headers()
                        self.wfile.write(msg)
                        _log(
                            f"req={request_id} event=response_failed_recovery_exhausted "
                            f"attempts={attempts} pair_safe_stages={response_failed_stages} "
                            f"dialogue_recovery={used_response_failed_dialogue_recovery} "
                            f"upstream_status={status_code} path={_safe_request_path(self.path)}"
                        )
                        return
                    retry_ceiling = 1 if disp == "once" else max_attempts - 1
                    transient_retries_used = attempt - response_failed_stages
                    if (
                        disp
                        and transient_retries_used < retry_ceiling
                        and not (status_code == 400 and disp == "full")
                        and not (status_code == 477 and disp == "full")
                    ):
                        delay = 3.0 if disp == "once" else backoffs[min(attempt, len(backoffs) - 1)]
                        _log(
                            f"req={request_id} event=upstream_retry status={status_code} "
                            f"disposition={disp} attempt={attempt + 1}/{retry_ceiling} "
                            f"delay_seconds={delay} path={_safe_request_path(self.path)}"
                        )
                        time.sleep(delay)
                        continue
                    if status_code == 477 and disp == "full":
                        # DMX's empty-response extension gets exactly one bounded,
                        # semantics-preserving fallback attempt instead of the
                        # ordinary identical-bytes retry budget. An unsafe
                        # projection rejects immediately without spending a
                        # second upstream attempt. A safe projection is
                        # dispatched right here as its own immediate, nested
                        # upstream request -- the same URL/method/headers/timeout
                        # -- independent of the outer attempt/iteration budget
                        # above, so it always fires exactly once even when this
                        # classified 477 arrives on the outer loop's very last
                        # iteration.
                        fingerprint = _empty_response_policy_fingerprint(body)
                        fallback, detail = _build_empty_response_fallback(body)
                        if fallback is None:
                            _record_counter("empty_response_fallback_rejected")
                            _record_counter("empty_response_recovery_exhausted")
                            _record_failure("empty_response_fallback_rejected")
                            _remember_empty_response_failure(fingerprint)
                            _send_empty_response_exhausted(self, 1)
                            _log(
                                f"req={request_id} event=empty_response_fallback_rejected "
                                f"reason={detail.get('reason', 'unknown')} attempts=1 "
                                f"path={_safe_request_path(self.path)}"
                            )
                            return
                        _record_counter("empty_response_fallback_attempts")
                        previous_bytes = len(attempt_body)
                        attempt_body = fallback
                        _log(
                            f"req={request_id} event=empty_response_fallback "
                            f"projected={detail.get('projected', False)} "
                            f"bytes={previous_bytes}->{len(fallback)} "
                            f"policy={EMPTY_RESPONSE_COMPAT_POLICY_VERSION} "
                            f"path={_safe_request_path(self.path)}"
                        )
                        fallback_req = urllib.request.Request(
                            url, data=attempt_body if attempt_body else None, method=method
                        )
                        for k, v in out_headers.items():
                            fallback_req.add_header(k, v)
                        try:
                            resp = _urlopen(fallback_req, timeout=UPSTREAM_TIMEOUT)
                        except urllib.error.HTTPError as fallback_error:
                            try:
                                fallback_error.read()
                                fallback_status = fallback_error.code
                            finally:
                                fallback_error.close()
                            _record_counter("empty_response_recovery_exhausted")
                            _record_failure("empty_response_recovery_exhausted")
                            _remember_empty_response_failure(fingerprint)
                            _send_empty_response_exhausted(self, 2)
                            _log(
                                f"req={request_id} event=empty_response_fallback_failed "
                                f"upstream_status={fallback_status} attempts=2 "
                                f"path={_safe_request_path(self.path)}"
                            )
                            return
                        except Exception as fallback_exc:
                            _record_counter("empty_response_recovery_exhausted")
                            _record_failure("empty_response_recovery_exhausted")
                            _remember_empty_response_failure(fingerprint)
                            _send_empty_response_exhausted(self, 2)
                            _log(
                                f"req={request_id} event=empty_response_fallback_failed "
                                f"exception={_safe_exception_label(fallback_exc)} attempts=2 "
                                f"path={_safe_request_path(self.path)}"
                            )
                            return
                        _record_counter("empty_response_fallback_accepted")
                        _log(
                            f"req={request_id} event=empty_response_fallback_accepted "
                            f"path={_safe_request_path(self.path)}"
                        )
                        break
                    self.send_response(status_code)
                    for k, v in error_headers.items():
                        if k.lower() not in _HOP_BY_HOP:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    _record_failure(classification)
                    _log(
                        f"req={request_id} event=upstream_http_terminal status={status_code} "
                        f"response_bytes={len(err_body)} attempts={attempt + 1} "
                        f"path={_safe_request_path(self.path)}"
                    )
                    return
                except Exception as e:
                    # The classified-477 fallback is dispatched as its own
                    # immediate nested request above, with its own HTTPError
                    # and transport-exception handling; a transport failure
                    # there never reaches this ordinary per-iteration handler.
                    last_err = e
                    if attempt < max_attempts - 1:
                        _log(
                            f"req={request_id} event=upstream_transport_retry "
                            f"attempt={attempt + 1} exception={_safe_exception_label(e)} "
                            f"path={_safe_request_path(self.path)}"
                        )
                        time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                        continue
                    msg = json.dumps({"error": {
                        "message": "DMX upstream transport failed after bounded retries; retry the turn",
                        "type": "upstream_unavailable",
                        "code": "upstream_transport_error",
                    }}, separators=(",", ":")).encode()
                    _record_failure("upstream_transport_error")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    _log(
                        f"req={request_id} event=upstream_transport_exhausted "
                        f"exception={_safe_exception_label(e)} path={_safe_request_path(self.path)}"
                    )
                    return

            if resp is None:
                msg = json.dumps({"error": {
                    "message": "DMX upstream transport failed after bounded retries; retry the turn",
                    "type": "upstream_unavailable",
                    "code": "upstream_transport_error",
                }}, separators=(",", ":")).encode()
                _record_failure("upstream_transport_error")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return

            # Stream the response back. Use chunked so we don't need a length up-front.
            ctype = resp.headers.get("Content-Type", "")
            is_sse = is_responses and "text/event-stream" in ctype.lower()

            def _send_stream_headers(r):
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in _HOP_BY_HOP or k.lower() == "content-length":
                        continue
                    self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

            if is_sse:
                # SSE: send headers lazily (on first downstream byte) so a stream
                # that dies before producing content can be transparently retried.
                def _reopen():
                    # Preserve the exact request that produced this upstream SSE.
                    # A recovered ``response_failed`` may be using a compact
                    # suffix; reopening the original oversized history would
                    # regress the repair during a pre-content reconnect.
                    req2 = urllib.request.Request(url, data=attempt_body if attempt_body else None, method=method)
                    for k, v in out_headers.items():
                        req2.add_header(k, v)
                    return _urlopen(req2, timeout=UPSTREAM_TIMEOUT)

                try:
                    stream_result = stream_sanitized_sse(
                        self, resp, self.path, request_id,
                        reopen=_reopen,
                        send_headers=lambda: _send_stream_headers(resp),
                    )
                    if stream_result["pre_content_exhausted"]:
                        msg = _stream_pre_content_exhausted(stream_result["attempts"])
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Retry-After", "3")
                        self.send_header("Content-Length", str(len(msg)))
                        self.end_headers()
                        self.wfile.write(msg)
                        _log(
                            f"req={request_id} event=sse_pre_content_exhausted "
                            f"attempts={stream_result['attempts']} path={_safe_request_path(self.path)}"
                        )
                except (BrokenPipeError, ConnectionResetError):
                    _log(f"req={request_id} event=downstream_client_closed path={_safe_request_path(self.path)}")
                except Exception as e:
                    _log(
                        f"req={request_id} event=stream_handler_exception "
                        f"exception={_safe_exception_label(e)} path={_safe_request_path(self.path)}"
                    )
            else:
                _send_stream_headers(resp)
                try:
                    import http.client
                    while True:
                        try:
                            chunk = resp.read(8192)
                        except http.client.IncompleteRead as ir:
                            chunk = ir.partial  # flush whatever arrived, then finish cleanly
                            if chunk:
                                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                            break
                        if not chunk:
                            break
                        self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.write(b"0\r\n\r\n")
                    if is_responses:
                        _record_counter("responses_completed")
                except (BrokenPipeError, ConnectionResetError):
                    # Client (Codex) closed the stream early — normal at turn end.
                    _log(f"req={request_id} event=downstream_client_closed path={_safe_request_path(self.path)}")
                except Exception as e:
                    _log(
                        f"req={request_id} event=stream_handler_exception "
                        f"exception={_safe_exception_label(e)} path={_safe_request_path(self.path)}"
                    )
        finally:
            if acquired:
                with _RESPONSE_GATE_LOCK:
                    _ACTIVE_RESPONSES -= 1
                    active_now = _ACTIVE_RESPONSES
                _RESPONSES_SEM.release()
                _log(
                    f"req={request_id} event=responses_slot_released "
                    f"active={active_now}/{RESPONSES_MAX_CONCURRENCY} path={_safe_request_path(self.path)}"
                )

    def _runtime_status(self):
        payload = json.dumps(runtime_status(), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _drain_control(self, enabled: bool):
        """Toggle local admission only for a loopback lifecycle controller."""
        if not _is_loopback_client(self.client_address[0]):
            self.send_error(403, "drain control is available only from loopback")
            return
        lease = self.headers.get("X-DMX-Drain-Lease-Seconds") if enabled else None
        payload = json.dumps(_set_draining(enabled, lease_seconds=lease), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handoff_control(self):
        """Prepare one replacement and acknowledge READY before crossing COMMIT."""
        if not _is_loopback_client(self.client_address[0]):
            self.send_error(403, "handoff control is available only from loopback")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            self.send_error(400, "invalid handoff content length")
            return
        if content_length <= 0 or content_length > HANDOFF_CONTROL_MAX_BYTES:
            self.send_error(413, "handoff request exceeds the control limit")
            return
        raw = self.rfile.read(content_length)
        if len(raw) != content_length:
            self.send_error(400, "incomplete handoff request")
            return
        try:
            request = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "invalid handoff JSON")
            return
        if not isinstance(request, dict):
            self.send_error(400, "handoff request must be an object")
            return
        allowed = {
            "transaction_id", "release", "source_sha256", "manifest_sha256",
            "timeout_seconds", "lease_seconds",
        }
        if set(request) - allowed:
            self.send_error(400, "handoff request contains unknown fields")
            return
        expected = {key: request.get(key) for key in (
            "transaction_id", "release", "source_sha256", "manifest_sha256",
        )}
        if not _disk_payload_matches_handoff_expected(expected):
            self.send_error(409, "handoff request does not match the current disk payload")
            return
        try:
            timeout_seconds = min(120.0, max(0.1, float(request.get("timeout_seconds", 30.0))))
            lease_seconds = _bounded_drain_lease_seconds(request.get("lease_seconds"))
            prepared = _prepare_handoff(
                self.server,
                expected,
                timeout_seconds=timeout_seconds,
                lease_seconds=lease_seconds,
            )
        except HandoffError as exc:
            status = 409 if isinstance(exc, HandoffConflict) else 503
            payload = json.dumps({
                "ok": False,
                "error": "handoff_in_progress" if status == 409 else "handoff_prepare_failed",
            }, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps({
            "ok": True,
            "state": "ready",
            "protocol_version": HANDOFF_PROTOCOL_VERSION,
            "child_pid": prepared["child"].process.pid,
            "transaction_id": expected["transaction_id"],
        }, separators=(",", ":")).encode()
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()
        threading.Thread(
            target=_commit_prepared_handoff,
            args=(self.server, prepared),
            daemon=True,
            name="dmx-handoff-commit",
        ).start()

    def do_POST(self):
        if self.path == "/control/drain":
            self._drain_control(True)
            return
        if self.path == "/control/handoff":
            self._handoff_control()
            return
        self._relay("POST")

    def do_GET(self):
        if self.path == "/healthz":
            self._runtime_status()
            return
        self._relay("GET")

    def do_DELETE(self):
        if self.path == "/control/drain":
            self._drain_control(False)
            return
        self._relay("DELETE")

    def do_PATCH(self):
        self._relay("PATCH")

    def do_PUT(self):
        self._relay("PUT")


def _serve_with_handoff_resume(
    server: ThreadingHTTPServer,
    *,
    initial_serving_thread: threading.Thread | None = None,
) -> None:
    """Serve until ordinary stop, finalized replacement, or a resumable rollback."""
    first_serving_thread = initial_serving_thread
    while True:
        if first_serving_thread is not None:
            first_serving_thread.join()
            first_serving_thread = None
        else:
            server.serve_forever()
        with _HANDOFF_LOCK:
            state = str(_HANDOFF_SESSION.get("state", "idle"))
            outcome = _HANDOFF_SESSION.get("outcome")
            outcome_ready = _HANDOFF_SESSION.get("outcome_ready")
            timeout_seconds = float(_HANDOFF_SESSION.get("timeout_seconds", 1.0))
        if outcome is None and state == "idle":
            with _RESPONSE_GATE_LOCK:
                draining = _DRAINING
            if not draining:
                return
        if isinstance(outcome_ready, threading.Event) and not outcome_ready.is_set():
            outcome_ready.wait(
                timeout=max(1.0, timeout_seconds * 3 + HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS)
            )
        with _HANDOFF_LOCK:
            outcome = _HANDOFF_SESSION.get("outcome")
            deadline = _HANDOFF_SESSION.get("drain_deadline")
        if outcome == "rolled_back":
            _set_draining(False)
            _reset_handoff_session_to_idle()
            continue
        if outcome == "finalized":
            if not isinstance(deadline, (int, float)):
                deadline = time.monotonic()
            while True:
                with _RESPONSE_GATE_LOCK:
                    active = max(_ACTIVE_RESPONSES, _ACTIVE_HANDLERS)
                if active <= 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
            if active > 0:
                _log(f"event=handoff_old_drain_expired remaining_active={active}")
            return
        if outcome == "abort_unconfirmed":
            _log("event=handoff_abort_unconfirmed action=old_listener_exit")
            return
        _log("event=handoff_outcome_unconfirmed action=old_listener_exit")
        return


def _read_child_control_message(stream) -> dict:
    line = stream.readline(HANDOFF_CONTROL_MAX_BYTES + 1)
    if not line:
        raise EOFError("handoff control pipe closed")
    if len(line) > HANDOFF_CONTROL_MAX_BYTES or not line.endswith(b"\n"):
        raise HandoffError("handoff control message exceeds the limit")
    try:
        message = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff control message is invalid") from exc
    if not isinstance(message, dict):
        raise HandoffError("handoff control message must be an object")
    return message


def _write_child_control_message(stream, message: dict) -> None:
    encoded = json.dumps(
        message, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii") + b"\n"
    if len(encoded) > HANDOFF_CONTROL_MAX_BYTES:
        raise HandoffError("handoff control message exceeds the limit")
    stream.write(encoded)
    stream.flush()


def _server_from_handoff_listener(listener: socket.socket) -> _ResilientProxyServer:
    address = listener.getsockname()
    server = _ResilientProxyServer(address, Handler, bind_and_activate=False)
    try:
        server.socket.close()
    except OSError:
        pass
    server.socket = listener
    server.server_address = address
    return server


def _valid_prepare_for_this_child(message: object) -> bool:
    if not isinstance(message, dict) or message.get("type") != "prepare":
        return False
    listener_fields = {"listener_share_b64"} if "listener_share_b64" in message else {"listener_fd"}
    expected_fields = {
        "type", "protocol_version", "transaction_id", "release",
        "source_sha256", "manifest_sha256",
    } | listener_fields
    if set(message) != expected_fields:
        return False
    return (
        message.get("protocol_version") == HANDOFF_PROTOCOL_VERSION
        and isinstance(message.get("transaction_id"), str)
        and bool(message.get("transaction_id"))
        and message.get("release") == release_version()
        and message.get("source_sha256") == source_sha256()
        and message.get("manifest_sha256") == _payload_manifest_sha256()
    )


def _run_handoff_child() -> int:
    """Hold the inherited listener dormant until the parent crosses COMMIT."""
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    server = None
    serving_thread = None
    try:
        prepare = _read_child_control_message(input_stream)
        if not _valid_prepare_for_this_child(prepare):
            raise HandoffError("handoff PREPARE identity mismatch")
        _transition_handoff("preparing")
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION.update({
                "transaction_id": prepare["transaction_id"],
                "child_pid": os.getpid(),
                "expected": {
                    "transaction_id": prepare["transaction_id"],
                    "release": prepare["release"],
                    "source_sha256": prepare["source_sha256"],
                    "manifest_sha256": prepare["manifest_sha256"],
                },
            })
        listener = _listener_from_handoff_prepare(prepare)
        server = _server_from_handoff_listener(listener)
        global _SERVER_INSTANCE
        _SERVER_INSTANCE = server
        _transition_handoff("ready")
        _write_child_control_message(output_stream, {
            "type": "ready",
            "protocol_version": HANDOFF_PROTOCOL_VERSION,
            "pid": os.getpid(),
            "transaction_id": prepare["transaction_id"],
            "release": release_version(),
            "source_sha256": source_sha256(),
            "manifest_sha256": _payload_manifest_sha256(),
        })
        command = _read_child_control_message(input_stream)
        if command != {"type": "commit"}:
            raise HandoffError("handoff child did not receive COMMIT")
        _transition_handoff("committing")
        _transition_handoff("serving")
        serving_thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="dmx-handoff-serving",
        )
        serving_thread.start()
        _write_child_control_message(output_stream, {
            "type": "serving",
            "pid": os.getpid(),
            "transaction_id": prepare["transaction_id"],
        })
        command = _read_child_control_message(input_stream)
        if command == {"type": "abort"}:
            raise HandoffError("handoff parent aborted before FINALIZE")
        if command != {"type": "finalize"}:
            raise HandoffError("handoff child did not receive FINALIZE")
        _transition_handoff("finalizing")
        _transition_handoff("finalized")
        _write_child_control_message(output_stream, {
            "type": "finalized",
            "pid": os.getpid(),
            "transaction_id": prepare["transaction_id"],
        })
        _serve_with_handoff_resume(server, initial_serving_thread=serving_thread)
        return 0
    except Exception:
        if server is not None:
            if serving_thread is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                serving_thread.join(timeout=2)
            try:
                server.server_close()
            except Exception:
                pass
        return 1


def main():
    if os.environ.get("DMX_HANDOFF_CHILD") == "1" or "--handoff-child" in sys.argv[1:]:
        raise SystemExit(_run_handoff_child())
    global _SERVER_INSTANCE
    _log(
        f"starting dmx-responses-proxy listener={HOST}:{PORT} "
        f"responses_max_concurrency={RESPONSES_MAX_CONCURRENCY} "
        f"upstream_timeout={UPSTREAM_TIMEOUT} read_timeout={UPSTREAM_READ_TIMEOUT} "
        f"log_max_bytes={LOG_MAX_BYTES} log_backup_count={LOG_BACKUP_COUNT}"
    )
    httpd = _ResilientProxyServer((HOST, PORT), Handler)
    _SERVER_INSTANCE = httpd
    try:
        _serve_with_handoff_resume(httpd)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
