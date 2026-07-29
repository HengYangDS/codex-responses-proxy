#!/usr/bin/env python3
"""Rolling-handoff wire protocol, transition, and platform contracts."""

from __future__ import annotations

import base64
import io
import os
import json
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.handoff import handoff_module
from tests.support.handoff import http_json
from tests.support.handoff import proxy_module
from tests.support.handoff import runtime_state_module
from platform_adapters import control_handoff
import http_surface


class TestProtocolContract(unittest.TestCase):
    """The wire-level contract every other component below depends on."""

    def setUp(self):
        self.p = proxy_module
        runtime_state_module.reset_for_test()
        handoff_module.reset_session_to_idle()

    def test_proxy_declares_handoff_protocol_version_two(self):
        self.assertEqual(handoff_module.HANDOFF_PROTOCOL_VERSION, 2)

    def test_control_declares_matching_handoff_protocol_version(self):
        self.assertEqual(control_handoff.HANDOFF_PROTOCOL_VERSION, 2)

    def test_runtime_status_contains_full_handoff_health_shape(self):
        status = self.p.runtime_status()
        for key in (
            "pid",
            "handoff_protocol_version",
            "handoff_transaction_id",
            "handoff_state",
            "release",
            "serving_payload_sha256",
            "release_receipt_sha256",
            "payload_manifest_sha256",
            "accepting",
            "draining",
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
                handoff_module._HANDOFF_SESSION["state"] = state
                try:
                    status = self.p.runtime_status()
                    self.assertIs(status["draining"], False)
                    self.assertIs(status["accepting"], False)
                finally:
                    handoff_module.reset_session_to_idle()

    def test_idle_handoff_state_has_no_transaction_id(self):
        status = self.p.runtime_status()
        self.assertIn(status["handoff_state"], (None, "idle"))
        self.assertIsNone(status["handoff_transaction_id"])

    def test_healthz_over_real_loopback_http_exposes_the_same_shape(self):
        proxy = self.p.create_server(("127.0.0.1", 0))
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        try:
            status_code, payload = http_json(proxy.server_address[1], "/healthz")
            self.assertEqual(status_code, 200)
            for key in (
                "pid",
                "handoff_protocol_version",
                "handoff_transaction_id",
                "handoff_state",
                "payload_manifest_sha256",
                "accepting",
            ):
                self.assertIn(key, payload)
        finally:
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=2)


class TestHandoffTransitionValidation(unittest.TestCase):
    def setUp(self):
        self.p = handoff_module

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
                self.assertTrue(self.p.validate_transition(current, target))

    def test_allows_an_abort_escape_from_every_non_idle_non_finalized_state(self):
        for current in ("preparing", "ready", "committing", "serving", "finalizing"):
            with self.subTest(current=current):
                self.assertTrue(self.p.validate_transition(current, "aborting"))
        self.assertTrue(self.p.validate_transition("aborting", "rolled_back"))
        self.assertTrue(self.p.validate_transition("rolled_back", "idle"))

    def test_idle_and_finalized_have_no_abort_escape(self):
        self.assertFalse(self.p.validate_transition("idle", "aborting"))
        self.assertFalse(self.p.validate_transition("finalized", "aborting"))

    def test_rejects_skipping_states_in_the_happy_path(self):
        self.assertFalse(self.p.validate_transition("idle", "committing"))
        self.assertFalse(self.p.validate_transition("idle", "serving"))
        self.assertFalse(self.p.validate_transition("preparing", "committing"))
        self.assertFalse(self.p.validate_transition("ready", "serving"))
        self.assertFalse(self.p.validate_transition("committing", "finalizing"))

    def test_finalized_can_only_recycle_to_idle_for_the_next_transaction(self):
        self.assertFalse(self.p.validate_transition("finalized", "preparing"))
        self.assertFalse(self.p.validate_transition("finalized", "rolled_back"))
        self.assertTrue(self.p.validate_transition("finalized", "idle"))

    def test_rejects_direct_nonterminal_to_rolled_back_shortcuts(self):
        # Every non-idle, non-finalized phase must pass through ``aborting``
        # first; jumping straight to ``rolled_back`` is illegal.
        for current in ("idle", "preparing", "ready", "committing", "serving", "finalizing"):
            with self.subTest(current=current):
                self.assertFalse(self.p.validate_transition(current, "rolled_back"))

    def test_rejects_committing_directly_from_rolled_back(self):
        self.assertFalse(self.p.validate_transition("rolled_back", "committing"))


