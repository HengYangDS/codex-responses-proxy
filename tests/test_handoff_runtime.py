#!/usr/bin/env python3
"""Parent state, control handler, and serve/resume handoff contracts."""

from __future__ import annotations

import sys
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.handoff import HandoffTestCase
from tests.support.handoff import handoff_module
from tests.support.handoff import handoff_outcome_ready
from tests.support.handoff import proxy_module
from tests.support.handoff import runtime_state_module
from tests.support.handoff import wait_until
import control_surface


class TestParentHandoffStateMachine(HandoffTestCase):
    """Legal/illegal runtime behavior of the prepare -> commit -> finalize driver."""

    def _expected(self, **overrides):
        expected = {
            "transaction_id": "txn-1",
            "release": "1.0.25",
            "serving_payload_sha256": "a" * 64,
            "release_receipt_sha256": "f" * 64,
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
            "protocol_version": handoff_module.HANDOFF_PROTOCOL_VERSION,
            "pid": child.process.pid,
            "transaction_id": expected["transaction_id"],
            "release": expected["release"],
            "serving_payload_sha256": expected["serving_payload_sha256"],
            "release_receipt_sha256": expected["release_receipt_sha256"],
            "manifest_sha256": expected["manifest_sha256"],
        }

    def _serving_message(self, child, expected):
        return {
            "type": "serving",
            "pid": child.process.pid,
            "transaction_id": expected["transaction_id"],
        }

    def _finalized_message(self, child, expected):
        return {
            "type": "finalized",
            "pid": child.process.pid,
            "transaction_id": expected["transaction_id"],
        }

    def _happy_recv_sequence(self, child, expected):
        return [
            self._ready_message(child, expected),
            self._serving_message(child, expected),
            self._finalized_message(child, expected),
        ]

    def _matching_health(self, child, expected, *, handoff_state="serving"):
        return {
            "pid": child.process.pid,
            "handoff_protocol_version": handoff_module.HANDOFF_PROTOCOL_VERSION,
            "handoff_transaction_id": expected["transaction_id"],
            "release": expected["release"],
            "serving_payload_sha256": expected["serving_payload_sha256"],
            "release_receipt_sha256": expected["release_receipt_sha256"],
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
            mock.patch.object(self.p, "spawn_child", return_value=child) as spawn,
            mock.patch.object(
                self.p, "probe_health", return_value=self._matching_health(child, expected)
            ),
        ):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
            self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "ready")
            outcome = self.p.commit(server, prepared, self.context)
        spawn.assert_called_once()
        self.assertEqual(outcome, "finalized")
        server.shutdown.assert_called_once()
        child.send_message.assert_any_call({"type": "commit"})
        child.send_message.assert_any_call({"type": "finalize"})
        self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "finalized")
        self.assertTrue(handoff_outcome_ready().is_set())

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
        real_set_draining = self.context.set_draining

        def observing_set_draining(enabled, **kwargs):
            order.append(f"draining:{enabled}")
            return real_set_draining(enabled, **kwargs)

        observing_context = proxy_module._handoff_context()
        object.__setattr__(observing_context, "set_draining", observing_set_draining)
        with (
            mock.patch.object(self.p, "spawn_child", return_value=child),
            mock.patch.object(
                self.p, "probe_health", return_value=self._matching_health(child, expected)
            ),
        ):
            prepared = self.p.prepare(server, expected, observing_context, timeout_seconds=5)
            self.p.commit(server, prepared, observing_context)
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
                self.assertTrue(
                    shutdown_returned.is_set(), "commit sent before shutdown() returned"
                )

        child.send_message.side_effect = send_message
        child.recv_message.side_effect = self._happy_recv_sequence(child, expected)
        with (
            mock.patch.object(self.p, "spawn_child", return_value=child),
            mock.patch.object(
                self.p, "probe_health", return_value=self._matching_health(child, expected)
            ),
        ):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
            self.p.commit(server, prepared, self.context)

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
                self.p.prepare(server, expected, self.context, timeout_seconds=5)
            except self.p.HandoffError as exc:
                errors.append(exc)

        with mock.patch.object(self.p, "spawn_child", side_effect=slow_spawn):
            first = threading.Thread(
                target=self.p.prepare,
                args=(server, expected, self.context),
                kwargs={"timeout_seconds": 5},
            )
            first.start()
            self.assertTrue(
                wait_until(lambda: self.p._HANDOFF_SESSION.get("state") == "preparing", timeout=2)
            )
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
        with mock.patch.object(self.p, "spawn_child", side_effect=OSError("fork failed")):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=5)
        server.shutdown.assert_not_called()
        self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "idle")

    def test_child_ready_timeout_resets_to_idle_without_touching_admission(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = TimeoutError("no ready message")
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
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
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "e" * 64,
            "manifest_sha256": "d" * 64,
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                handoff_module.reset_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                message = dict(self._ready_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [message]
                with mock.patch.object(self.p, "spawn_child", return_value=child):
                    with self.assertRaises(self.p.HandoffError):
                        self.p.prepare(server, expected, self.context, timeout_seconds=1)
                server.shutdown.assert_not_called()
                child.terminate_bounded.assert_called_once()

    def test_ready_message_wrong_type_is_rejected(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        message = dict(self._ready_message(child, expected), type="hello")
        child.recv_message.side_effect = [message]
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
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
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
            outcome = self.p.commit(server, prepared, self.context)
        self.assertEqual(outcome, "rolled_back")
        server.shutdown.assert_called_once()  # shutdown already happened before commit
        child.terminate_bounded.assert_called_once()
        self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "rolled_back")
        self.assertTrue(handoff_outcome_ready().is_set())

    def test_serving_timeout_aborts_and_records_rollback(self):
        server = self._fake_server()
        child = self._fake_child()
        expected = self._expected()
        child.recv_message.side_effect = [
            self._ready_message(child, expected),
            TimeoutError("no serving message"),
        ]
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=1)
            outcome = self.p.commit(server, prepared, self.context)
        self.assertEqual(outcome, "rolled_back")
        child.terminate_bounded.assert_called_once()

    def test_serving_message_field_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        for field, bad_value in (("pid", 1), ("transaction_id", "wrong-txn")):
            with self.subTest(field=field):
                handoff_module.reset_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                serving = dict(self._serving_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [self._ready_message(child, expected), serving]
                with mock.patch.object(self.p, "spawn_child", return_value=child):
                    prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
                    outcome = self.p.commit(server, prepared, self.context)
                self.assertEqual(outcome, "rolled_back")
                child.terminate_bounded.assert_called_once()

    def test_health_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        overrides = {
            "pid": 1,
            "handoff_protocol_version": 1,
            "handoff_transaction_id": "txn-wrong",
            "release": "1.0.24",
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "e" * 64,
            "payload_manifest_sha256": "d" * 64,
            "handoff_state": "idle",
            "accepting": False,
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                handoff_module.reset_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                health = dict(self._matching_health(child, expected), **{field: bad_value})
                child.recv_message.side_effect = self._happy_recv_sequence(child, expected)[:2]
                with (
                    mock.patch.object(self.p, "spawn_child", return_value=child),
                    mock.patch.object(self.p, "probe_health", return_value=health),
                ):
                    prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
                    outcome = self.p.commit(server, prepared, self.context)
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
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
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
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=1)
            outcome = self.p.commit(server, prepared, self.context)
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
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
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
            mock.patch.object(self.p, "spawn_child", return_value=child),
            mock.patch.object(
                self.p, "probe_health", return_value=self._matching_health(child, expected)
            ),
        ):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
            outcome = self.p.commit(server, prepared, self.context)
        self.assertEqual(outcome, "rolled_back")
        child.terminate_bounded.assert_called_once()

    def test_finalized_message_field_mismatches_each_abort_and_record_rollback(self):
        expected = self._expected()
        for field, bad_value in (("pid", 1), ("transaction_id", "wrong-txn")):
            with self.subTest(field=field):
                handoff_module.reset_session_to_idle()
                server = self._fake_server()
                child = self._fake_child()
                finalized = dict(self._finalized_message(child, expected), **{field: bad_value})
                child.recv_message.side_effect = [
                    self._ready_message(child, expected),
                    self._serving_message(child, expected),
                    finalized,
                ]
                with (
                    mock.patch.object(self.p, "spawn_child", return_value=child),
                    mock.patch.object(
                        self.p, "probe_health", return_value=self._matching_health(child, expected)
                    ),
                ):
                    prepared = self.p.prepare(server, expected, self.context, timeout_seconds=5)
                    outcome = self.p.commit(server, prepared, self.context)
                self.assertEqual(outcome, "rolled_back")
                child.terminate_bounded.assert_called_once()


class TestHandoffControlHandler(unittest.TestCase):
    def setUp(self):
        self.bindings = control_surface.Bindings(
            runtime_status=proxy_module.runtime_status,
            handoff_context=proxy_module._handoff_context,
        )

    def _expected(self):
        return {
            "transaction_id": "txn-handler",
            "release": "1.0.25",
            "serving_payload_sha256": "a" * 64,
            "release_receipt_sha256": "e" * 64,
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
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(handoff_module, "prepare", return_value=prepared),
            mock.patch("threading.Thread") as thread_cls,
        ):
            thread_cls.return_value.start.side_effect = lambda: order.append("coordinator_started")
            control_surface.prepare_handoff(fake_self, self.bindings)
        self.assertEqual(order, ["write", "flush", "coordinator_started"])
        thread_cls.assert_called_once()
        _, kwargs = thread_cls.call_args
        self.assertEqual(kwargs.get("target"), handoff_module.commit)

    def test_handler_response_body_carries_child_pid_and_transaction_id(self):
        fake_self = self._fake_handler_self(self._expected())
        written = []
        fake_self.wfile.write.side_effect = lambda chunk: written.append(chunk)
        prepared = {"child": mock.Mock(process=mock.Mock(pid=999)), "expected": self._expected()}
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(handoff_module, "prepare", return_value=prepared),
            mock.patch("threading.Thread"),
        ):
            control_surface.prepare_handoff(fake_self, self.bindings)
        fake_self.send_response.assert_called_once_with(202)
        body = json.loads(b"".join(written))
        self.assertEqual(body.get("child_pid"), 999)
        self.assertEqual(body.get("transaction_id"), self._expected()["transaction_id"])

    def test_handler_rejects_non_loopback_clients(self):
        fake_self = self._fake_handler_self(self._expected())
        fake_self.client_address = ("10.0.0.5", 51234)
        with mock.patch.object(handoff_module, "prepare") as prepare:
            control_surface.prepare_handoff(fake_self, self.bindings)
        prepare.assert_not_called()
        fake_self.send_error.assert_called_once()
        self.assertEqual(fake_self.send_error.call_args.args[0], 403)

    def test_handler_returns_409_when_a_handoff_is_already_in_progress(self):
        fake_self = self._fake_handler_self(self._expected())
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(
                handoff_module,
                "prepare",
                side_effect=handoff_module.HandoffConflict("a handoff is already in progress"),
            ),
        ):
            control_surface.prepare_handoff(fake_self, self.bindings)
        fake_self.send_response.assert_called_once_with(409)


