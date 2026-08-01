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
from typing import cast
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.runtime.handoff.fixtures import expected_metadata
from tests.runtime.handoff.fixtures import handoff_module
from codex_responses_proxy.listener.handoff import protocol as handoff_protocol_module
from tests.runtime.handoff.fixtures import http_json
from tests.runtime.handoff.fixtures import entrypoint_module
from tests.runtime.handoff.fixtures import runtime_state_module
from codex_responses_proxy.deployment import handoff


class TestProtocolContract(unittest.TestCase):
    """The wire-level contract every other component below depends on."""

    def setUp(self):
        self.p = entrypoint_module
        runtime_state_module.reset_for_test()
        handoff_module.reset_session_to_idle()

    def test_parent_and_controller_declare_protocol_version_two(self):
        self.assertEqual(
            (handoff_module.HANDOFF_PROTOCOL_VERSION, handoff.HANDOFF_PROTOCOL_VERSION),
            (2, 2),
        )

    def test_runtime_status_contains_full_handoff_health_shape(self):
        status = self.p.runtime_status()
        required = (
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
        )
        self.assertEqual(set(required).difference(status), set())
        self.assertEqual(status["handoff_protocol_version"], 2)
        self.assertEqual(status["pid"], os.getpid())

    def test_runtime_status_reports_an_accepting_idle_state(self):
        status = self.p.runtime_status()
        self.assertEqual(
            (status["accepting"], status["draining"], status["handoff_transaction_id"]),
            (True, False, None),
        )
        self.assertIn(status["handoff_state"], (None, "idle"))

    def test_a_prepared_or_committing_child_window_is_not_draining_but_is_also_not_accepting(self):
        # ``accepting`` is not merely ``not draining``: a transaction that owns
        # the single-flight session but has not yet closed admission (draining
        # is still False) must still report itself as unavailable for a fresh
        # handoff/admission decision.
        def assert_unavailable(state):
            handoff_module._HANDOFF_SESSION["state"] = state
            try:
                status = self.p.runtime_status()
                self.assertEqual((status["draining"], status["accepting"]), (False, False))
            finally:
                handoff_module.reset_session_to_idle()

        for state in ("ready", "committing"):
            assert_unavailable(state)

    def test_healthz_over_real_loopback_http_exposes_the_same_shape(self):
        proxy = self.p.create_server(("127.0.0.1", 0))
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        try:
            status_code, payload = http_json(proxy.server_address[1], "/healthz")
            self.assertEqual(status_code, 200)
            required = (
                "pid",
                "handoff_protocol_version",
                "handoff_transaction_id",
                "handoff_state",
                "payload_manifest_sha256",
                "accepting",
            )
            self.assertEqual(set(required).difference(payload), set())
        finally:
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=2)


class TestHandoffTransitionValidation(unittest.TestCase):
    def test_transition_table_matches_the_documented_protocol(self):
        allowed = frozenset(
            (
                ("idle", "preparing"),
                ("preparing", "ready"),
                ("ready", "committing"),
                ("committing", "serving"),
                ("serving", "finalizing"),
                ("finalizing", "finalized"),
                ("finalized", "idle"),
                ("aborting", "rolled_back"),
                ("rolled_back", "idle"),
            )
            + tuple(
                (state, "aborting")
                for state in ("preparing", "ready", "committing", "serving", "finalizing")
            )
        )
        states = {state for transition in allowed for state in transition}
        results = {
            (current, target): handoff_module.validate_transition(current, target)
            for current in states
            for target in states
        }
        self.assertEqual({transition for transition, valid in results.items() if valid}, allowed)


