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
sys.path.insert(0, str(ROOT))

from tests.support.handoff import (
    HandoffTestCase,
    child_message,
    child_pid_matching_health,
    entrypoint_module,
    expected_metadata,
    fake_child,
    fake_handler,
    fake_server,
    handoff_module,
    handoff_outcome_ready,
    matching_health,
    runtime_state_module,
    wait_until,
)
from codex_dmx_proxy.listener import control


class TestSuccessorHealthObservation(unittest.TestCase):
    """Exact successor states accepted by the subprocess health observer."""

    def test_successor_observer_accepts_the_stable_finalized_health_state(self):
        expected = expected_metadata()
        health = matching_health(54321, expected, handoff_state="finalized")

        with mock.patch("tests.support.handoff.http_json", return_value=(200, health)):
            observed = child_pid_matching_health(8791, expected, exclude_pid=12345)

        self.assertEqual(observed, 54321)

    def test_successor_observer_rejects_non_successor_health(self):
        expected = expected_metadata()
        cases = (
            matching_health(54321, expected, handoff_state="idle"),
            matching_health(54321, expected, release="wrong-release"),
            matching_health(0, expected),
            matching_health(True, expected),
        )

        for health in cases:
            with (
                self.subTest(health=health),
                mock.patch("tests.support.handoff.http_json", return_value=(200, health)),
            ):
                self.assertIsNone(child_pid_matching_health(8791, expected, exclude_pid=12345))