class TestServeWithHandoffResume(HandoffTestCase):
    def test_rollback_outcome_reopens_admission_and_serves_again_on_the_same_socket(self):
        server = mock.Mock()
        calls = []

        def fake_serve_forever():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                runtime_state_module.set_draining(True)
                self.p._HANDOFF_SESSION["outcome"] = "rolled_back"
                handoff_outcome_ready().set()
            else:
                self.p._HANDOFF_SESSION["outcome"] = None
                handoff_outcome_ready().set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p.serve_with_resume(server, self.context)
        self.assertEqual(server.serve_forever.call_count, 2)
        self.assertFalse(proxy_module.runtime_status()["draining"])

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
                runtime_state_module.set_draining(True)

                def delayed_outcome():
                    time.sleep(0.05)
                    self.p._HANDOFF_SESSION["outcome"] = "rolled_back"
                    handoff_outcome_ready().set()

                threading.Thread(target=delayed_outcome, daemon=True).start()
            else:
                self.p._HANDOFF_SESSION["outcome"] = None
                handoff_outcome_ready().set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p.serve_with_resume(server, self.context)
        self.assertEqual(
            server.serve_forever.call_count,
            2,
            "resume loop did not wait for the delayed rollback outcome",
        )

    def test_finalized_outcome_returns_without_serving_again(self):
        server = mock.Mock()

        def fake_serve_forever():
            self.p._HANDOFF_SESSION["outcome"] = "finalized"
            handoff_outcome_ready().set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p.serve_with_resume(server, self.context)
        server.serve_forever.assert_called_once()

    def test_no_handoff_outcome_returns_without_serving_again(self):
        server = mock.Mock()

        def fake_serve_forever():
            self.p._HANDOFF_SESSION["outcome"] = None  # e.g. plain KeyboardInterrupt
            handoff_outcome_ready().set()

        server.serve_forever.side_effect = fake_serve_forever
        self.p.serve_with_resume(server, self.context)
        server.serve_forever.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