class TestHandoffPlatformHelpers(unittest.TestCase):
    def setUp(self):
        self.p = handoff_protocol_module

    def test_platform_popen_kwargs_are_minimal_and_inherit_only_the_listener(self):
        posix = self.p.popen_kwargs(37, is_windows=False)
        windows = self.p.popen_kwargs(None, is_windows=True)
        self.assertEqual(posix["pass_fds"], (37,))
        self.assertNotIn("pass_fds", windows)
        projected = tuple(
            (kwargs["close_fds"], kwargs["stdin"], kwargs["stdout"]) for kwargs in (posix, windows)
        )
        self.assertEqual(projected, ((True, subprocess.PIPE, subprocess.PIPE),) * 2)
        with self.assertRaisesRegex(self.p.HandoffError, "requires a listener fd"):
            self.p.popen_kwargs(None, is_windows=False)

    def test_child_constructor_requires_both_control_pipes(self):
        def reject_pipes(pipes):
            process = mock.Mock(stdin=pipes[0], stdout=pipes[1])
            with self.assertRaisesRegex(self.p.HandoffError, "pipes are unavailable"):
                self.p.HandoffChild(process)

        for pipes in ((None, mock.Mock()), (mock.Mock(), None)):
            reject_pipes(pipes)

    def test_child_message_writer_rejects_invalid_oversized_and_broken_pipes(self):
        process = mock.Mock(stdin=mock.Mock(), stdout=mock.Mock())
        child = self.p.HandoffChild(process)
        with self.assertRaisesRegex(self.p.HandoffError, "must be an object"):
            child.send_message(cast("dict[str, object]", []))
        with self.assertRaisesRegex(self.p.HandoffError, "exceeds the control limit"):
            child.send_message({"value": "x" * self.p.HANDOFF_CONTROL_MAX_BYTES})
        process.stdin.write.side_effect = BrokenPipeError
        with self.assertRaisesRegex(self.p.HandoffError, "pipe write failed"):
            child.send_message({"type": "prepare"})

    def test_child_reader_projects_timeout_and_malformed_messages(self):
        def reject(case):
            raw, message = case
            process = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO(raw))
            child = self.p.HandoffChild(process)
            with self.assertRaisesRegex(self.p.HandoffError, message):
                child.recv_message(0.1)

        cases = (
            (b"", "control pipe closed"),
            (b"x" * (self.p.HANDOFF_CONTROL_MAX_BYTES + 1), "exceeds the control limit"),
            (b"{\n", "invalid JSON"),
            (b"[]\n", "must be an object"),
        )
        for case in cases:
            reject(case)

        process = mock.Mock(stdin=io.BytesIO(), stdout=mock.Mock())
        child = self.p.HandoffChild(process)
        child._reader_started = True
        with self.assertRaisesRegex(self.p.HandoffError, "response timed out"):
            child.recv_message(0)

        child = self.p.HandoffChild(
            mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO(b'{"type":"ready"}\n'))
        )
        self.assertEqual(child.recv_message(1), {"type": "ready"})
        child._start_reader()
        self.assertTrue(child._reader_started)

        broken = mock.Mock()
        broken.readline.side_effect = OSError
        child = self.p.HandoffChild(mock.Mock(stdin=io.BytesIO(), stdout=broken))
        with self.assertRaisesRegex(self.p.HandoffError, "pipe read failed"):
            child.recv_message(0.1)

    def test_bounded_child_shutdown_handles_already_exited_success_and_timeout(self):
        def verify(case):
            method, poll_result, poll_effect, wait, expected = case
            process = mock.Mock(stdin=mock.Mock(), stdout=mock.Mock())
            process.poll.return_value = poll_result
            process.poll.side_effect = poll_effect
            process.wait.side_effect = wait
            self.assertIs(getattr(self.p.HandoffChild(process), method)(0), expected)

        outcomes = (
            (0, None, None, True),
            (None, None, None, True),
            (None, [None, None], subprocess.TimeoutExpired("child", 0.01), False),
        )
        cases = (
            (method, poll_result, poll_effect, wait, expected)
            for method in ("terminate_bounded", "kill_bounded")
            for poll_result, poll_effect, wait, expected in outcomes
        )
        for case in cases:
            verify(case)

    def test_spawn_projects_only_the_platform_listener_capability(self):
        expected = expected_metadata(transaction_id="txn-platform", release_receipt_sha256="e" * 64)
        for is_windows, pid in ((False, 4242), (True, 5150)):
            with self.subTest(is_windows=is_windows):
                process = mock.Mock(pid=pid, stdin=mock.Mock(), stdout=mock.Mock())
                listener = mock.Mock()
                listener.fileno.return_value = 37
                listener.share.return_value = b"opaque-share-bytes"
                with mock.patch("subprocess.Popen", return_value=process) as popen:
                    child = self.p.spawn_child(
                        listener,
                        expected,
                        entrypoint_module._handoff_context(),
                        is_windows=is_windows,
                    )
                self.assertIs(child.process, process)
                args, kwargs = popen.call_args
                written = b"".join(call.args[0] for call in process.stdin.write.call_args_list)
                if is_windows:
                    self.assertNotIn("pass_fds", kwargs)
                    self.assertNotIn(b"opaque-share-bytes", str(args).encode())
                    self.assertNotIn("opaque-share-bytes", json.dumps(kwargs.get("env") or {}))
                    listener.share.assert_called_once_with(pid)
                    self.assertEqual(
                        base64.b64decode(json.loads(written.splitlines()[0])["listener_share_b64"]),
                        b"opaque-share-bytes",
                    )
                    continue
                self.assertEqual(kwargs["pass_fds"], (37,))
                self.assertNotIn(b"listener_share_b64", written)

    def test_windows_share_failure_terminates_the_owned_child(self):
        fake_process = mock.Mock(pid=5150, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.share.side_effect = OSError("sharing failed")
        with (
            mock.patch("subprocess.Popen", return_value=fake_process),
            mock.patch.object(
                self.p.HandoffChild, "terminate_bounded", return_value=True
            ) as terminate,
        ):
            with self.assertRaisesRegex(self.p.HandoffError, "listener sharing failed"):
                self.p.spawn_child(
                    listener,
                    expected_metadata(
                        transaction_id="txn-platform", release_receipt_sha256="e" * 64
                    ),
                    entrypoint_module._handoff_context(),
                    is_windows=True,
                )
        terminate.assert_called_once()

    def test_spawn_write_failure_escalates_from_terminate_to_kill(self):
        fake_process = mock.Mock(pid=4242, stdin=mock.Mock(), stdout=mock.Mock())
        listener = mock.Mock()
        listener.fileno.return_value = 37
        with (
            mock.patch("subprocess.Popen", return_value=fake_process),
            mock.patch.object(self.p.HandoffChild, "send_message", side_effect=BrokenPipeError),
            mock.patch.object(
                self.p.HandoffChild, "terminate_bounded", return_value=False
            ) as terminate,
            mock.patch.object(self.p.HandoffChild, "kill_bounded", return_value=True) as kill,
        ):
            with self.assertRaises(BrokenPipeError):
                self.p.spawn_child(
                    listener,
                    expected_metadata(
                        transaction_id="txn-platform", release_receipt_sha256="e" * 64
                    ),
                    entrypoint_module._handoff_context(),
                    is_windows=False,
                )
        terminate.assert_called_once()
        kill.assert_called_once()

    def test_listener_reconstruction_uses_the_platform_specific_projection(self):
        fake_socket = mock.Mock()
        share = base64.b64encode(b"share-bytes").decode("ascii")
        with mock.patch.object(socket, "fromshare", create=True, return_value=fake_socket) as ctor:
            self.assertIs(self.p.listener_from_prepare({"listener_share_b64": share}), fake_socket)
        ctor.assert_called_once_with(b"share-bytes")
        with mock.patch.object(socket, "socket", return_value=fake_socket) as ctor:
            self.assertIs(self.p.listener_from_prepare({"listener_fd": 37}), fake_socket)
        ctor.assert_called_once_with(fileno=37)

    def test_listener_reconstruction_rejects_invalid_platform_payloads(self):
        def reject(message):
            with self.assertRaises(self.p.HandoffError):
                self.p.listener_from_prepare(message)

        invalid = (
            {"listener_share_b64": 7},
            {"listener_share_b64": "x" * (self.p.HANDOFF_CONTROL_MAX_BYTES + 1)},
            {"listener_share_b64": "not base64!"},
            {"listener_fd": -1},
            {"listener_fd": "37"},
        )
        for message in invalid:
            reject(message)

    def test_control_message_helpers_reject_invalid_framing_and_round_trip(self):
        target = io.BytesIO()
        self.p.write_control_message(target, {"type": "commit"})
        self.assertEqual(
            self.p.read_control_message(io.BytesIO(target.getvalue())), {"type": "commit"}
        )

        def reject(case):
            raw, error = case
            with self.assertRaises(error):
                self.p.read_control_message(io.BytesIO(raw))

        invalid = (
            (b"", EOFError),
            (b"x" * (self.p.HANDOFF_CONTROL_MAX_BYTES + 1), self.p.HandoffError),
            (b"{\n", self.p.HandoffError),
            (b"[]\n", self.p.HandoffError),
        )
        for case in invalid:
            reject(case)
        with self.assertRaises(self.p.HandoffError):
            self.p.write_control_message(
                io.BytesIO(), {"value": "x" * self.p.HANDOFF_CONTROL_MAX_BYTES}
            )

    def test_child_protocol_accepts_finalize_and_rejects_invalid_commands(self):
        context = entrypoint_module._handoff_context()
        prepare = {
            "type": "prepare",
            "protocol_version": handoff_module.HANDOFF_PROTOCOL_VERSION,
            "transaction_id": "txn-child",
            "release": entrypoint_module.release_version(),
            "serving_payload_sha256": entrypoint_module.serving_payload_sha256(),
            "release_receipt_sha256": entrypoint_module.release_receipt_sha256(),
            "manifest_sha256": context.payload_manifest_sha256(),
            "listener_fd": 37,
        }

        def run(*commands, valid_prepare=True, server=None):
            handoff_module.reset_session_to_idle()
            first = prepare if valid_prepare else {**prepare, "protocol_version": 1}
            raw = b"".join(
                json.dumps(message, separators=(",", ":")).encode() + b"\n"
                for message in (first, *commands)
            )
            fake_stdin = mock.Mock(buffer=io.BytesIO(raw))
            fake_stdout = mock.Mock(buffer=io.BytesIO())
            fake_server = server or mock.Mock()
            object.__setattr__(context, "server_factory", lambda _listener: fake_server)
            with (
                mock.patch.object(sys, "stdin", fake_stdin),
                mock.patch.object(sys, "stdout", fake_stdout),
                mock.patch.object(
                    handoff_module, "listener_from_prepare", return_value=mock.Mock()
                ),
                mock.patch.object(handoff_module, "serve_with_resume"),
                mock.patch("threading.Thread") as thread_cls,
            ):
                result = handoff_module.run_child(context)
            self.assertEqual(
                thread_cls.return_value.start.call_count, int({"type": "commit"} in commands)
            )
            return (
                result,
                fake_server,
                [json.loads(line) for line in fake_stdout.buffer.getvalue().splitlines()],
            )

        result, server, messages = run({"type": "commit"}, {"type": "finalize"})
        self.assertEqual(result, 0)
        self.assertEqual(
            [message["type"] for message in messages], ["ready", "serving", "finalized"]
        )
        server.server_close.assert_not_called()

        for commands, valid_prepare in (
            ((), False),
            (({"type": "unexpected"},), True),
            (({"type": "commit"}, {"type": "abort"}), True),
            (({"type": "commit"}, {"type": "unexpected"}), True),
        ):
            with self.subTest(commands=commands, valid_prepare=valid_prepare):
                result, server, _ = run(*commands, valid_prepare=valid_prepare)
                self.assertEqual(result, 1)
                self.assertEqual(server.server_close.call_count, int(valid_prepare))

        failed = mock.Mock()
        failed.shutdown.side_effect = OSError
        failed.server_close.side_effect = OSError
        result, failed, _ = run({"type": "commit"}, {"type": "abort"}, server=failed)
        self.assertEqual(result, 1)
        failed.shutdown.assert_called_once()
        failed.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
