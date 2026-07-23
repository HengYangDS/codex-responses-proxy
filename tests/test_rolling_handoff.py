#!/usr/bin/env python3
"""Step-3 TDD contract tests for the protocol-v2 rolling handoff (no dual accept, no orphan).

This suite was written before the rolling-handoff implementation and now serves
as its executable protocol, rollback, and cross-process regression contract.

This revision is the second correction pass. It fixes the full state-transition
table (adds the ``ready``/``aborting`` phases), makes ``accepting`` independent
from ``draining`` instead of a universal identity, strictly validates every
field of the "ready"/"serving"/"finalized" child messages and the health probe
(using the real runtime key names), documents the drain-before-shutdown
ordering and an outcome-ready event that guards ``main()``'s resume loop against
reading stale state, corrects the controller fixtures/mocks to match the real
listener-transition and legacy-path call sites, and reorders the real-subprocess
cleanups so owned processes are always terminated before their temporary
payload directory is removed.

PRIVATE API SURFACE
-------------------
``proxy/dmx_responses_proxy.py``:
  * ``HANDOFF_PROTOCOL_VERSION = 2`` module constant.
  * ``runtime_status()`` (and therefore ``GET /healthz``) gains: ``pid`` (int,
    ``os.getpid()``), ``handoff_protocol_version`` (int), ``handoff_transaction_id``
    (str | None), ``handoff_state`` (``None|"idle"|"preparing"|"ready"|
    "committing"|"serving"|"finalizing"|"finalized"|"aborting"|"rolled_back"``),
    ``payload_manifest_sha256`` (str | None), ``accepting`` (bool) -- alongside
    the existing ``release``, ``source_sha256``, ``draining``. ``accepting`` is
    *not* simply ``not draining``: while idle it is ``True`` (and ``draining``
    is ``False``), but during a prepared/ready/committing handoff window
    ``draining`` may still be ``False`` (admission has not been closed yet) even
    though ``accepting`` is already ``False``, because a transaction already
    owns the single-flight session and new handoff attempts (and, once wired,
    steady-state admission judgment) must not treat the process as freely
    available.
  * ``class HandoffError(RuntimeError)``.
  * ``_HANDOFF_LOCK`` / ``_HANDOFF_SESSION`` (a small dict: ``state``,
    ``transaction_id``, ``child_pid``, ``outcome``, ``outcome_ready`` -- a
    ``threading.Event`` set exactly once ``outcome`` has its final value)
    protecting single-flight state.
  * ``_validate_handoff_transition(current_state, target_state) -> bool`` -- a
    pure lookup against the documented legal-transition table:
    ``idle -> preparing -> ready -> committing -> serving -> finalizing ->
    finalized -> idle``, with an ``aborting`` escape from every one of
    ``preparing``/``ready``/``committing``/``serving``/``finalizing`` (never
    from ``idle`` or ``finalized``), followed by
    ``aborting -> rolled_back -> idle``. A direct ``<nonterminal> ->
    rolled_back`` shortcut that skips ``aborting`` is illegal.
  * ``_reset_handoff_session_to_idle() -> None``.
  * ``_handoff_popen_kwargs(listener_fd, *, is_windows) -> dict`` -- POSIX
    (``is_windows=False``) includes ``pass_fds=(listener_fd,)`` and
    ``close_fds=True``; Windows (``is_windows=True``) omits ``pass_fds`` entirely
    but keeps ``close_fds=True`` and pipes stdin/stdout.
  * ``_spawn_handoff_child(listener, expected, *, is_windows=None) -> _HandoffChild``
    -- builds the child ``Popen`` via ``_handoff_popen_kwargs`` and immediately
    writes one structured JSON "prepare" message to the child's stdin carrying
    ``transaction_id``/``release``/``source_sha256``/``manifest_sha256`` plus,
    Windows-only, ``listener_share_b64`` (``base64.b64encode(listener.share(pid))``,
    never the raw opaque bytes, and never placed in argv/env/log). On POSIX the fd
    is inherited via ``pass_fds`` instead.
  * ``class _HandoffChild`` with ``.process`` (Popen-like, exposes ``.pid``),
    ``.send_message(dict)``/``.recv_message(timeout) -> dict`` (one JSON object per
    line -- structured events, not plain text), ``.terminate_bounded(timeout) ->
    bool``, ``.kill_bounded(timeout) -> bool``.
  * ``_listener_from_handoff_prepare(message: dict) -> socket.socket`` -- the
    child-side counterpart: ``socket.fromshare(base64.b64decode(message[
    "listener_share_b64"]))`` on Windows, or ``socket.socket(fileno=message[
    "listener_fd"])`` over the inherited POSIX fd.
  * ``_probe_handoff_health(port, *, timeout_seconds) -> dict`` -- returns the
    same shape as ``runtime_status()``.
  * ``_prepare_handoff(server, expected, *, timeout_seconds=30.0,
    lease_seconds=30.0) -> dict`` -- runs synchronously on the HTTP request
    thread: single-flight guard (``idle -> preparing``), spawns the child on the
    *existing* listening socket, blocks for a "ready" message that must match
    *every* one of ``type=="ready"``, ``protocol_version``, ``pid`` (the child's
    own pid), ``transaction_id``, ``release``, ``source_sha256``, and
    ``manifest_sha256`` -- any single field mismatch is treated exactly like a
    timeout. Never touches admission or calls ``server.shutdown()``. On success
    transitions ``preparing -> ready`` and returns a ``prepared`` record consumed
    by ``_commit_prepared_handoff``. On a concurrent attempt, a spawn failure, or
    a ready timeout/mismatch, it bounds the child's exit (terminate then kill
    fallback), drives the session ``-> aborting -> rolled_back -> idle``, and
    raises ``HandoffError``.
  * ``_commit_prepared_handoff(server, prepared) -> str`` -- runs on a background
    thread started only *after* the HTTP handler has fully written and flushed
    its ``202`` response. Transitions ``ready -> committing``: sets draining via
    the existing ``_set_draining(True, lease_seconds=...)`` admission-lease
    primitive *before* calling ``server.shutdown()`` (draining must be visibly
    set first; ``shutdown()`` is only called once that has happened), and sends
    the "commit" message only once ``shutdown()`` has returned. Awaits
    "serving" (``committing -> serving``, message must carry the child's own
    ``pid`` and the ``transaction_id``), probes ``_probe_handoff_health`` for an
    *exact* match on ``pid``, ``handoff_protocol_version``,
    ``handoff_transaction_id``, ``release``, ``source_sha256``,
    ``payload_manifest_sha256``, ``handoff_state == "serving"``, and
    ``accepting is True``, transitions ``serving -> finalizing``, sends
    "finalize", awaits "finalized" (matching ``pid``/``transaction_id``).
    Returns ``"finalized"`` and records that outcome (then sets
    ``outcome_ready``) in ``_HANDOFF_SESSION``; any failure before the
    "finalized" acknowledgement calls ``_abort_handoff``, records
    ``"rolled_back"`` (then sets ``outcome_ready``), and returns
    ``"rolled_back"`` instead. Never calls ``serve_forever()`` itself.
  * ``_abort_handoff(child) -> None`` -- sends "abort" (best-effort), transitions
    the session ``-> aborting``, bounds child exit via ``terminate_bounded`` then
    ``kill_bounded`` fallback, and finally transitions ``aborting ->
    rolled_back``.
  * ``_serve_with_handoff_resume(server) -> None`` -- the new body of ``main()``'s
    outer loop, replacing a bare ``server.serve_forever()``: loops calling
    ``serve_forever()``; when it returns because a handoff shut it down, this
    function must not trust ``_HANDOFF_SESSION["outcome"]`` immediately --
    ``server.shutdown()`` returning on the request thread races with the
    background coordinator thread still finishing "serving"/"finalize"/health
    work -- so it first waits (bounded) on ``_HANDOFF_SESSION["outcome_ready"]``.
    A ``"rolled_back"`` outcome reopens admission (``_set_draining(False)``),
    resets the session, and calls ``serve_forever()`` again on the same
    still-open socket; a ``"finalized"`` outcome lets the process exit once the
    already-set drain lease/deadline reaches zero active responses or its
    deadline (reusing the existing lease/active-count bookkeeping; handler
    threads are already daemonic via ``daemon_threads = True`` so none of them
    block process exit); any other outcome (e.g. a plain ``KeyboardInterrupt``)
    returns immediately. This intentionally does *not* assume a
    ``server.resume_serving()`` hook.
  * ``Handler`` gains ``POST /control/handoff`` (loopback-only, single-flight ->
    HTTP 409 while one is already in progress; optionally reads
    ``lease_seconds``/``timeout_seconds`` from the JSON body and forwards them
    to ``_prepare_handoff``/``_commit_prepared_handoff``). The handler calls
    ``_prepare_handoff`` synchronously; on success it writes and flushes a full
    HTTP 202 "ready" JSON body *before* starting ``_commit_prepared_handoff`` on
    a daemon thread -- this ordering is unit-tested directly below.

``control.py``:
  * ``HANDOFF_PROTOCOL_VERSION = 2``.
  * ``_runtime_supports_handoff(runtime: dict | None) -> bool`` -- ``True`` only
    for a complete idle protocol-v2 identity with exact PID, release, source,
    manifest, admission, and transaction-state evidence. Incomplete or legacy
    snapshots fail closed (including an installed 1.0.24 -> first 1.0.25
    migration reading its own pre-v2 snapshot).
  * ``_expected_handoff_metadata(root: str) -> dict`` -- reads ``VERSION``,
    hashes ``proxy/dmx_responses_proxy.py``, and hashes the payload manifest
    under ``root`` (either the live ``ctx.install_dir`` for ``reload()`` or a
    staged directory for ``upgrade_from_stage()``), and mints a fresh
    ``transaction_id``.
  * ``_handoff_post(ctx, expected, *, lease_seconds) -> dict`` -- POSTs
    ``/control/handoff`` and requires an HTTP 202 "ready" body (mirrors the
    existing ``_drain_request`` shape/error handling) that echoes
    ``transaction_id`` and carries the new child's ``child_pid``.
  * ``_request_handoff(ctx, expected, *, timeout_seconds=30.0,
    lease_seconds=30.0) -> dict`` -- requires exactly one verified old listener
    *before* posting, calls ``_handoff_post`` to learn ``child_pid``, then polls
    both ``/healthz`` (via ``_runtime_metrics``) and
    ``common.verified_proxy_listener_pids`` until: the verified listener set is
    *exactly* ``[child_pid]`` (a transient ``[old_pid, child_pid]`` dual-accept
    window is not accepted as done -- it must keep polling), and the health
    snapshot is an *exact* match on ``pid == child_pid``,
    ``handoff_protocol_version``, ``handoff_transaction_id``, ``release``,
    ``source_sha256``, ``payload_manifest_sha256``, and ``accepting is True``.
    A wrong ``pid`` in the health snapshot (one that does not equal the
    ``child_pid`` the ready ack promised) is rejected exactly like any other
    field mismatch. Never calls ``common.terminate_pid``.
  * ``reload()`` gains an early branch: if the current runtime advertises
    handoff support, it calls ``_request_handoff`` and returns without ever
    terminating the old PID; otherwise it falls through, unchanged, to the
    existing ``_drain_listener_with_legacy_bootstrap`` + ``terminate_pid`` body.
  * ``upgrade_from_stage()`` gains the same early branch, captured *before*
    ``common.commit_payload_transaction`` is called (so it reads the old
    process's own pre-commit capability, not anything staged): if supported, it
    commits the stage, requests a handoff to the staged release/source/manifest,
    and finalizes the payload transaction only after ``_request_handoff``
    proves the exact match; any pre-finalize failure calls
    ``common.restore_payload_transaction`` + ``common.finalize_payload_transaction``
    and re-raises without ever calling ``common.terminate_pid``. When
    unsupported, the existing legacy drain/commit/terminate/watchdog body (via
    ``_drain_listener_with_legacy_bootstrap``) runs completely unchanged.
  * No new CLI subcommand: ``main()``'s ``command`` choices remain exactly
    ``("status", "enable", "disable", "reload", "adopt-aigw",
    "apply-control-plane", "upgrade")``.

Run: python3 -m unittest tests.test_rolling_handoff -v
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "proxy"))

from platform_adapters import common  # noqa: E402
import control  # noqa: E402
import dmx_responses_proxy as proxy_module  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until(predicate, timeout, interval=0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _proxy_is_up(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _http_json(port, path, *, method="GET", body=None, timeout=3.0):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.status, json.loads(response.read())


def _terminate_process(process: "subprocess.Popen", timeout=5) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _terminate_pid_best_effort(pid: "int | None") -> None:
    if pid is None:
        return
    try:
        common.terminate_pid(pid)
    except Exception:
        pass


def _pid_alive(pid: "int | None") -> bool:
    if pid is None:
        return False
    try:
        return bool(common.process_command(pid))
    except Exception:
        return False


class _ScriptedUpstream:
    """A real loopback HTTP server standing in for dmxapi during subprocess tests."""

    def __init__(self):
        received = self.received = []
        outer = self
        self._lock = threading.Lock()
        self._queue = []

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received.append(self.rfile.read(length))
                with outer._lock:
                    behavior = outer._queue.pop(0) if outer._queue else (200, b'{"id":"ok"}')
                if callable(behavior):
                    behavior(self)
                    return
                status, payload = behavior
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def push(self, behavior):
        with self._lock:
            self._queue.append(behavior)

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def _write_installed_payload(root: Path, *, release: str, port: int) -> common.InstallContext:
    """Build an installed-like temporary payload without touching the source tree."""
    install_dir = root / ".codex" / "dmx-proxy"
    for relative in common.RUNTIME_PAYLOAD_FILES:
        source = Path(ROOT, relative)
        target = install_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (install_dir / "VERSION").write_text(release + "\n", encoding="utf-8")
    ctx = common.InstallContext(
        home=str(root),
        install_dir=str(install_dir),
        proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
        watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
        python=sys.executable,
        codex_config=str(root / ".codex" / "config.toml"),
        log_dir=str(root / ".codex" / "log"),
        port=port,
    )
    common.write_payload_manifest(ctx)
    return ctx


def _installed_expected_metadata(ctx: common.InstallContext, transaction_id: str) -> dict:
    """Read exactly what the (not-yet-existing) production helper would compute."""
    manifest_path = Path(common.payload_manifest_path(ctx))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "transaction_id": transaction_id,
        "release": manifest["release"],
        "source_sha256": manifest["files"]["proxy/dmx_responses_proxy.py"],
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "timeout_seconds": 10,
    }


def _start_real_proxy(ctx: common.InstallContext, *, upstream_url: str, log_path: Path,
                       extra_env: dict | None = None) -> "subprocess.Popen":
    env = dict(os.environ)
    env["DMX_PROXY_HOST"] = "127.0.0.1"
    env["DMX_PROXY_PORT"] = str(ctx.port)
    env["DMX_UPSTREAM"] = upstream_url
    env["DMX_PROXY_LOG"] = str(log_path)
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        [ctx.python, ctx.proxy_script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_until(lambda: _proxy_is_up(ctx.port), timeout=10):
        _terminate_process(process)
        raise RuntimeError("real proxy subprocess did not bind its listening socket in time")
    return process


# ---------------------------------------------------------------------------
# 1. Protocol / status contract
# ---------------------------------------------------------------------------

class TestProtocolContract(unittest.TestCase):
    """The wire-level contract every other component below depends on."""

    def setUp(self):
        self.p = proxy_module
        self.p._reset_runtime_metrics_for_test()
        self.p._reset_handoff_session_to_idle()

    def test_proxy_declares_handoff_protocol_version_two(self):
        self.assertEqual(self.p.HANDOFF_PROTOCOL_VERSION, 2)

    def test_control_declares_matching_handoff_protocol_version(self):
        self.assertEqual(control.HANDOFF_PROTOCOL_VERSION, 2)

    def test_runtime_status_contains_full_handoff_health_shape(self):
        status = self.p.runtime_status()
        for key in (
            "pid", "handoff_protocol_version", "handoff_transaction_id", "handoff_state",
            "release", "source_sha256", "payload_manifest_sha256", "accepting", "draining",
        ):
            self.assertIn(key, status, f"runtime_status() is missing {key!r}")
        self.assertEqual(status["handoff_protocol_version"], 2)
        self.assertEqual(status["pid"], os.getpid())

    def test_runtime_status_reports_accepting_true_and_draining_false_when_idle(self):
        status = self.p.runtime_status()
        self.assertIs(status["accepting"], True)
        self.assertIs(status["draining"], False)

    def test_a_prepared_or_committing_child_window_is_not_draining_but_is_also_not_accepting(self):
        # ``accepting`` is not merely ``not draining``: a transaction that owns
        # the single-flight session but has not yet closed admission (draining
        # is still False) must still report itself as unavailable for a fresh
        # handoff/admission decision.
        for state in ("ready", "committing"):
            with self.subTest(state=state):
                self.p._HANDOFF_SESSION["state"] = state
                try:
                    status = self.p.runtime_status()
                    self.assertIs(status["draining"], False)
                    self.assertIs(status["accepting"], False)
                finally:
                    self.p._reset_handoff_session_to_idle()

    def test_idle_handoff_state_has_no_transaction_id(self):
        status = self.p.runtime_status()
        self.assertIn(status["handoff_state"], (None, "idle"))
        self.assertIsNone(status["handoff_transaction_id"])

    def test_healthz_over_real_loopback_http_exposes_the_same_shape(self):
        proxy = self.p._ResilientProxyServer(("127.0.0.1", 0), self.p.Handler)
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        try:
            status_code, payload = _http_json(proxy.server_address[1], "/healthz")
            self.assertEqual(status_code, 200)
            for key in ("pid", "handoff_protocol_version", "handoff_transaction_id",
                        "handoff_state", "payload_manifest_sha256", "accepting"):
                self.assertIn(key, payload)
        finally:
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=2)


# ---------------------------------------------------------------------------
# 2. Legal/illegal handoff state transitions (pure lookup table)
# ---------------------------------------------------------------------------

class TestHandoffTransitionValidation(unittest.TestCase):
    def setUp(self):
        self.p = proxy_module

    def test_allows_the_documented_happy_path(self):
        for current, target in (
            ("idle", "preparing"),
            ("preparing", "ready"),
            ("ready", "committing"),
            ("committing", "serving"),
            ("serving", "finalizing"),
            ("finalizing", "finalized"),
            ("finalized", "idle"),
        ):
            with self.subTest(current=current, target=target):
                self.assertTrue(self.p._validate_handoff_transition(current, target))

    def test_allows_an_abort_escape_from_every_non_idle_non_finalized_state(self):
        for current in ("preparing", "ready", "committing", "serving", "finalizing"):
            with self.subTest(current=current):
                self.assertTrue(self.p._validate_handoff_transition(current, "aborting"))
        self.assertTrue(self.p._validate_handoff_transition("aborting", "rolled_back"))
        self.assertTrue(self.p._validate_handoff_transition("rolled_back", "idle"))

    def test_idle_and_finalized_have_no_abort_escape(self):
        self.assertFalse(self.p._validate_handoff_transition("idle", "aborting"))
        self.assertFalse(self.p._validate_handoff_transition("finalized", "aborting"))

    def test_rejects_skipping_states_in_the_happy_path(self):
        self.assertFalse(self.p._validate_handoff_transition("idle", "committing"))
        self.assertFalse(self.p._validate_handoff_transition("idle", "serving"))
        self.assertFalse(self.p._validate_handoff_transition("preparing", "committing"))
        self.assertFalse(self.p._validate_handoff_transition("ready", "serving"))
        self.assertFalse(self.p._validate_handoff_transition("committing", "finalizing"))

    def test_finalized_can_only_recycle_to_idle_for_the_next_transaction(self):
        self.assertFalse(self.p._validate_handoff_transition("finalized", "preparing"))
        self.assertFalse(self.p._validate_handoff_transition("finalized", "rolled_back"))
        self.assertTrue(self.p._validate_handoff_transition("finalized", "idle"))

    def test_rejects_direct_nonterminal_to_rolled_back_shortcuts(self):
        # Every non-idle, non-finalized phase must pass through ``aborting``
        # first; jumping straight to ``rolled_back`` is illegal.
        for current in ("idle", "preparing", "ready", "committing", "serving", "finalizing"):
            with self.subTest(current=current):
                self.assertFalse(self.p._validate_handoff_transition(current, "rolled_back"))

    def test_rejects_committing_directly_from_rolled_back(self):
        self.assertFalse(self.p._validate_handoff_transition("rolled_back", "committing"))


# ---------------------------------------------------------------------------
# 3. Platform-specific child spawning (no separate platform module)
# ---------------------------------------------------------------------------

class TestHandoffPlatformHelpers(unittest.TestCase):
    def setUp(self):
        self.p = proxy_module

    def _expected(self):
        return {
            "transaction_id": "txn-platform",
            "release": "1.0.25",
            "source_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        }

    def test_posix_kwargs_include_pass_fds_and_close_fds(self):
        kwargs = self.p._handoff_popen_kwargs(37, is_windows=False)
        self.assertEqual(kwargs.get("pass_fds"), (37,))
        self.assertTrue(kwargs.get("close_fds"))

    def test_windows_kwargs_omit_pass_fds_but_still_close_fds_and_pipe_stdio(self):
        kwargs = self.p._handoff_popen_kwargs(None, is_windows=True)
        self.assertNotIn("pass_fds", kwargs)
        self.assertTrue(kwargs.get("close_fds"))
        self.assertEqual(kwargs.get("stdin"), subprocess.PIPE)
        self.assertEqual(kwargs.get("stdout"), subprocess.PIPE)

    def test_posix_spawn_uses_the_listener_fileno_via_pass_fds(self):
        fake_process = mock.Mock(pid=4242, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.fileno.return_value = 37
        with mock.patch("subprocess.Popen", return_value=fake_process) as popen:
            child = self.p._spawn_handoff_child(listener, self._expected(), is_windows=False)
        self.assertIs(child.process, fake_process)
        _, kwargs = popen.call_args
        self.assertEqual(kwargs.get("pass_fds"), (37,))
        self.assertTrue(kwargs.get("close_fds"))
        written = b"".join(call.args[0] for call in fake_process.stdin.write.call_args_list)
        self.assertNotIn(b"listener_share_b64", written)

    def test_windows_spawn_never_supplies_pass_fds_and_sends_share_bytes_only_as_base64_over_stdin(self):
        fake_process = mock.Mock(pid=5150, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.share = mock.Mock(return_value=b"opaque-share-bytes")
        with mock.patch("subprocess.Popen", return_value=fake_process) as popen:
            self.p._spawn_handoff_child(listener, self._expected(), is_windows=True)
        args, kwargs = popen.call_args
        self.assertNotIn("pass_fds", kwargs)
        self.assertNotIn(b"opaque-share-bytes", str(args).encode())
        self.assertNotIn("opaque-share-bytes", json.dumps(kwargs.get("env") or {}))
        listener.share.assert_called_once_with(5150)
        written = b"".join(call.args[0] for call in fake_process.stdin.write.call_args_list)
        self.assertNotIn(b"opaque-share-bytes", written)  # only the base64 projection travels
        message = json.loads(written.splitlines()[0])
        self.assertEqual(
            base64.b64decode(message["listener_share_b64"]),
            b"opaque-share-bytes",
        )

    def test_windows_fromshare_roundtrip_reconstructs_a_socket_from_the_prepare_message(self):
        fake_socket = mock.Mock()
        message = {"listener_share_b64": base64.b64encode(b"share-bytes").decode("ascii")}
        with mock.patch.object(socket, "fromshare", create=True, return_value=fake_socket) as fromshare:
            result = self.p._listener_from_handoff_prepare(message)
        fromshare.assert_called_once_with(b"share-bytes")
        self.assertIs(result, fake_socket)

    def test_posix_listener_from_handoff_prepare_uses_the_inherited_fd(self):
        fake_socket = mock.Mock()
        message = {"listener_fd": 37}
        with mock.patch.object(socket, "socket", return_value=fake_socket) as ctor:
            result = self.p._listener_from_handoff_prepare(message)
        ctor.assert_called_once_with(fileno=37)
        self.assertIs(result, fake_socket)

    def test_precommit_control_pipe_eof_closes_without_shutdown_deadlock(self):
        self.p._reset_handoff_session_to_idle()
        prepare = {
            "type": "prepare",
            "protocol_version": self.p.HANDOFF_PROTOCOL_VERSION,
            "transaction_id": "txn-eof",
            "release": self.p.release_version(),
            "source_sha256": self.p.source_sha256(),
            "manifest_sha256": self.p._payload_manifest_sha256(),
            "listener_fd": 37,
        }
        raw = json.dumps(prepare, separators=(",", ":")).encode() + b"\n"
        fake_stdin = mock.Mock(buffer=io.BytesIO(raw))
        fake_stdout = mock.Mock(buffer=io.BytesIO())
        fake_server = mock.Mock()
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch.object(sys, "stdout", fake_stdout),
            mock.patch.object(self.p, "_listener_from_handoff_prepare", return_value=mock.Mock()),
            mock.patch.object(self.p, "_server_from_handoff_listener", return_value=fake_server),
        ):
            self.assertEqual(self.p._run_handoff_child(), 1)
        fake_server.shutdown.assert_not_called()
        fake_server.server_close.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Parent-side handoff state machine (mocked child / server, no real subprocess)
# ---------------------------------------------------------------------------

class TestParentHandoffStateMachine(unittest.TestCase):
    """Legal/illegal runtime behavior of the prepare -> commit -> finalize driver."""

    def setUp(self):
        self.p = proxy_module
        self.p._reset_runtime_metrics_for_test()
        self.p._reset_handoff_session_to_idle()

    def _expected(self, **overrides):
        expected = {
            "transaction_id": "txn-1",
            "release": "1.0.25",
            "source_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        }
        expected.update(overrides)
        return expected

    def _fake_server(self):
        server = mock.Mock()
        server.shutdown = mock.Mock()
        return server

    def _fake_child(self, *, pid=54321):
        child = mock.Mock()
        child.process = mock.Mock(pid=pid)
        child.terminate_bounded.return_value = True
        return child

    def _ready_message(self, child, expected):
        return {
            "type": "ready",
            "protocol_version": self.p.HANDOFF_PROTOCOL_VERSION,
            "pid": child.process.pid,
            "transaction_id": expected["transaction_id"],
            "release": expected["release"],
            "source_sha256": expected["source_sha256"],
            "manifest_sha256": expected["manifest_sha256"],
        }

    def _serving_message(self, child, expected):
        return {"type": "serving", "pid": child.process.pid, "transaction_id": expected["transaction_id"]}

    def _finalized_message(self, child, expected):
        return {"type": "finalized", "pid": child.process.pid, "transaction_id": expected["transaction_id"]}

    def _happy_recv_sequence(self, child, expected):
        return [
            self._ready_message(child, expected),
            self._serving_message(child, expected),
            self._finalized_message(child, expected),
        ]

    def _matching_health(self, child, expected, *, handoff_state="serving"):
        return {
            "pid": child.process.pid,
            "handoff_protocol_version": self.p.HANDOFF_PROTOCOL_VERSION,
            "handoff_transaction_id": expected["transaction_id"],
            "release": expected["release"],
            "source_sha256": expected["source_sha256"],
            "payload_manifest_sha256": expected["manifest_sha256"],
            "handoff_state": handoff_state,
            "accepting": True,
        }

    def test_prepare_then_commit_finalizes_and_never_reopens_admission_itself(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = self._happy_recv_sequence(child, expected)
        with (
            mock.patch.object(self.p, "_spawn_handoff_child", return_value=child) as spawn,
            mock.patch.object(self.p, "_probe_handoff_health", return_value=self._matching_health(child, expected)),
        ):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
            self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "ready")
            outcome = self.p._commit_prepared_handoff(server, prepared)
        spawn.assert_called_once()
        self.assertEqual(outcome, "finalized")
        server.shutdown.assert_called_once()
        child.send_message.assert_any_call({"type": "commit"})
        child.send_message.assert_any_call({"type": "finalize"})
        self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "finalized")
        self.assertTrue(self.p._HANDOFF_SESSION["outcome_ready"].is_set())

    def test_draining_is_set_before_shutdown_and_shutdown_completes_before_commit_is_sent(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        order = []
        server.shutdown.side_effect = lambda: order.append("shutdown")

        def send_message(message):
            order.append(f"send:{message.get('type')}")

        child.send_message.side_effect = send_message
        child.recv_message.side_effect = self._happy_recv_sequence(child, expected)
        real_set_draining = self.p._set_draining

        def observing_set_draining(enabled, **kwargs):
            order.append(f"draining:{enabled}")
            return real_set_draining(enabled, **kwargs)

        with (
            mock.patch.object(self.p, "_spawn_handoff_child", return_value=child),
            mock.patch.object(self.p, "_probe_handoff_health", return_value=self._matching_health(child, expected)),
            mock.patch.object(self.p, "_set_draining", side_effect=observing_set_draining),
        ):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
            self.p._commit_prepared_handoff(server, prepared)
        self.assertIn("draining:True", order)
        self.assertLess(order.index("draining:True"), order.index("shutdown"))
        self.assertLess(order.index("shutdown"), order.index("send:commit"))

    def test_child_never_receives_commit_before_shutdown_returns(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        shutdown_returned = threading.Event()

        def slow_shutdown():
            time.sleep(0.05)
            shutdown_returned.set()

        server.shutdown.side_effect = slow_shutdown

        def send_message(message):
            if message.get("type") == "commit":
                self.assertTrue(shutdown_returned.is_set(), "commit sent before shutdown() returned")

        child.send_message.side_effect = send_message
        child.recv_message.side_effect = self._happy_recv_sequence(child, expected)
        with (
            mock.patch.object(self.p, "_spawn_handoff_child", return_value=child),
            mock.patch.object(self.p, "_probe_handoff_health", return_value=self._matching_health(child, expected)),
        ):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
            self.p._commit_prepared_handoff(server, prepared)

    def test_simultaneous_handoff_is_rejected(self):
        server = self._fake_server()
        expected = self._expected()
        release_spawn = threading.Event()
        child = self._fake_child()
        child.recv_message.side_effect = [self._ready_message(child, expected)]

        def slow_spawn(*_args, **_kwargs):
            release_spawn.wait(timeout=5)
            return child

        errors = []

        def second_attempt():
            try:
                self.p._prepare_handoff(server, expected, timeout_seconds=5)
            except self.p.HandoffError as exc:
                errors.append(exc)

        with mock.patch.object(self.p, "_spawn_handoff_child", side_effect=slow_spawn):
            first = threading.Thread(target=self.p._prepare_handoff, args=(server, expected), kwargs={"timeout_seconds": 5})
            first.start()
            self.assertTrue(_wait_until(lambda: self.p._HANDOFF_SESSION.get("state") == "preparing", timeout=2))
            second = threading.Thread(target=second_attempt)
            second.start()
            second.join(timeout=5)
            release_spawn.set()
            first.join(timeout=5)
        self.assertEqual(len(errors), 1)
        self.assertIn("already in progress", str(errors[0]).lower())

    def test_child_start_failure_never_touches_admission_and_resets_to_idle(self):
        server = self._fake_server()
        expected = self._expected()
        with mock.patch.object(self.p, "_spawn_handoff_child", side_effect=OSError("fork failed")):
            with self.assertRaises(self.p.HandoffError):
                self.p._prepare_handoff(server, expected, timeout_seconds=5)
        server.shutdown.assert_not_called()
        self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "idle")

    def test_child_ready_timeout_resets_to_idle_without_touching_admission(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = TimeoutError("no ready message")
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p._prepare_handoff(server, expected, timeout_seconds=1)
        server.shutdown.assert_not_called()
        self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "idle")
        child.terminate_bounded.assert_called_once()

    def test_ready_message_field_mismatches_are_each_rejected(self):
        expected = self._expected()
        overrides = {
            "protocol_version": 1,
            "pid": 999999,
            "transaction_id": "wrong-txn",
            "release": "1.0.24",
            "source_sha256": "c" * 64,
            "manifest_sha256": "d" * 64,
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                self.p._reset_handoff_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                message = dict(self._ready_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [message]
                with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
                    with self.assertRaises(self.p.HandoffError):
                        self.p._prepare_handoff(server, expected, timeout_seconds=1)
                server.shutdown.assert_not_called()
                child.terminate_bounded.assert_called_once()

    def test_ready_message_wrong_type_is_rejected(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        message = dict(self._ready_message(child, expected), type="hello")
        child.recv_message.side_effect = [message]
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p._prepare_handoff(server, expected, timeout_seconds=1)
        child.terminate_bounded.assert_called_once()

    def test_commit_pipe_failure_aborts_and_records_rollback(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = [self._ready_message(child, expected)]

        def send_message(message):
            if message.get("type") == "commit":
                raise BrokenPipeError("child closed its stdin")

        child.send_message.side_effect = send_message
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
            outcome = self.p._commit_prepared_handoff(server, prepared)
        self.assertEqual(outcome, "rolled_back")
        server.shutdown.assert_called_once()  # shutdown already happened before commit
        child.terminate_bounded.assert_called_once()
        self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "rolled_back")
        self.assertTrue(self.p._HANDOFF_SESSION["outcome_ready"].is_set())

    def test_serving_timeout_aborts_and_records_rollback(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = [
            self._ready_message(child, expected),
            TimeoutError("no serving message"),
        ]
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=1)
            outcome = self.p._commit_prepared_handoff(server, prepared)
        self.assertEqual(outcome, "rolled_back")
        child.terminate_bounded.assert_called_once()

    def test_serving_message_field_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        for field, bad_value in (("pid", 1), ("transaction_id", "wrong-txn")):
            with self.subTest(field=field):
                self.p._reset_handoff_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                serving = dict(self._serving_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [self._ready_message(child, expected), serving]
                with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
                    prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
                    outcome = self.p._commit_prepared_handoff(server, prepared)
                self.assertEqual(outcome, "rolled_back")
                child.terminate_bounded.assert_called_once()

    def test_health_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        overrides = {
            "pid": 1,
            "handoff_protocol_version": 1,
            "handoff_transaction_id": "txn-wrong",
            "release": "1.0.24",
            "source_sha256": "c" * 64,
            "payload_manifest_sha256": "d" * 64,
            "handoff_state": "idle",
            "accepting": False,
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                self.p._reset_handoff_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                health = dict(self._matching_health(child, expected), **{field: bad_value})
                child.recv_message.side_effect = self._happy_recv_sequence(child, expected)[:2]
                with (
                    mock.patch.object(self.p, "_spawn_handoff_child", return_value=child),
                    mock.patch.object(self.p, "_probe_handoff_health", return_value=health),
                ):
                    prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
                    outcome = self.p._commit_prepared_handoff(server, prepared)
                self.assertEqual(outcome, "rolled_back")
                child.send_message.assert_any_call({"type": "abort"})
                child.terminate_bounded.assert_called_once()

    def test_abort_falls_back_to_kill_when_terminate_does_not_exit_child_in_time(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = TimeoutError("no ready message")
        child.terminate_bounded.return_value = False  # terminate alone was insufficient
        child.kill_bounded = mock.Mock(return_value=True)
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p._prepare_handoff(server, expected, timeout_seconds=1)
        child.terminate_bounded.assert_called_once()
        child.kill_bounded.assert_called_once()

    def test_unconfirmed_abort_never_reports_a_resumable_rollback(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = [
            self._ready_message(child, expected),
            BrokenPipeError("commit pipe failed"),
        ]
        child.terminate_bounded.return_value = False
        child.kill_bounded = mock.Mock(return_value=False)
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=1)
            outcome = self.p._commit_prepared_handoff(server, prepared)
        self.assertEqual(outcome, "abort_unconfirmed")
        self.assertEqual(self.p._HANDOFF_SESSION["outcome"], "abort_unconfirmed")
        self.assertNotEqual(self.p._HANDOFF_SESSION["state"], "rolled_back")
        server.shutdown.assert_called()

    def test_unconfirmed_precommit_abort_stays_fail_closed_instead_of_returning_idle(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = TimeoutError("no ready message")
        child.terminate_bounded.return_value = False
        child.kill_bounded = mock.Mock(return_value=False)
        with mock.patch.object(self.p, "_spawn_handoff_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p._prepare_handoff(server, expected, timeout_seconds=1)
        self.assertEqual(self.p._HANDOFF_SESSION["state"], "aborting")

    def test_finalize_ack_failure_aborts_and_records_rollback(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = [
            self._ready_message(child, expected),
            self._serving_message(child, expected),
            BrokenPipeError("gone"),
        ]
        with (
            mock.patch.object(self.p, "_spawn_handoff_child", return_value=child),
            mock.patch.object(self.p, "_probe_handoff_health", return_value=self._matching_health(child, expected)),
        ):
            prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
            outcome = self.p._commit_prepared_handoff(server, prepared)
        self.assertEqual(outcome, "rolled_back")
        child.terminate_bounded.assert_called_once()

    def test_finalized_message_field_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        for field, bad_value in (("pid", 1), ("transaction_id", "wrong-txn")):
            with self.subTest(field=field):
                self.p._reset_handoff_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                finalized = dict(self._finalized_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [
                    self._ready_message(child, expected),
                    self._serving_message(child, expected),
                    finalized,
                ]
                with (
                    mock.patch.object(self.p, "_spawn_handoff_child", return_value=child),
                    mock.patch.object(self.p, "_probe_handoff_health", return_value=self._matching_health(child, expected)),
                ):
                    prepared = self.p._prepare_handoff(server, expected, timeout_seconds=5)
                    outcome = self.p._commit_prepared_handoff(server, prepared)
                self.assertEqual(outcome, "rolled_back")
                child.terminate_bounded.assert_called_once()


# ---------------------------------------------------------------------------
# 5. The /control/handoff HTTP handler: response-before-coordinator ordering
# ---------------------------------------------------------------------------

class TestHandoffControlHandler(unittest.TestCase):
    def setUp(self):
        self.p = proxy_module

    def _expected(self):
        return {
            "transaction_id": "txn-handler",
            "release": "1.0.25",
            "source_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        }

    def _fake_handler_self(self, body: dict):
        payload = json.dumps(body).encode()
        fake_self = mock.Mock()
        fake_self.client_address = ("127.0.0.1", 51234)
        fake_self.headers = {"Content-Length": str(len(payload))}
        fake_self.rfile = mock.Mock()
        fake_self.rfile.read.return_value = payload
        fake_self.wfile = mock.Mock()
        fake_self.server = mock.Mock()
        return fake_self

    def test_handler_writes_and_flushes_the_202_before_starting_the_background_coordinator(self):
        order = []
        fake_self = self._fake_handler_self(self._expected())
        fake_self.wfile.write.side_effect = lambda *_a: order.append("write")
        fake_self.wfile.flush.side_effect = lambda: order.append("flush")
        prepared = {"child": mock.Mock(process=mock.Mock(pid=999)), "expected": self._expected()}
        with (
            mock.patch.object(self.p, "_disk_payload_matches_handoff_expected", return_value=True),
            mock.patch.object(self.p, "_prepare_handoff", return_value=prepared),
            mock.patch("threading.Thread") as thread_cls,
        ):
            thread_cls.return_value.start.side_effect = lambda: order.append("coordinator_started")
            self.p.Handler._handoff_control(fake_self)
        self.assertEqual(order, ["write", "flush", "coordinator_started"])
        thread_cls.assert_called_once()
        _, kwargs = thread_cls.call_args
        self.assertEqual(kwargs.get("target"), self.p._commit_prepared_handoff)

    def test_handler_response_body_carries_child_pid_and_transaction_id(self):
        fake_self = self._fake_handler_self(self._expected())
        written = []
        fake_self.wfile.write.side_effect = lambda chunk: written.append(chunk)
        prepared = {"child": mock.Mock(process=mock.Mock(pid=999)), "expected": self._expected()}
        with (
            mock.patch.object(self.p, "_disk_payload_matches_handoff_expected", return_value=True),
            mock.patch.object(self.p, "_prepare_handoff", return_value=prepared),
            mock.patch("threading.Thread"),
        ):
            self.p.Handler._handoff_control(fake_self)
        fake_self.send_response.assert_called_once_with(202)
        body = json.loads(b"".join(written))
        self.assertEqual(body.get("child_pid"), 999)
        self.assertEqual(body.get("transaction_id"), self._expected()["transaction_id"])

    def test_handler_rejects_non_loopback_clients(self):
        fake_self = self._fake_handler_self(self._expected())
        fake_self.client_address = ("10.0.0.5", 51234)
        with mock.patch.object(self.p, "_prepare_handoff") as prepare:
            self.p.Handler._handoff_control(fake_self)
        prepare.assert_not_called()
        fake_self.send_error.assert_called_once()
        self.assertEqual(fake_self.send_error.call_args.args[0], 403)

    def test_handler_returns_409_when_a_handoff_is_already_in_progress(self):
        fake_self = self._fake_handler_self(self._expected())
        with (
            mock.patch.object(self.p, "_disk_payload_matches_handoff_expected", return_value=True),
            mock.patch.object(
                self.p,
                "_prepare_handoff",
                side_effect=self.p.HandoffConflict("a handoff is already in progress"),
            ),
        ):
            self.p.Handler._handoff_control(fake_self)
        fake_self.send_response.assert_called_once_with(409)


# ---------------------------------------------------------------------------
# 6. main()'s outer loop: reopen-and-resume vs. bounded-drain-then-exit
# ---------------------------------------------------------------------------

class TestServeWithHandoffResume(unittest.TestCase):
    def setUp(self):
        self.p = proxy_module
        self.p._reset_runtime_metrics_for_test()
        self.p._reset_handoff_session_to_idle()

    def test_rollback_outcome_reopens_admission_and_serves_again_on_the_same_socket(self):
        server = mock.Mock()
        calls = []

        def fake_serve_forever():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                self.p._set_draining(True)
                self.p._HANDOFF_SESSION["outcome"] = "rolled_back"
                self.p._HANDOFF_SESSION["outcome_ready"].set()
            else:
                self.p._HANDOFF_SESSION["outcome"] = None
                self.p._HANDOFF_SESSION["outcome_ready"].set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p._serve_with_handoff_resume(server)
        self.assertEqual(server.serve_forever.call_count, 2)
        self.assertFalse(self.p.runtime_status()["draining"])

    def test_waits_for_the_outcome_ready_event_instead_of_trusting_stale_state(self):
        # ``server.shutdown()`` returning on the request thread races with the
        # background coordinator thread still finishing its work; the resume
        # loop must not read ``outcome`` the instant ``serve_forever()``
        # returns, or it could observe a stale ``None``/pre-commit value.
        server = mock.Mock()
        calls = []

        def fake_serve_forever():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                self.p._set_draining(True)

                def delayed_outcome():
                    time.sleep(0.05)
                    self.p._HANDOFF_SESSION["outcome"] = "rolled_back"
                    self.p._HANDOFF_SESSION["outcome_ready"].set()

                threading.Thread(target=delayed_outcome, daemon=True).start()
            else:
                self.p._HANDOFF_SESSION["outcome"] = None
                self.p._HANDOFF_SESSION["outcome_ready"].set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p._serve_with_handoff_resume(server)
        self.assertEqual(server.serve_forever.call_count, 2, "resume loop did not wait for the delayed rollback outcome")

    def test_finalized_outcome_returns_without_serving_again(self):
        server = mock.Mock()

        def fake_serve_forever():
            self.p._HANDOFF_SESSION["outcome"] = "finalized"
            self.p._HANDOFF_SESSION["outcome_ready"].set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p._serve_with_handoff_resume(server)
        server.serve_forever.assert_called_once()

    def test_no_handoff_outcome_returns_without_serving_again(self):
        server = mock.Mock()

        def fake_serve_forever():
            self.p._HANDOFF_SESSION["outcome"] = None  # e.g. plain KeyboardInterrupt
            self.p._HANDOFF_SESSION["outcome_ready"].set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p._serve_with_handoff_resume(server)
        server.serve_forever.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Controller (control.py) reload / upgrade internal branching
# ---------------------------------------------------------------------------

class TestControllerHandoffWiring(unittest.TestCase):
    def _ctx(self, root: Path):
        install_dir = root / ".codex" / "dmx-proxy"
        return common.InstallContext(
            home=str(root),
            install_dir=str(install_dir),
            proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
            watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
            python=sys.executable,
            codex_config=str(root / ".codex" / "config.toml"),
            log_dir=str(root / ".codex" / "log"),
            port=8791,
        )

    def _expected(self, **overrides):
        expected = {
            "transaction_id": "txn-ctl",
            "release": "1.0.25",
            "source_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        }
        expected.update(overrides)
        return expected

    def _matching_runtime(self, expected, *, pid=1000, **overrides):
        runtime = {
            "pid": pid,
            "handoff_protocol_version": 2,
            "handoff_transaction_id": expected["transaction_id"],
            "release": expected["release"],
            "source_sha256": expected["source_sha256"],
            "payload_manifest_sha256": expected["manifest_sha256"],
            "accepting": True,
            "draining": False,
            "handoff_state": "serving",
        }
        runtime.update(overrides)
        return runtime

    def _idle_runtime(self, **overrides):
        runtime = {
            "pid": 999,
            "handoff_protocol_version": 2,
            "handoff_transaction_id": None,
            "handoff_state": "idle",
            "release": "1.0.24",
            "source_sha256": "a" * 64,
            "payload_manifest_sha256": "b" * 64,
            "accepting": True,
            "draining": False,
        }
        runtime.update(overrides)
        return runtime

    @staticmethod
    def _commit_side_effect(ctx, *, error=None):
        def commit(*_args, **_kwargs):
            Path(common.payload_transaction_dir(ctx), "rollback").mkdir(parents=True)
            if error is not None:
                raise error
        return commit

    def test_runtime_supports_handoff_requires_a_complete_idle_identity(self):
        self.assertTrue(control._runtime_supports_handoff(self._idle_runtime()))
        self.assertTrue(control._runtime_supports_handoff(self._idle_runtime(
            handoff_state="finalized",
            handoff_transaction_id="txn-previous-finalized",
        )))

    def test_runtime_supports_handoff_reports_false_for_legacy_or_unavailable_runtime(self):
        incomplete = self._idle_runtime()
        incomplete.pop("source_sha256")
        for runtime in (
            {"handoff_protocol_version": 1},
            {"handoff_protocol_version": 2},
            incomplete,
            self._idle_runtime(accepting=False),
            self._idle_runtime(draining=True),
            self._idle_runtime(handoff_state="ready"),
            {},
            None,
            {"release": "1.0.24"},
        ):
            with self.subTest(runtime=runtime):
                self.assertFalse(control._runtime_supports_handoff(runtime))

    def test_request_handoff_never_terminates_the_old_pid(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        listener_calls = {"n": 0}

        def fake_listener_pids(_ctx):
            listener_calls["n"] += 1
            return [999] if listener_calls["n"] == 1 else [1000]

        with (
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=fake_listener_pids),
            mock.patch.object(control, "_handoff_post", return_value={"status": "ready", "transaction_id": expected["transaction_id"], "child_pid": 1000}),
            mock.patch.object(control, "_runtime_metrics", return_value=self._matching_runtime(expected)),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control._request_handoff(ctx, expected, timeout_seconds=5)
        terminate.assert_not_called()
        self.assertEqual(result["old_pid"], 999)
        self.assertEqual(result["child_pid"], 1000)

    def test_request_handoff_requires_exactly_one_verified_old_listener(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with mock.patch.object(common, "verified_proxy_listener_pids", return_value=[888, 999]):
            with self.assertRaisesRegex(common.InstallError, "exactly one verified"):
                control._request_handoff(ctx, self._expected(), timeout_seconds=5)

    def test_request_handoff_surfaces_a_conflicting_in_progress_transaction_distinctly(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[999]),
            mock.patch.object(control, "_handoff_post", side_effect=common.InstallError("handoff control returned HTTP 409")),
        ):
            with self.assertRaisesRegex(common.InstallError, "409"):
                control._request_handoff(ctx, self._expected(), timeout_seconds=1)

    def test_handoff_post_requires_a_complete_protocol_v2_ready_acknowledgement(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()

        class Response:
            status = 202

            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return self.payload

        valid = {
            "ok": True,
            "state": "ready",
            "protocol_version": 2,
            "transaction_id": expected["transaction_id"],
            "child_pid": 1000,
        }
        opener = mock.Mock()
        with mock.patch.object(urllib.request, "build_opener", return_value=opener):
            opener.open.return_value = Response(valid)
            self.assertEqual(control._handoff_post(ctx, expected)["child_pid"], 1000)
            for field, bad_value in (
                ("ok", False),
                ("state", "preparing"),
                ("protocol_version", 1),
                ("transaction_id", "wrong"),
                ("child_pid", 0),
            ):
                with self.subTest(field=field):
                    opener.open.return_value = Response({**valid, field: bad_value})
                    with self.assertRaises(common.InstallError):
                        control._handoff_post(ctx, expected)

    def test_request_handoff_keeps_polling_through_a_transient_dual_listener_window(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        listener_calls = {"n": 0}

        def fake_listener_pids(_ctx):
            listener_calls["n"] += 1
            if listener_calls["n"] == 1:
                return [999]
            if listener_calls["n"] < 4:
                return [999, 1000]  # transient dual-accept: must not be accepted as "done"
            return [1000]

        with (
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=fake_listener_pids),
            mock.patch.object(control, "_handoff_post", return_value={"status": "ready", "transaction_id": expected["transaction_id"], "child_pid": 1000}),
            mock.patch.object(control, "_runtime_metrics", return_value=self._matching_runtime(expected)),
            mock.patch.object(control.time, "sleep"),
        ):
            result = control._request_handoff(ctx, expected, timeout_seconds=5)
        self.assertEqual(result["child_pid"], 1000)
        self.assertGreaterEqual(listener_calls["n"], 4)

    def test_request_handoff_rejects_a_wrong_child_pid_in_the_health_snapshot(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[999], [1000]]),
            mock.patch.object(control, "_handoff_post", return_value={"status": "ready", "transaction_id": expected["transaction_id"], "child_pid": 1000}),
            mock.patch.object(control, "_runtime_metrics", return_value=self._matching_runtime(expected, pid=4242)),
            mock.patch.object(control.time, "sleep"),
        ):
            with self.assertRaises(common.InstallError):
                control._request_handoff(ctx, expected, timeout_seconds=1)

    def test_request_handoff_rejects_each_runtime_field_mismatch(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        overrides = {
            "handoff_protocol_version": 1,
            "handoff_transaction_id": "wrong-txn",
            "release": "1.0.24",
            "source_sha256": "c" * 64,
            "payload_manifest_sha256": "d" * 64,
            "accepting": False,
            "draining": True,
            "handoff_state": "ready",
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                runtime = self._matching_runtime(expected, **{field: bad_value})
                with (
                    mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[999], [1000]]),
                    mock.patch.object(control, "_handoff_post", return_value={"status": "ready", "transaction_id": expected["transaction_id"], "child_pid": 1000}),
                    mock.patch.object(control, "_runtime_metrics", return_value=runtime),
                    mock.patch.object(control.time, "sleep"),
                ):
                    with self.assertRaises(common.InstallError):
                        control._request_handoff(ctx, expected, timeout_seconds=1)

    def test_failure_resolver_classifies_finalized_rolled_back_and_unknown_states(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        old = self._idle_runtime()
        finalized = self._matching_runtime(expected, pid=1000, handoff_state="finalized")
        cases = (
            ("finalized", [1000], finalized, ("finalized", finalized)),
            ("rolled_back", [999], old, ("rolled_back", old)),
        )
        for name, listeners, runtime, expected_result in cases:
            with self.subTest(name=name):
                with (
                    mock.patch.object(common, "verified_proxy_listener_pids", return_value=listeners),
                    mock.patch.object(control, "_runtime_metrics", return_value=runtime),
                ):
                    self.assertEqual(
                        control._resolve_handoff_after_controller_failure(
                            ctx, old, expected, timeout_seconds=1, lease_seconds=1,
                        ),
                        expected_result,
                    )
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[999, 1000]),
            mock.patch.object(control, "_runtime_metrics", return_value=finalized),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0, 8.0]),
            mock.patch.object(control.time, "sleep"),
        ):
            self.assertEqual(
                control._resolve_handoff_after_controller_failure(
                    ctx, old, expected, timeout_seconds=1, lease_seconds=1,
                ),
                ("unknown", None),
            )

    def test_reload_uses_handoff_without_terminating_the_old_pid_when_supported(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected()),
            mock.patch.object(control, "_request_handoff", return_value={"old_pid": 1, "child_pid": 2, "release": "1.0.25"}) as handoff,
            mock.patch.object(control, "_drain_listener_with_legacy_bootstrap") as legacy_drain,
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=5)
        handoff.assert_called_once()
        legacy_drain.assert_not_called()
        terminate.assert_not_called()
        self.assertEqual(result, {"old_pid": 1, "new_pid": 2})

    def test_reload_rejects_v2_handoff_when_installed_payload_integrity_fails(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(common, "verify_payload_manifest", return_value=(False, "hash mismatch")),
            mock.patch.object(control, "_request_handoff") as handoff,
        ):
            with self.assertRaisesRegex(common.InstallError, "integrity"):
                control.reload(ctx, timeout_seconds=5)
        handoff.assert_not_called()

    def test_reload_recovers_a_finalized_result_after_controller_failure(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        old = self._idle_runtime()
        finalized = self._matching_runtime(expected, pid=1000, handoff_state="finalized")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=old),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=expected),
            mock.patch.object(control, "_request_handoff", side_effect=KeyboardInterrupt()),
            mock.patch.object(
                control,
                "_resolve_handoff_after_controller_failure",
                return_value=("finalized", finalized),
            ),
        ):
            result = control.reload(ctx, timeout_seconds=5)
        self.assertEqual(result["new_pid"], 1000)
        self.assertTrue(result["recovered_after_controller_failure"])

    def test_reload_falls_back_to_legacy_drain_and_terminate_when_runtime_lacks_handoff_support(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"release": "1.0.24", "active_responses": 0, "draining": False}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=False),
            mock.patch.object(control, "_drain_listener_with_legacy_bootstrap", return_value={"listener": 12345, "runtime": {"draining": True, "active_responses": 0}}),
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[54321]]),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=0.1)
        terminate.assert_called_once_with(12345)
        self.assertEqual(result, {"old_pid": 12345, "new_pid": 54321})

    def test_upgrade_captures_handoff_capability_before_committing_the_staged_payload(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        order = []
        with (
            mock.patch.object(control, "_runtime_metrics", side_effect=lambda c: order.append("capability_read") or {"handoff_protocol_version": 2}),
            mock.patch.object(control, "_runtime_supports_handoff", side_effect=lambda runtime: order.append("capability_check") or True),
            mock.patch.object(common, "commit_payload_transaction", side_effect=lambda *a, **k: order.append("commit")),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected(release="1.0.25")),
            mock.patch.object(control, "_request_handoff", return_value={"old_pid": 1, "child_pid": 2, "release": "1.0.25"}),
            mock.patch.object(common, "finalize_payload_transaction"),
        ):
            control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        self.assertEqual(order[:3], ["capability_read", "capability_check", "commit"])

    def test_upgrade_commit_failure_uses_the_same_rollback_boundary(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=self._idle_runtime()),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(
                common,
                "commit_payload_transaction",
                side_effect=self._commit_side_effect(
                    ctx, error=common.InstallError("commit interrupted")
                ),
            ),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected(release="1.0.25")),
            mock.patch.object(control, "_request_handoff") as handoff,
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(control, "_wait_for_handoff_rollback") as wait_for_rollback,
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
        ):
            with self.assertRaisesRegex(common.InstallError, "commit interrupted"):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        handoff.assert_not_called()
        restore.assert_called_once_with(ctx)
        wait_for_rollback.assert_called_once()
        finalize.assert_called_once_with(ctx)

    def test_upgrade_rolls_back_and_finalizes_without_terminating_old_on_pre_finalize_failure(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(
                common,
                "commit_payload_transaction",
                side_effect=self._commit_side_effect(ctx),
            ),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected(release="1.0.25")),
            mock.patch.object(control, "_request_handoff", side_effect=common.InstallError("handoff health mismatch")),
            mock.patch.object(
                control,
                "_resolve_handoff_after_controller_failure",
                return_value=("rolled_back", None),
            ),
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(control, "_wait_for_handoff_rollback") as wait_for_rollback,
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            with self.assertRaises(common.InstallError):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        restore.assert_called_once_with(ctx)
        wait_for_rollback.assert_called_once()
        finalize.assert_called_once_with(ctx)
        terminate.assert_not_called()

    def test_upgrade_preserves_the_rollback_transaction_if_old_listener_does_not_resume(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(
                common,
                "commit_payload_transaction",
                side_effect=self._commit_side_effect(ctx),
            ),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected(release="1.0.25")),
            mock.patch.object(control, "_request_handoff", side_effect=common.InstallError("handoff health mismatch")),
            mock.patch.object(
                control,
                "_resolve_handoff_after_controller_failure",
                return_value=("rolled_back", None),
            ),
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(
                control,
                "_wait_for_handoff_rollback",
                side_effect=common.InstallError("old listener did not resume"),
            ),
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
        ):
            with self.assertRaisesRegex(common.InstallError, "old listener did not resume"):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        restore.assert_called_once_with(ctx)
        finalize.assert_not_called()

    def test_upgrade_keeps_new_payload_when_proxy_finalized_after_controller_failure(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        expected = self._expected(release="1.0.25")
        finalized_runtime = self._matching_runtime(expected, pid=222, handoff_state="finalized")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=self._idle_runtime()),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(common, "commit_payload_transaction"),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=expected),
            mock.patch.object(control, "_request_handoff", side_effect=KeyboardInterrupt()),
            mock.patch.object(
                control,
                "_resolve_handoff_after_controller_failure",
                return_value=("finalized", finalized_runtime),
            ),
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
        ):
            result = control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        restore.assert_not_called()
        finalize.assert_called_once_with(ctx)
        self.assertEqual(result["new_pid"], 222)
        self.assertTrue(result["recovered_after_controller_failure"])

    def test_upgrade_preserves_transaction_when_handoff_outcome_is_unknown(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=self._idle_runtime()),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=True),
            mock.patch.object(
                common,
                "commit_payload_transaction",
                side_effect=self._commit_side_effect(ctx),
            ),
            mock.patch.object(control, "_expected_handoff_metadata", return_value=self._expected(release="1.0.25")),
            mock.patch.object(control, "_request_handoff", side_effect=common.InstallError("timeout")),
            mock.patch.object(
                control,
                "_resolve_handoff_after_controller_failure",
                return_value=("unknown", None),
            ),
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
        ):
            with self.assertRaisesRegex(common.InstallError, "unconfirmed"):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        restore.assert_not_called()
        finalize.assert_not_called()
        self.assertTrue(Path(common.payload_transaction_dir(ctx), "rollback").is_dir())

        with (
            mock.patch.object(common, "commit_payload_transaction") as second_commit,
            mock.patch.object(common, "restore_payload_transaction") as second_restore,
        ):
            with self.assertRaisesRegex(common.InstallError, "preserved payload rollback"):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=5)
        second_commit.assert_not_called()
        second_restore.assert_not_called()

    def test_upgrade_legacy_runtime_preserves_the_existing_migration_path(self):
        # 1.0.24 predates handoff support entirely, so the migrating listener's
        # own health snapshot cannot advertise it; the capability probe must
        # read that as "unsupported" rather than raising on a missing key, and
        # the unchanged legacy drain/commit/terminate/watchdog body (through
        # ``_drain_listener_with_legacy_bootstrap``, the real call site) must
        # run.
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"release": "1.0.25"}),
            mock.patch.object(control, "_runtime_supports_handoff", return_value=False),
            mock.patch.object(control, "_drain_listener_with_legacy_bootstrap", return_value={"listener": 111}) as legacy_drain,
            mock.patch.object(common, "commit_payload_transaction") as commit,
            mock.patch.object(common, "terminate_pid") as terminate,
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[222]),
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
            mock.patch.object(control, "_request_handoff") as handoff,
        ):
            result = control.upgrade_from_stage(ctx, str(stage), timeout_seconds=1.0, allow_legacy_bootstrap=True)
        legacy_drain.assert_called_once()
        commit.assert_called_once_with(ctx, str(stage))
        terminate.assert_called_once_with(111)
        finalize.assert_called_once_with(ctx)
        handoff.assert_not_called()
        self.assertEqual(result, {"old_pid": 111, "new_pid": 222, "release": "1.0.25"})


# ---------------------------------------------------------------------------
# 8. Real subprocess integration (no blanket platform skip; no assertRaises)
# ---------------------------------------------------------------------------

class TestRealSubprocessHandoffIntegration(unittest.TestCase):
    """Owns and reliably terminates every subprocess/server it starts.

    Cleanups are appended in the order: temp-payload-directory removal FIRST,
    then everything else. ``tearDown`` runs them in reverse (LIFO), so the
    directory is always the *last* thing removed -- every owned child/old
    process must already be confirmed exited (and, on Windows, its open log
    file handle released) before the temporary payload it depended on is torn
    down.
    """

    def setUp(self):
        self._handoff_cleanups = []

    def tearDown(self):
        for cleanup in reversed(self._handoff_cleanups):
            try:
                cleanup()
            except Exception:
                pass

    def _addCleanupNow(self, fn):
        self._handoff_cleanups.append(fn)

    def _new_temp_root(self) -> Path:
        tmp_ctx = tempfile.TemporaryDirectory()
        # Registered first on purpose: reversed teardown order runs this last,
        # i.e. only after every process cleanup registered below has run.
        self._addCleanupNow(tmp_ctx.cleanup)
        return Path(tmp_ctx.name)

    def _child_takes_over_with_matching_health(self, port, expected, *, exclude_pid):
        try:
            _, health = _http_json(port, "/healthz", timeout=1)
        except (OSError, urllib.error.URLError, ValueError):
            return None
        if (
            isinstance(health.get("pid"), int)
            and health.get("pid") != exclude_pid
            and health.get("handoff_protocol_version") == proxy_module.HANDOFF_PROTOCOL_VERSION
            and health.get("handoff_transaction_id") == expected["transaction_id"]
            and health.get("release") == expected["release"]
            and health.get("source_sha256") == expected["source_sha256"]
            and health.get("payload_manifest_sha256") == expected["manifest_sha256"]
            and health.get("accepting") is True
        ):
            return health["pid"]
        return None

    def _post_responses(self, port, *, timeout=15):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=b'{"stream": false, "input": []}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            return response.read()

    def test_old_pid_serves_before_handoff_and_child_pid_serves_after(self):
        upstream = _ScriptedUpstream()
        self._addCleanupNow(upstream.close)
        upstream.push((200, b'{"id":"ok"}'))

        root = self._new_temp_root()
        port = _free_port()
        ctx = _write_installed_payload(root, release="1.0.25", port=port)
        log_path = root / "proxy.log"
        old = _start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: _terminate_process(old))

        status_code, before = _http_json(port, "/healthz")
        self.assertEqual(status_code, 200)
        self.assertEqual(before.get("pid"), old.pid)

        expected = _installed_expected_metadata(ctx, "txn-real-1")
        status_code, ready = _http_json(port, "/control/handoff", method="POST", body=expected, timeout=15)
        self.assertEqual(status_code, 202)
        self.assertEqual(ready.get("transaction_id"), expected["transaction_id"])
        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(_wait_until(observe, timeout=10), "child did not take over serving with matching health")
        self._addCleanupNow(lambda: _terminate_pid_best_effort(child_pid["value"]))
        self.assertTrue(_wait_until(lambda: old.poll() is not None, timeout=10), "old process did not exit after finalize")

    def test_finalized_child_can_drive_a_second_real_handoff(self):
        upstream = _ScriptedUpstream()
        self._addCleanupNow(upstream.close)
        root = self._new_temp_root()
        port = _free_port()
        ctx = _write_installed_payload(root, release="1.0.25", port=port)
        old = _start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self._addCleanupNow(lambda: _terminate_process(old))

        first = _installed_expected_metadata(ctx, "txn-repeat-1")
        status_code, _ready = _http_json(port, "/control/handoff", method="POST", body=first, timeout=15)
        self.assertEqual(status_code, 202)
        child_one = {"value": None}

        def observe_first():
            child_one["value"] = self._child_takes_over_with_matching_health(
                port, first, exclude_pid=old.pid,
            )
            return child_one["value"] is not None

        self.assertTrue(_wait_until(observe_first, timeout=10))
        self._addCleanupNow(lambda: _terminate_pid_best_effort(child_one["value"]))
        self.assertTrue(_wait_until(lambda: old.poll() is not None, timeout=10))

        second = _installed_expected_metadata(ctx, "txn-repeat-2")
        second_request = {**second, "lease_seconds": 1, "timeout_seconds": 3}
        status_code, _ready = _http_json(
            port, "/control/handoff", method="POST", body=second_request, timeout=15,
        )
        self.assertEqual(status_code, 202)
        child_two = {"value": None}

        def observe_second():
            child_two["value"] = self._child_takes_over_with_matching_health(
                port, second, exclude_pid=child_one["value"],
            )
            return child_two["value"] is not None

        self.assertTrue(_wait_until(observe_second, timeout=10))
        self._addCleanupNow(lambda: _terminate_pid_best_effort(child_two["value"]))
        retired = _wait_until(lambda: not _pid_alive(child_one["value"]), timeout=10)
        detail = common.process_command(child_one["value"]) if not retired else None
        self.assertTrue(
            retired,
            f"first finalized child did not retire after the second handoff: {detail!r}",
        )

    def test_long_upstream_response_completes_during_handoff_while_child_serves_and_old_exits_after(self):
        upstream = _ScriptedUpstream()
        self._addCleanupNow(upstream.close)
        started = threading.Event()
        release = threading.Event()

        def long_response(handler):
            started.set()
            release.wait(timeout=10)
            payload = b'{"id":"finished-late"}'
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        upstream.push(long_response)

        root = self._new_temp_root()
        port = _free_port()
        ctx = _write_installed_payload(root, release="1.0.25", port=port)
        log_path = root / "proxy.log"
        old = _start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: _terminate_process(old))

        held = {}

        def run_holder():
            held["body"] = self._post_responses(port)

        holder = threading.Thread(target=run_holder)
        holder.start()
        self._addCleanupNow(lambda: release.set())
        self.assertTrue(started.wait(timeout=10), "long upstream call did not start on the old process in time")

        expected = _installed_expected_metadata(ctx, "txn-real-2")
        status_code, ready = _http_json(port, "/control/handoff", method="POST", body=expected, timeout=15)
        self.assertEqual(status_code, 202)

        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(_wait_until(observe, timeout=10), "child did not take over serving with matching health")
        self._addCleanupNow(lambda: _terminate_pid_best_effort(child_pid["value"]))

        # The queue is now empty (the held request already popped its own
        # behavior before blocking on ``release``), so pushing exactly one new
        # behavior now deterministically belongs to the next request only.
        upstream.push((200, b'{"id":"new-via-child"}'))
        new_body = json.loads(self._post_responses(port, timeout=10))
        self.assertEqual(new_body.get("id"), "new-via-child")

        release.set()
        holder.join(timeout=15)
        self.assertEqual(held.get("body"), b'{"id":"finished-late"}')
        self.assertTrue(_wait_until(lambda: old.poll() is not None, timeout=10), "old process did not exit after the held response completed")

    def test_bounded_lease_forces_old_to_exit_even_if_a_held_stream_never_finishes(self):
        upstream = _ScriptedUpstream()
        self._addCleanupNow(upstream.close)
        started = threading.Event()
        never_release = threading.Event()

        def never_finishes(handler):
            started.set()
            never_release.wait(timeout=6)  # bounded so the test itself cannot hang
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"{}")

        upstream.push(never_finishes)

        root = self._new_temp_root()
        port = _free_port()
        ctx = _write_installed_payload(root, release="1.0.25", port=port)
        log_path = root / "proxy.log"
        old = _start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: _terminate_process(old))

        def hold_stream():
            try:
                self._post_responses(port, timeout=8)
            except Exception:
                pass

        holder = threading.Thread(target=hold_stream, daemon=True)
        holder.start()
        self._addCleanupNow(never_release.set)
        self.assertTrue(started.wait(timeout=10), "held stream did not start on the old process in time")

        expected = _installed_expected_metadata(ctx, "txn-real-3")
        expected["lease_seconds"] = 1
        status_code, ready = _http_json(port, "/control/handoff", method="POST", body=expected, timeout=15)
        self.assertEqual(status_code, 202)

        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(_wait_until(observe, timeout=10), "child did not take over serving with matching health")
        self._addCleanupNow(lambda: _terminate_pid_best_effort(child_pid["value"]))

        # Deterministic: the held request's behavior was already popped before
        # it blocked, so this new push belongs solely to the queued request below.
        upstream.push((200, b'{"id":"via-child-while-old-held"}'))
        queued_body = json.loads(self._post_responses(port, timeout=10))
        self.assertEqual(queued_body.get("id"), "via-child-while-old-held")

        self.assertTrue(
            _wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit despite the lease expiring on a held stream",
        )
        status_code, still_healthy = _http_json(port, "/healthz", timeout=3)
        self.assertEqual(status_code, 200)
        self.assertEqual(still_healthy.get("pid"), child_pid["value"])
        self.assertIs(still_healthy.get("accepting"), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
