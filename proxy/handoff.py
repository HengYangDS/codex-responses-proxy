"""Protocol-v2 rolling handoff for the DMX Responses proxy.

This module owns the process-local transaction, listener transfer, parent/child
control channel, and bounded rollback semantics. The proxy entrypoint supplies
its drain gate, server construction, runtime identity, and logging primitives
through :class:`Context`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import IO
from typing import Callable
from typing import Mapping
from typing import TypedDict
from typing import cast


type JsonObject = dict[str, object]
type ReadOnlyJsonObject = Mapping[str, object]


class _PopenKwargs(TypedDict, total=False):
    """Keyword arguments for a binary handoff child process."""

    stdin: int
    stdout: int
    stderr: int
    close_fds: bool
    creationflags: int
    pass_fds: tuple[int, ...]
    start_new_session: bool
    env: dict[str, str]


class PreparedHandoff(TypedDict):
    """Validated replacement and bounded timing used at the commit barrier."""

    child: "HandoffChild"
    expected: JsonObject
    timeout_seconds: float
    lease_seconds: int


HANDOFF_PROTOCOL_VERSION = 2
HANDOFF_CONTROL_MAX_BYTES = 32 * 1024
HANDOFF_READY_TIMEOUT_SECONDS = 10.0
HANDOFF_CHILD_EXIT_TIMEOUT_SECONDS = 5.0
HANDOFF_DEFAULT_LEASE_SECONDS = 30.0


class HandoffError(RuntimeError):
    """A bounded rolling-handoff transaction could not be completed safely."""


class HandoffConflict(HandoffError):
    """Another process-local handoff already owns the single-flight session."""


@dataclass(frozen=True)
class Context:
    """Proxy-owned primitives needed by the handoff transaction."""

    proxy_script: Path
    release_version: Callable[[], str]
    serving_payload_sha256: Callable[[], str | None]
    release_receipt_sha256: Callable[[], str | None]
    response_gate_lock: threading.Lock
    draining: Callable[[], bool]
    active_responses: Callable[[], int]
    active_handlers: Callable[[], int]
    bounded_lease_seconds: Callable[[object | None], int]
    set_draining: Callable[..., JsonObject]
    log: Callable[[str], None]
    server_factory: Callable[[socket.socket], ThreadingHTTPServer]
    set_server_instance: Callable[[ThreadingHTTPServer], None]


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


def validate_transition(current_state: str, target_state: str) -> bool:
    """Return whether one explicit protocol-v2 state transition is legal."""
    return target_state in _HANDOFF_TRANSITIONS.get(current_state, frozenset())


def reset_session_to_idle() -> None:
    """Reset the process-local transaction only after child cleanup is complete."""
    with _HANDOFF_LOCK:
        _HANDOFF_SESSION.clear()
        _HANDOFF_SESSION.update(
            state="idle",
            transaction_id=None,
            child_pid=None,
            outcome=None,
            outcome_ready=threading.Event(),
            lease_seconds=HANDOFF_DEFAULT_LEASE_SECONDS,
            drain_deadline=None,
        )


def _transition(target_state: str) -> None:
    with _HANDOFF_LOCK:
        current = str(_HANDOFF_SESSION.get("state", "idle"))
        if not validate_transition(current, target_state):
            raise HandoffError(f"illegal handoff transition {current}->{target_state}")
        _HANDOFF_SESSION["state"] = target_state


def payload_manifest_sha256(context: Context) -> str | None:
    """Hash the installed payload manifest without exposing its contents."""
    candidate = context.proxy_script.parents[1] / "payload-manifest.json"
    try:
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return None


def disk_payload_matches_expected(expected: ReadOnlyJsonObject, context: Context) -> bool:
    """Verify the payload that a replacement child would load from disk."""
    return (
        expected.get("release") == context.release_version()
        and expected.get("serving_payload_sha256") == context.serving_payload_sha256()
        and expected.get("release_receipt_sha256") == context.release_receipt_sha256()
        and expected.get("manifest_sha256") == payload_manifest_sha256(context)
    )


def runtime_identity(context: Context) -> dict[str, object]:
    """Return secret-free process and transaction identity for health proofs."""
    with _HANDOFF_LOCK, context.response_gate_lock:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        accepting = not context.draining() and state in {"idle", "serving", "finalized"}
        return {
            "pid": os.getpid(),
            "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
            "handoff_transaction_id": _HANDOFF_SESSION.get("transaction_id"),
            "handoff_state": state,
            "payload_manifest_sha256": payload_manifest_sha256(context),
            "accepting": accepting,
            "active_handlers": context.active_handlers(),
        }


def popen_kwargs(listener_fd: int | None, *, is_windows: bool) -> _PopenKwargs:
    """Return platform-specific, pipe-only child process settings."""
    kwargs: _PopenKwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if is_windows:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        if listener_fd is None:
            raise HandoffError("POSIX handoff requires a listener fd")
        kwargs["pass_fds"] = (listener_fd,)
        kwargs["start_new_session"] = True
    return kwargs


class HandoffChild:
    """One bounded structured control channel to a prepared replacement."""

    def __init__(self, process: subprocess.Popen[bytes]):
        if process.stdin is None or process.stdout is None:
            raise HandoffError("handoff child pipes are unavailable")
        self.process = process
        self._input: IO[bytes] = process.stdin
        self._output: IO[bytes] = process.stdout
        self._send_lock = threading.Lock()
        self._events: queue.Queue[JsonObject | Exception] = queue.Queue()
        self._reader_started = False
        self._reader_lock = threading.Lock()

    def send_message(self, message: JsonObject) -> None:
        if not isinstance(message, dict):
            raise HandoffError("handoff message must be an object")
        encoded = (
            json.dumps(message, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
            + b"\n"
        )
        if len(encoded) > HANDOFF_CONTROL_MAX_BYTES:
            raise HandoffError("handoff message exceeds the control limit")
        with self._send_lock:
            try:
                self._input.write(encoded)
                self._input.flush()
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
                        line = self._output.readline(HANDOFF_CONTROL_MAX_BYTES + 1)
                        if not line:
                            self._events.put(HandoffError("handoff child control pipe closed"))
                            return
                        if len(line) > HANDOFF_CONTROL_MAX_BYTES or not line.endswith(b"\n"):
                            self._events.put(
                                HandoffError("handoff child message exceeds the control limit")
                            )
                            return
                        try:
                            message = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            self._events.put(HandoffError("handoff child emitted invalid JSON"))
                            return
                        if not isinstance(message, dict):
                            self._events.put(
                                HandoffError("handoff child message must be an object")
                            )
                            return
                        self._events.put(message)
                except (OSError, ValueError):
                    self._events.put(HandoffError("handoff child control pipe read failed"))

            threading.Thread(target=read_events, daemon=True, name="dmx-handoff-reader").start()

    def recv_message(self, timeout: float) -> JsonObject:
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


def spawn_child(
    listener: socket.socket,
    expected: ReadOnlyJsonObject,
    context: Context,
    *,
    is_windows: bool | None = None,
) -> HandoffChild:
    """Spawn a non-accepting replacement and send its bounded PREPARE message."""
    windows = os.name == "nt" if is_windows is None else bool(is_windows)
    listener_fd = None if windows else listener.fileno()
    kwargs = popen_kwargs(listener_fd, is_windows=windows)
    env = os.environ.copy()
    env["DMX_HANDOFF_CHILD"] = "1"
    kwargs["env"] = env
    process: subprocess.Popen[bytes] = subprocess.Popen(
        [sys.executable, str(context.proxy_script), "--handoff-child"],
        **kwargs,
    )
    child = HandoffChild(process)
    message = {
        "type": "prepare",
        "protocol_version": HANDOFF_PROTOCOL_VERSION,
        "transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "serving_payload_sha256": expected["serving_payload_sha256"],
        "release_receipt_sha256": expected["release_receipt_sha256"],
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


def listener_from_prepare(message: ReadOnlyJsonObject) -> socket.socket:
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


def _message_matches(message: object, expected: ReadOnlyJsonObject, message_type: str) -> bool:
    if not isinstance(message, dict):
        return False
    typed_message = cast("JsonObject", message)
    if typed_message.get("type") != message_type:
        return False
    common = {
        "type": message_type,
        "pid": expected["pid"],
        "transaction_id": expected["transaction_id"],
    }
    if message_type == "ready":
        common.update(
            {
                "protocol_version": HANDOFF_PROTOCOL_VERSION,
                "release": expected["release"],
                "serving_payload_sha256": expected["serving_payload_sha256"],
                "release_receipt_sha256": expected["release_receipt_sha256"],
                "manifest_sha256": expected["manifest_sha256"],
            }
        )
    return set(typed_message) == set(common) and all(
        typed_message.get(key) == value for key, value in common.items()
    )


def _health_matches(health: object, expected: ReadOnlyJsonObject) -> bool:
    if not isinstance(health, dict):
        return False
    typed_health = cast("JsonObject", health)
    required = {
        "pid": expected["pid"],
        "handoff_protocol_version": HANDOFF_PROTOCOL_VERSION,
        "handoff_transaction_id": expected["transaction_id"],
        "release": expected["release"],
        "serving_payload_sha256": expected["serving_payload_sha256"],
        "release_receipt_sha256": expected["release_receipt_sha256"],
        "payload_manifest_sha256": expected["manifest_sha256"],
        "handoff_state": "serving",
        "accepting": True,
    }
    return all(typed_health.get(key) == value for key, value in required.items())


def probe_health(port: int, *, timeout_seconds: float) -> JsonObject:
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


def _rollback_without_child() -> None:
    with _HANDOFF_LOCK:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        if state in {"preparing", "ready", "committing", "serving", "finalizing"}:
            _transition("aborting")
            _transition("rolled_back")
        if _HANDOFF_SESSION.get("state") == "rolled_back":
            _transition("idle")
        _HANDOFF_SESSION["transaction_id"] = None
        _HANDOFF_SESSION["child_pid"] = None


def abort(child: HandoffChild) -> None:
    """Abort one child and confirm its exit before exposing rollback."""
    with _HANDOFF_LOCK:
        state = str(_HANDOFF_SESSION.get("state", "idle"))
        if state not in {"aborting", "rolled_back", "idle"}:
            _transition("aborting")
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
            _transition("rolled_back")


def prepare(
    server: ThreadingHTTPServer,
    expected: ReadOnlyJsonObject,
    context: Context,
    *,
    timeout_seconds: float = HANDOFF_READY_TIMEOUT_SECONDS,
    lease_seconds: float = HANDOFF_DEFAULT_LEASE_SECONDS,
) -> PreparedHandoff:
    """Prepare and validate a non-accepting replacement without closing admission."""
    required = (
        "transaction_id",
        "release",
        "serving_payload_sha256",
        "release_receipt_sha256",
        "manifest_sha256",
    )
    if not isinstance(expected, dict) or any(
        not isinstance(expected.get(key), str) or not expected.get(key) for key in required
    ):
        raise HandoffError("handoff request identity is incomplete")
    with _HANDOFF_LOCK:
        if _HANDOFF_SESSION.get("state") == "finalized":
            reset_session_to_idle()
        if _HANDOFF_SESSION.get("state") != "idle":
            raise HandoffConflict("handoff is already in progress")
        _transition("preparing")
        _HANDOFF_SESSION.update(
            transaction_id=expected["transaction_id"],
            child_pid=None,
            outcome=None,
            outcome_ready=threading.Event(),
            lease_seconds=context.bounded_lease_seconds(lease_seconds),
            timeout_seconds=max(0.1, float(timeout_seconds)),
        )
    child = None
    try:
        child = spawn_child(server.socket, expected, context)
        child_expected = {**expected, "pid": child.process.pid}
        ready = child.recv_message(max(0.1, float(timeout_seconds)))
        if not _message_matches(ready, child_expected, "ready"):
            raise HandoffError("handoff child READY identity mismatch")
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION.update(
                child_pid=child.process.pid, child=child, expected=dict(expected)
            )
            _transition("ready")
        return {
            "child": child,
            "expected": dict(expected),
            "timeout_seconds": max(0.1, float(timeout_seconds)),
            "lease_seconds": context.bounded_lease_seconds(lease_seconds),
        }
    except Exception as exc:
        if child is not None:
            try:
                abort(child)
            finally:
                with _HANDOFF_LOCK:
                    if _HANDOFF_SESSION.get("state") == "rolled_back":
                        _transition("idle")
                    _HANDOFF_SESSION["transaction_id"] = None
                    _HANDOFF_SESSION["child_pid"] = None
        else:
            _rollback_without_child()
        if isinstance(exc, HandoffError):
            raise
        raise HandoffError("handoff child preparation failed") from exc


def _set_outcome(outcome: str) -> None:
    with _HANDOFF_LOCK:
        _HANDOFF_SESSION["outcome"] = outcome
        event = _HANDOFF_SESSION.get("outcome_ready")
        if isinstance(event, threading.Event):
            event.set()


def commit(server: ThreadingHTTPServer, prepared: PreparedHandoff, context: Context) -> str:
    """Cross the accept barrier and either finalize or expose a resumable rollback."""
    child = prepared["child"]
    expected = prepared["expected"]
    child_expected = {**expected, "pid": child.process.pid}
    timeout_seconds = prepared["timeout_seconds"]
    accept_stopped = False
    try:
        _transition("committing")
        drain = context.set_draining(True, lease_seconds=prepared["lease_seconds"])
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION["drain_deadline"] = time.monotonic() + prepared["lease_seconds"]
            _HANDOFF_SESSION["drain_generation"] = drain["drain_generation"]
        server.shutdown()
        accept_stopped = True
        child.send_message({"type": "commit"})
        serving = child.recv_message(timeout_seconds)
        if not _message_matches(serving, child_expected, "serving"):
            raise HandoffError("handoff child SERVING identity mismatch")
        _transition("serving")
        address = getattr(server, "server_address", None)
        health_port = (
            address[1] if isinstance(address, (tuple, list)) and len(address) > 1 else 8791
        )
        health = probe_health(health_port, timeout_seconds=timeout_seconds)
        if not _health_matches(health, child_expected):
            raise HandoffError("handoff child health identity mismatch")
        _transition("finalizing")
        child.send_message({"type": "finalize"})
        finalized = child.recv_message(timeout_seconds)
        if not _message_matches(finalized, child_expected, "finalized"):
            raise HandoffError("handoff child FINALIZED identity mismatch")
        _transition("finalized")
        _set_outcome("finalized")
        return "finalized"
    except Exception:
        abort_confirmed = False
        try:
            abort(child)
            abort_confirmed = True
        except Exception:
            _set_outcome("abort_unconfirmed")
        if abort_confirmed:
            _set_outcome("rolled_back")
        if not accept_stopped:
            try:
                server.shutdown()
            except Exception:
                pass
        return "rolled_back" if abort_confirmed else "abort_unconfirmed"


def serve_with_resume(
    server: ThreadingHTTPServer,
    context: Context,
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
            raw_timeout_seconds = _HANDOFF_SESSION.get("timeout_seconds", 1.0)
            timeout_seconds = (
                float(raw_timeout_seconds) if isinstance(raw_timeout_seconds, (int, float)) else 1.0
            )
        if outcome is None and state == "idle":
            with context.response_gate_lock:
                draining = context.draining()
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
            context.set_draining(False)
            reset_session_to_idle()
            continue
        if outcome == "finalized":
            if not isinstance(deadline, (int, float)):
                deadline = time.monotonic()
            while True:
                with context.response_gate_lock:
                    active = max(context.active_responses(), context.active_handlers())
                if active <= 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
            if active > 0:
                context.log(f"event=handoff_old_drain_expired remaining_active={active}")
            return
        if outcome == "abort_unconfirmed":
            context.log("event=handoff_abort_unconfirmed action=old_listener_exit")
            return
        context.log("event=handoff_outcome_unconfirmed action=old_listener_exit")
        return


def _read_control_message(stream: IO[bytes]) -> JsonObject:
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


def _write_control_message(stream: IO[bytes], message: ReadOnlyJsonObject) -> None:
    encoded = (
        json.dumps(message, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
        + b"\n"
    )
    if len(encoded) > HANDOFF_CONTROL_MAX_BYTES:
        raise HandoffError("handoff control message exceeds the limit")
    stream.write(encoded)
    stream.flush()


def _valid_prepare(message: object, context: Context) -> bool:
    if not isinstance(message, dict):
        return False
    typed_message = cast("JsonObject", message)
    if typed_message.get("type") != "prepare":
        return False
    listener_fields = (
        {"listener_share_b64"} if "listener_share_b64" in typed_message else {"listener_fd"}
    )
    expected_fields = {
        "type",
        "protocol_version",
        "transaction_id",
        "release",
        "serving_payload_sha256",
        "release_receipt_sha256",
        "manifest_sha256",
    } | listener_fields
    if set(typed_message) != expected_fields:
        return False
    return (
        typed_message.get("protocol_version") == HANDOFF_PROTOCOL_VERSION
        and isinstance(typed_message.get("transaction_id"), str)
        and bool(typed_message.get("transaction_id"))
        and typed_message.get("release") == context.release_version()
        and typed_message.get("serving_payload_sha256") == context.serving_payload_sha256()
        and typed_message.get("release_receipt_sha256") == context.release_receipt_sha256()
        and typed_message.get("manifest_sha256") == payload_manifest_sha256(context)
    )


def run_child(context: Context) -> int:
    """Hold the inherited listener dormant until the parent crosses COMMIT."""
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    server = None
    serving_thread = None
    try:
        prepare_message = _read_control_message(input_stream)
        if not _valid_prepare(prepare_message, context):
            raise HandoffError("handoff PREPARE identity mismatch")
        _transition("preparing")
        with _HANDOFF_LOCK:
            _HANDOFF_SESSION.update(
                transaction_id=prepare_message["transaction_id"],
                child_pid=os.getpid(),
                expected={
                    key: prepare_message[key]
                    for key in (
                        "transaction_id",
                        "release",
                        "serving_payload_sha256",
                        "release_receipt_sha256",
                        "manifest_sha256",
                    )
                },
            )
        listener = listener_from_prepare(prepare_message)
        server = context.server_factory(listener)
        context.set_server_instance(server)
        _transition("ready")
        _write_control_message(
            output_stream,
            {
                "type": "ready",
                "protocol_version": HANDOFF_PROTOCOL_VERSION,
                "pid": os.getpid(),
                "transaction_id": prepare_message["transaction_id"],
                "release": context.release_version(),
                "serving_payload_sha256": context.serving_payload_sha256(),
                "release_receipt_sha256": context.release_receipt_sha256(),
                "manifest_sha256": payload_manifest_sha256(context),
            },
        )
        command = _read_control_message(input_stream)
        if command != {"type": "commit"}:
            raise HandoffError("handoff child did not receive COMMIT")
        _transition("committing")
        _transition("serving")
        serving_thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="dmx-handoff-serving",
        )
        serving_thread.start()
        _write_control_message(
            output_stream,
            {
                "type": "serving",
                "pid": os.getpid(),
                "transaction_id": prepare_message["transaction_id"],
            },
        )
        command = _read_control_message(input_stream)
        if command == {"type": "abort"}:
            raise HandoffError("handoff parent aborted before FINALIZE")
        if command != {"type": "finalize"}:
            raise HandoffError("handoff child did not receive FINALIZE")
        _transition("finalizing")
        _transition("finalized")
        _write_control_message(
            output_stream,
            {
                "type": "finalized",
                "pid": os.getpid(),
                "transaction_id": prepare_message["transaction_id"],
            },
        )
        serve_with_resume(server, context, initial_serving_thread=serving_thread)
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


reset_session_to_idle()