class TestParentHandoffStateMachine(HandoffTestCase):
    """Legal/illegal runtime behavior of the prepare -> commit -> finalize driver."""

    def committed(self, *after_ready, health=None, **kwargs):
        expected = kwargs.pop("expected", expected_metadata())
        child = kwargs.pop("child", fake_child())
        server = kwargs.pop("server", fake_server())
        child.recv_message.side_effect = [child_message("ready", child, expected), *after_ready]
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context, **kwargs)
        with mock.patch.object(
            self.p,
            "probe_health",
            return_value=matching_health(child, expected) if health is None else health,
        ):
            outcome = self.p.commit(server, prepared, self.context)
        return outcome, server, child, expected

    def test_prepare_then_commit_finalizes_and_never_reopens_admission_itself(self):
        child = fake_child()
        expected = expected_metadata()
        outcome, server, _, _ = self.committed(
            child_message("serving", child, expected),
            child_message("finalized", child, expected),
            child=child,
            expected=expected,
            timeout_seconds=5,
        )
        self.assertEqual(outcome, "finalized")
        server.shutdown.assert_called_once()
        child.send_message.assert_any_call({"type": "commit"})
        child.send_message.assert_any_call({"type": "finalize"})
        self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "finalized")
        self.assertTrue(handoff_outcome_ready().is_set())

    def test_draining_is_set_before_shutdown_and_shutdown_completes_before_commit_is_sent(self):
        server = fake_server()
        child = fake_child()
        expected = expected_metadata()
        order = []
        server.shutdown.side_effect = lambda: order.append("shutdown")

        def send_message(message):
            order.append(f"send:{message.get('type')}")

        child.send_message.side_effect = send_message
        child.recv_message.side_effect = [
            child_message("ready", child, expected),
            child_message("serving", child, expected),
            child_message("finalized", child, expected),
        ]
        real_set_draining = self.installation.set_draining

        def observing_set_draining(enabled, **kwargs):
            order.append(f"draining:{enabled}")
            return real_set_draining(enabled, **kwargs)

        observing_context = entrypoint_module._handoff_context()
        object.__setattr__(observing_context, "set_draining", observing_set_draining)
        with (
            mock.patch.object(self.p, "spawn_child", return_value=child),
            mock.patch.object(
                self.p, "probe_health", return_value=matching_health(child, expected)
            ),
        ):
            prepared = self.p.prepare(server, expected, observing_context, timeout_seconds=5)
            self.p.commit(server, prepared, observing_context)
        self.assertIn("draining:True", order)
        self.assertLess(order.index("draining:True"), order.index("shutdown"))
        self.assertLess(order.index("shutdown"), order.index("send:commit"))

    def test_simultaneous_handoff_is_rejected(self):
        server = fake_server()
        expected = expected_metadata()
        release_spawn = threading.Event()
        child = fake_child()
        child.recv_message.side_effect = [child_message("ready", child, expected)]

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

    def test_prepare_rejects_incomplete_identity_and_recycles_finalized_session(self):
        server = fake_server()
        for expected in ({}, {**expected_metadata(), "release": ""}):
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(self.p.HandoffError, "identity is incomplete"),
            ):
                self.p.prepare(server, expected, self.context)

        child = fake_child()
        expected = expected_metadata(transaction_id="txn-recycled")
        child.recv_message.return_value = child_message("ready", child, expected)
        self.p._HANDOFF_SESSION["state"] = "finalized"
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context)
        self.assertEqual(prepared["expected"], expected)
        self.assertEqual(self.p._HANDOFF_SESSION["state"], "ready")

    def test_transition_and_disk_identity_helpers_fail_closed(self):
        self.p._HANDOFF_SESSION["state"] = "idle"
        with self.assertRaisesRegex(self.p.HandoffError, "illegal handoff transition"):
            self.p._transition("serving")

        expected = {
            "release": entrypoint_module.release_version(),
            "serving_payload_sha256": entrypoint_module.serving_payload_sha256(),
            "release_receipt_sha256": entrypoint_module.release_receipt_sha256(),
            "manifest_sha256": self.p.payload_manifest_sha256(self.context),
        }
        self.assertTrue(self.p.disk_payload_matches_expected(expected, self.context))
        self.assertFalse(
            self.p.disk_payload_matches_expected({**expected, "release": "wrong"}, self.context)
        )
        missing_context = entrypoint_module._handoff_context()
        object.__setattr__(missing_context, "proxy_script", Path("/missing/proxy/dmx.py"))
        self.assertIsNone(self.p.payload_manifest_sha256(missing_context))

        self.p._HANDOFF_SESSION.update(state="ready", transaction_id="txn-identity")
        identity = self.p.runtime_identity(self.context)
        self.assertFalse(identity["accepting"])
        self.assertEqual(identity["handoff_transaction_id"], "txn-identity")

    def test_probe_health_rejects_oversized_invalid_and_non_object_payloads(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        opener = mock.Mock(open=mock.Mock(return_value=response))
        with mock.patch.object(self.p.urllib.request, "build_opener", return_value=opener):
            for payload, error in (
                (b"x" * (self.p.HANDOFF_CONTROL_MAX_BYTES + 1), "exceeds the control limit"),
                (b"{", "response is invalid"),
                (b"[]", "must be an object"),
            ):
                with self.subTest(error=error), self.assertRaisesRegex(self.p.HandoffError, error):
                    response.read.return_value = payload
                    self.p.probe_health(8791, timeout_seconds=1)
            response.read.return_value = b'{"ok":true}'
            self.assertEqual(self.p.probe_health(8791, timeout_seconds=1), {"ok": True})

    def test_prepare_failures_never_cross_admission_and_reset_when_child_exit_is_confirmed(self):
        expected = expected_metadata()
        for name, spawn_result in (
            ("spawn", OSError("fork failed")),
            ("ready timeout", TimeoutError("no ready message")),
        ):
            with self.subTest(case=name):
                handoff_module.reset_session_to_idle()
                server = fake_server()
                child = fake_child()
                child.recv_message.side_effect = spawn_result
                options = (
                    {"side_effect": spawn_result} if name == "spawn" else {"return_value": child}
                )
                with (
                    mock.patch.object(self.p, "spawn_child", **options),
                    self.assertRaises(self.p.HandoffError),
                ):
                    self.p.prepare(server, expected, self.context, timeout_seconds=1)
                server.shutdown.assert_not_called()
                self.assertEqual(self.p._HANDOFF_SESSION.get("state"), "idle")
                self.assertEqual(child.terminate_bounded.call_count, int(name != "spawn"))

    def test_commit_failures_roll_back_after_the_accept_barrier(self):
        child = fake_child()
        cases = (
            ("commit pipe", (), BrokenPipeError("commit pipe failed")),
            ("serving timeout", (TimeoutError("no serving message"),), None),
            ("serving pid", ({"type": "serving", "pid": 1, "transaction_id": "txn-1"},), None),
            (
                "serving transaction",
                ({"type": "serving", "pid": child.process.pid, "transaction_id": "wrong-txn"},),
                None,
            ),
        )
        for name, messages, send_failure in cases:
            with self.subTest(case=name):
                handoff_module.reset_session_to_idle()
                child = fake_child()
                child.send_message.side_effect = send_failure
                outcome, server, child, _ = self.committed(
                    *messages, child=child, timeout_seconds=1
                )
                self.assertEqual(outcome, "rolled_back")
                server.shutdown.assert_called_once()
                child.terminate_bounded.assert_called_once()
                self.assertEqual(self.p._HANDOFF_SESSION.get("outcome"), "rolled_back")
                self.assertTrue(handoff_outcome_ready().is_set())

    def test_identity_matrices_reject_ready_serving_health_and_finalized_mismatches(self):
        expected = expected_metadata()
        child = fake_child()
        fields = {
            "ready": {
                "protocol_version": 1,
                "pid": 999999,
                "transaction_id": "wrong-txn",
                "release": "1.0.24",
                "serving_payload_sha256": "c" * 64,
                "release_receipt_sha256": "e" * 64,
                "manifest_sha256": "d" * 64,
            },
            "serving": {"pid": 1, "transaction_id": "wrong-txn"},
            "health": {
                "pid": 1,
                "handoff_protocol_version": 1,
                "handoff_transaction_id": "txn-wrong",
                "release": "1.0.24",
                "serving_payload_sha256": "c" * 64,
                "release_receipt_sha256": "e" * 64,
                "payload_manifest_sha256": "d" * 64,
                "handoff_state": "idle",
                "accepting": False,
            },
            "finalized": {"pid": 1, "transaction_id": "wrong-txn"},
        }
        for stage, overrides in fields.items():
            for field, bad_value in overrides.items():
                with self.subTest(stage=stage, field=field):
                    handoff_module.reset_session_to_idle()
                    child = fake_child()
                    message = {
                        **child_message(stage if stage != "health" else "serving", child, expected),
                        **{field: bad_value},
                    }
                    if stage == "ready":
                        child.recv_message.side_effect = [message]
                        with (
                            mock.patch.object(self.p, "spawn_child", return_value=child),
                            self.assertRaises(self.p.HandoffError),
                        ):
                            self.p.prepare(fake_server(), expected, self.context, timeout_seconds=1)
                        child.terminate_bounded.assert_called_once()
                        continue
                    after_ready = [child_message("serving", child, expected)]
                    health = matching_health(child, expected)
                    after_ready = [message] if stage == "serving" else after_ready
                    health = {**health, field: bad_value} if stage == "health" else health
                    after_ready += [message] * (stage == "finalized")
                    outcome, _, child, _ = self.committed(
                        *after_ready, child=child, health=health, timeout_seconds=1
                    )
                    self.assertEqual(outcome, "rolled_back")
                    child.terminate_bounded.assert_called_once()

    def test_health_identity_allows_observability_fields(self):
        expected = expected_metadata()
        child = fake_child()
        health = {
            **matching_health(child, expected),
            "uptime_seconds": 12.5,
            "active_responses": 0,
            "active_handlers": 1,
            "counters": {},
            "upstream_classifications": {},
            "last_failure": None,
        }
        outcome, _, child, _ = self.committed(
            child_message("serving", child, expected),
            child_message("finalized", child, expected),
            child=child,
            expected=expected,
            health=health,
            timeout_seconds=1,
        )
        self.assertEqual(outcome, "finalized")
        child.terminate_bounded.assert_not_called()

    def test_abort_falls_back_to_kill_when_terminate_does_not_exit_child_in_time(self):
        server = fake_server()
        child = fake_child()
        expected = expected_metadata()
        child.recv_message.side_effect = TimeoutError("no ready message")
        child.terminate_bounded.return_value = False  # terminate alone was insufficient
        child.kill_bounded = mock.Mock(return_value=True)
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
        child.terminate_bounded.assert_called_once()
        child.kill_bounded.assert_called_once()

    def test_unconfirmed_abort_never_reports_a_resumable_rollback(self):
        server = fake_server()
        child = fake_child()
        expected = expected_metadata()
        child.recv_message.side_effect = [
            child_message("ready", child, expected),
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

    def test_abort_swallows_control_and_shutdown_errors_but_requires_confirmed_exit(self):
        child = fake_child()
        child.send_message.side_effect = BrokenPipeError
        child.terminate_bounded.side_effect = OSError
        child.kill_bounded.return_value = True
        self.p._HANDOFF_SESSION["state"] = "serving"
        self.p.abort(child)
        self.assertEqual(self.p._HANDOFF_SESSION["state"], "rolled_back")

        child = fake_child()
        child.terminate_bounded.side_effect = OSError
        child.kill_bounded.side_effect = OSError
        self.p._HANDOFF_SESSION["state"] = "serving"
        with self.assertRaisesRegex(self.p.HandoffError, "could not be confirmed exited"):
            self.p.abort(child)

    def test_unconfirmed_precommit_abort_stays_fail_closed_instead_of_returning_idle(self):
        server = fake_server()
        child = fake_child()
        expected = expected_metadata()
        child.recv_message.side_effect = TimeoutError("no ready message")
        child.terminate_bounded.return_value = False
        child.kill_bounded = mock.Mock(return_value=False)
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            with self.assertRaises(self.p.HandoffError):
                self.p.prepare(server, expected, self.context, timeout_seconds=1)
        self.assertEqual(self.p._HANDOFF_SESSION["state"], "aborting")

    def test_internal_fail_closed_branches_are_bounded(self):
        expected = expected_metadata()
        server = fake_server()
        child = fake_child()
        child.send_message.side_effect = BrokenPipeError
        child.terminate_bounded.return_value = True
        server.socket.fileno.return_value = 37
        with (
            mock.patch.object(self.p.subprocess, "Popen", return_value=mock.Mock()),
            mock.patch.object(self.p, "HandoffChild", return_value=child),
        ):
            with self.assertRaises(BrokenPipeError):
                self.p.spawn_child(server.socket, expected, self.context, is_windows=False)
        child.kill_bounded.assert_not_called()

        self.p._HANDOFF_SESSION["state"] = "idle"
        self.p.abort(fake_child())
        self.assertEqual(self.p._HANDOFF_SESSION["state"], "idle")

        self.p._HANDOFF_SESSION["outcome_ready"] = object()
        self.p._set_outcome("rolled_back")
        self.assertEqual(self.p._HANDOFF_SESSION["outcome"], "rolled_back")

        invalid_context = entrypoint_module._handoff_context()
        self.assertFalse(self.p._valid_prepare([], invalid_context))

        child = fake_child()
        child.recv_message.return_value = child_message("ready", child, expected)
        with mock.patch.object(self.p, "spawn_child", return_value=child):
            prepared = self.p.prepare(server, expected, self.context, timeout_seconds=1)
        child.send_message.side_effect = BrokenPipeError
        child.terminate_bounded.return_value = False
        child.kill_bounded.return_value = False
        server.shutdown.side_effect = OSError
        outcome = self.p.commit(server, prepared, self.context)
        self.assertEqual(outcome, "abort_unconfirmed")


class TestHandoffControlHandler(unittest.TestCase):
    def setUp(self):
        self.bindings = control.Bindings(
            runtime_status=entrypoint_module.runtime_status,
            handoff_context=entrypoint_module._handoff_context,
        )

    def test_handler_acknowledges_ready_before_starting_the_commit_coordinator(self):
        order = []
        handler = fake_handler(expected_metadata())
        handler.wfile.write.side_effect = lambda chunk: order.append(("write", chunk))
        handler.wfile.flush.side_effect = lambda: order.append(("flush", None))
        expected = expected_metadata()
        prepared = {"child": mock.Mock(process=mock.Mock(pid=999)), "expected": expected}
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(handoff_module, "prepare", return_value=prepared),
            mock.patch("threading.Thread") as thread_cls,
        ):
            thread_cls.return_value.start.side_effect = lambda: order.append(("start", None))
            control.prepare_handoff(handler, self.bindings)
        body = json.loads(order[0][1])
        self.assertEqual([event for event, _ in order], ["write", "flush", "start"])
        self.assertEqual(
            (handler.send_response.call_args.args[0], body["child_pid"], body["transaction_id"]),
            (202, 999, expected["transaction_id"]),
        )
        self.assertEqual(thread_cls.call_args.kwargs["target"], handoff_module.commit)

    def test_handler_rejects_non_loopback_clients(self):
        handler = fake_handler(expected_metadata())
        handler.client_address = ("10.0.0.5", 51234)
        with mock.patch.object(handoff_module, "prepare") as prepare:
            control.prepare_handoff(handler, self.bindings)
            prepare.assert_not_called()
        self.assertEqual(handler.send_error.call_args.args[0], 403)

    def test_handler_returns_409_when_a_handoff_is_already_in_progress(self):
        fake_self = fake_handler(expected_metadata())
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(
                handoff_module,
                "prepare",
                side_effect=handoff_module.HandoffConflict("a handoff is already in progress"),
            ),
        ):
            control.prepare_handoff(fake_self, self.bindings)
        fake_self.send_response.assert_called_once_with(409)

    def test_drain_control_enforces_loopback_and_projects_the_lease(self):
        remote = fake_handler({})
        remote.client_address = ("198.51.100.7", 51234)
        with mock.patch.object(runtime_state_module, "set_draining") as set_draining:
            control.set_drain(remote, True)
        set_draining.assert_not_called()
        remote.send_error.assert_called_once_with(
            403, "drain control is available only from loopback"
        )

        local = fake_handler({})
        local.headers["X-DMX-Drain-Lease-Seconds"] = "41"
        with mock.patch.object(
            runtime_state_module,
            "set_draining",
            return_value={"draining": True, "drain_generation": 1},
        ) as set_draining:
            control.set_drain(local, True)
        set_draining.assert_called_once_with(True, lease_seconds="41")
        local.send_response.assert_called_once_with(200)

        reopened = fake_handler({})
        with mock.patch.object(
            runtime_state_module,
            "set_draining",
            return_value={"draining": False, "drain_generation": 2},
        ) as set_draining:
            control.set_drain(reopened, False)
        set_draining.assert_called_once_with(False, lease_seconds=None)

    def test_status_control_serializes_the_bound_runtime_snapshot(self):
        fake_self = fake_handler({})
        bindings = control.Bindings(
            runtime_status=lambda: {"ok": True, "pid": 42},
            handoff_context=entrypoint_module._handoff_context,
        )
        control.send_status(fake_self, bindings)
        fake_self.send_response.assert_called_once_with(200)
        self.assertEqual(
            json.loads(fake_self.wfile.write.call_args.args[0]), {"ok": True, "pid": 42}
        )

    def test_handler_rejects_invalid_control_envelopes_before_prepare(self):
        cases = (
            ({"Content-Length": "not-an-int"}, b"{}", 400),
            ({"Content-Length": "0"}, b"", 413),
            (
                {"Content-Length": str(handoff_module.HANDOFF_CONTROL_MAX_BYTES + 1)},
                b"",
                413,
            ),
            ({"Content-Length": "2"}, b"{", 400),
            ({"Content-Length": "1"}, b"{", 400),
            ({"Content-Length": "2"}, b"[]", 400),
        )
        for headers, raw, expected_status in cases:
            with self.subTest(headers=headers, raw=raw):
                fake_self = fake_handler({})
                fake_self.headers = headers
                fake_self.rfile.read.return_value = raw
                with mock.patch.object(handoff_module, "prepare") as prepare:
                    control.prepare_handoff(fake_self, self.bindings)
                prepare.assert_not_called()
                fake_self.send_error.assert_called_once()
                self.assertEqual(fake_self.send_error.call_args.args[0], expected_status)

        unknown = fake_handler({**expected_metadata(), "unexpected": True})
        with mock.patch.object(handoff_module, "prepare") as prepare:
            control.prepare_handoff(unknown, self.bindings)
            prepare.assert_not_called()
        unknown.send_error.assert_called_once_with(400, "handoff request contains unknown fields")

    def test_handler_rejects_disk_mismatch_and_projects_non_conflict_prepare_failure(self):
        mismatch = fake_handler(expected_metadata())
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=False),
            mock.patch.object(handoff_module, "prepare") as prepare,
        ):
            control.prepare_handoff(mismatch, self.bindings)
            prepare.assert_not_called()
        mismatch.send_error.assert_called_once_with(
            409, "handoff request does not match the current disk payload"
        )

        failed = fake_handler(
            {**expected_metadata(), "timeout_seconds": "999", "lease_seconds": "17"}
        )
        written = []
        failed.wfile.write.side_effect = written.append
        with (
            mock.patch.object(handoff_module, "disk_payload_matches_expected", return_value=True),
            mock.patch.object(
                handoff_module,
                "prepare",
                side_effect=handoff_module.HandoffError("child failed"),
            ) as prepare,
        ):
            control.prepare_handoff(failed, self.bindings)
        self.assertEqual(prepare.call_args.kwargs["timeout_seconds"], 120.0)
        self.assertEqual(prepare.call_args.kwargs["lease_seconds"], 17)
        failed.send_response.assert_called_once_with(503)
        self.assertEqual(json.loads(b"".join(written))["error"], "handoff_prepare_failed")


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
        self.assertFalse(entrypoint_module.runtime_status()["draining"])

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

    def test_terminal_outcomes_stop_serving_and_log_only_unconfirmed_states(self):
        for outcome, expected_log in (
            ("finalized", None),
            (None, None),
            ("abort_unconfirmed", "handoff_abort_unconfirmed"),
            ("unknown", "handoff_outcome_unconfirmed"),
        ):
            with self.subTest(outcome=outcome):
                self.p.reset_session_to_idle()
                logs = []
                context = entrypoint_module._handoff_context()
                object.__setattr__(context, "log", logs.append)
                server = mock.Mock()

                def serve():
                    self.p._HANDOFF_SESSION["outcome"] = outcome
                    handoff_outcome_ready().set()

                server.serve_forever.side_effect = serve
                self.p.serve_with_resume(server, context)
                server.serve_forever.assert_called_once()
                self.assertEqual(bool(logs and expected_log in logs[0]), bool(expected_log))

    def test_finalized_outcome_waits_for_active_work_until_deadline(self):
        server = mock.Mock()
        active = iter((2, 0))
        context = entrypoint_module._handoff_context()
        object.__setattr__(context, "active_responses", lambda: next(active))
        object.__setattr__(context, "active_handlers", lambda: 0)
        logs = []
        object.__setattr__(context, "log", logs.append)

        server.serve_forever.side_effect = lambda: (
            self.p._HANDOFF_SESSION.update(
                outcome="finalized", drain_deadline=time.monotonic() + 10
            ),
            handoff_outcome_ready().set(),
        )
        with mock.patch.object(self.p.time, "sleep", return_value=None):
            self.p.serve_with_resume(server, context)
        self.assertEqual(logs, [])

        context = entrypoint_module._handoff_context()
        object.__setattr__(context, "active_responses", lambda: 3)
        object.__setattr__(context, "active_handlers", lambda: 0)
        logs = []
        object.__setattr__(context, "log", logs.append)
        self.p._HANDOFF_SESSION.update(outcome="finalized", drain_deadline=time.monotonic() - 1)
        server.serve_forever.side_effect = lambda: handoff_outcome_ready().set()
        self.p.serve_with_resume(server, context)
        self.assertIn("remaining_active=3", logs[0])

    def test_initial_serving_thread_is_joined_before_outcome_projection(self):
        initial = mock.Mock()
        server = mock.Mock()
        self.p._HANDOFF_SESSION.update(outcome=None, state="idle")
        self.p.serve_with_resume(server, self.context, initial_serving_thread=initial)
        initial.join.assert_called_once()
        server.serve_forever.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