class TestHandoffPlatformHelpers(unittest.TestCase):
    def setUp(self):
        self.p = handoff_module

    def _expected(self):
        return {
            "transaction_id": "txn-platform",
            "release": "1.0.25",
            "serving_payload_sha256": "a" * 64,
            "release_receipt_sha256": "e" * 64,
            "manifest_sha256": "b" * 64,
        }

    def test_posix_kwargs_include_pass_fds_and_close_fds(self):
        kwargs = self.p.popen_kwargs(37, is_windows=False)
        self.assertEqual(kwargs.get("pass_fds"), (37,))
        self.assertTrue(kwargs.get("close_fds"))

    def test_windows_kwargs_omit_pass_fds_but_still_close_fds_and_pipe_stdio(self):
        kwargs = self.p.popen_kwargs(None, is_windows=True)
        self.assertNotIn("pass_fds", kwargs)
        self.assertTrue(kwargs.get("close_fds"))
        self.assertEqual(kwargs.get("stdin"), subprocess.PIPE)
        self.assertEqual(kwargs.get("stdout"), subprocess.PIPE)

    def test_posix_spawn_uses_the_listener_fileno_via_pass_fds(self):
        fake_process = mock.Mock(pid=4242, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.fileno.return_value = 37
        with mock.patch("subprocess.Popen", return_value=fake_process) as popen:
            child = self.p.spawn_child(
                listener, self._expected(), proxy_module._handoff_context(), is_windows=False
            )
        self.assertIs(child.process, fake_process)
        _, kwargs = popen.call_args
        self.assertEqual(kwargs.get("pass_fds"), (37,))
        self.assertTrue(kwargs.get("close_fds"))
        written = b"".join(call.args[0] for call in fake_process.stdin.write.call_args_list)
        self.assertNotIn(b"listener_share_b64", written)

    def test_windows_spawn_never_supplies_pass_fds_and_sends_share_bytes_only_as_base64_over_stdin(
        self,
    ):
        fake_process = mock.Mock(pid=5150, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.share = mock.Mock(return_value=b"opaque-share-bytes")
        with mock.patch("subprocess.Popen", return_value=fake_process) as popen:
            self.p.spawn_child(
                listener, self._expected(), proxy_module._handoff_context(), is_windows=True
            )
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
        with mock.patch.object(
            socket, "fromshare", create=True, return_value=fake_socket
        ) as fromshare:
            result = self.p.listener_from_prepare(message)
        fromshare.assert_called_once_with(b"share-bytes")
        self.assertIs(result, fake_socket)

    def test_posix_listener_from_handoff_prepare_uses_the_inherited_fd(self):
        fake_socket = mock.Mock()
        message = {"listener_fd": 37}
        with mock.patch.object(socket, "socket", return_value=fake_socket) as ctor:
            result = self.p.listener_from_prepare(message)
        ctor.assert_called_once_with(fileno=37)
        self.assertIs(result, fake_socket)

    def test_precommit_control_pipe_eof_closes_without_shutdown_deadlock(self):
        handoff_module.reset_session_to_idle()
        prepare = {
            "type": "prepare",
            "protocol_version": handoff_module.HANDOFF_PROTOCOL_VERSION,
            "transaction_id": "txn-eof",
            "release": proxy_module.release_version(),
            "serving_payload_sha256": proxy_module.serving_payload_sha256(),
            "release_receipt_sha256": proxy_module.release_receipt_sha256(),
            "manifest_sha256": self.p.payload_manifest_sha256(proxy_module._handoff_context()),
            "listener_fd": 37,
        }
        raw = json.dumps(prepare, separators=(",", ":")).encode() + b"\n"
        fake_stdin = mock.Mock(buffer=io.BytesIO(raw))
        fake_stdout = mock.Mock(buffer=io.BytesIO())
        fake_server = mock.Mock()
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch.object(sys, "stdout", fake_stdout),
            mock.patch.object(self.p, "listener_from_prepare", return_value=mock.Mock()),
            mock.patch.object(http_surface, "server_from_listener", return_value=fake_server),
        ):
            self.assertEqual(self.p.run_child(proxy_module._handoff_context()), 1)
        fake_server.shutdown.assert_not_called()
        fake_server.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
