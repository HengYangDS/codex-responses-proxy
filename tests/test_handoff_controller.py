#!/usr/bin/env python3
"""Installed same-payload reload wiring for the rolling-handoff protocol."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_adapters import common, control_handoff, payload
import control


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
            "serving_payload_sha256": "a" * 64,
            "release_receipt_sha256": "f" * 64,
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
            "serving_payload_sha256": expected["serving_payload_sha256"],
            "release_receipt_sha256": expected["release_receipt_sha256"],
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
            "serving_payload_sha256": "a" * 64,
            "release_receipt_sha256": "e" * 64,
            "payload_manifest_sha256": "b" * 64,
            "accepting": True,
            "draining": False,
        }
        runtime.update(overrides)
        return runtime

    @staticmethod
    def _commit_side_effect(ctx, *, error=None):
        def commit(*_args, **_kwargs):
            Path(payload.payload_transaction_dir(ctx), "rollback").mkdir(parents=True)
            if error is not None:
                raise error

        return commit

    def test_runtime_supports_handoff_requires_a_complete_idle_identity(self):
        self.assertTrue(control_handoff.runtime_supports_handoff(self._idle_runtime()))
        self.assertTrue(
            control_handoff.runtime_supports_handoff(
                self._idle_runtime(
                    handoff_state="finalized",
                    handoff_transaction_id="txn-previous-finalized",
                )
            )
        )

    def test_runtime_supports_handoff_reports_false_for_legacy_or_unavailable_runtime(self):
        incomplete = self._idle_runtime()
        incomplete.pop("serving_payload_sha256")
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
                self.assertFalse(control_handoff.runtime_supports_handoff(runtime))

    def test_request_handoff_never_terminates_the_old_pid(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        listener_calls = {"n": 0}

        def fake_listener_pids(_ctx):
            listener_calls["n"] += 1
            return [999] if listener_calls["n"] == 1 else [1000]

        with (
            mock.patch.object(
                common, "verified_proxy_listener_pids", side_effect=fake_listener_pids
            ),
            mock.patch.object(
                control_handoff,
                "post_ready",
                return_value={
                    "status": "ready",
                    "transaction_id": expected["transaction_id"],
                    "child_pid": 1000,
                },
            ),
            mock.patch.object(control_handoff.time, "sleep"),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control_handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: self._matching_runtime(expected),
                timeout_seconds=5,
            )
        terminate.assert_not_called()
        self.assertEqual(result["old_pid"], 999)
        self.assertEqual(result["child_pid"], 1000)

    def test_request_handoff_requires_exactly_one_verified_old_listener(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with mock.patch.object(common, "verified_proxy_listener_pids", return_value=[888, 999]):
            with self.assertRaisesRegex(common.InstallError, "exactly one verified"):
                control_handoff.request(
                    ctx,
                    self._expected(),
                    runtime_reader=lambda _ctx: None,
                    timeout_seconds=5,
                )

    def test_request_handoff_surfaces_a_conflicting_in_progress_transaction_distinctly(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[999]),
            mock.patch.object(
                control_handoff,
                "post_ready",
                side_effect=common.InstallError("handoff control returned HTTP 409"),
            ),
        ):
            with self.assertRaisesRegex(common.InstallError, "409"):
                control_handoff.request(
                    ctx,
                    self._expected(),
                    runtime_reader=lambda _ctx: None,
                    timeout_seconds=1,
                )

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
        with mock.patch.object(control_handoff.urllib.request, "build_opener", return_value=opener):
            opener.open.return_value = Response(valid)
            self.assertEqual(control_handoff.post_ready(ctx, expected)["child_pid"], 1000)
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
                        control_handoff.post_ready(ctx, expected)

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
            mock.patch.object(
                common, "verified_proxy_listener_pids", side_effect=fake_listener_pids
            ),
            mock.patch.object(
                control_handoff,
                "post_ready",
                return_value={
                    "status": "ready",
                    "transaction_id": expected["transaction_id"],
                    "child_pid": 1000,
                },
            ),
            mock.patch.object(control_handoff.time, "sleep"),
        ):
            result = control_handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: self._matching_runtime(expected),
                timeout_seconds=5,
            )
        self.assertEqual(result["child_pid"], 1000)
        self.assertGreaterEqual(listener_calls["n"], 4)

    def test_request_handoff_rejects_a_wrong_child_pid_in_the_health_snapshot(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[999], [1000]]),
            mock.patch.object(
                control_handoff,
                "post_ready",
                return_value={
                    "status": "ready",
                    "transaction_id": expected["transaction_id"],
                    "child_pid": 1000,
                },
            ),
            mock.patch.object(control_handoff.time, "sleep"),
        ):
            with self.assertRaises(common.InstallError):
                control_handoff.request(
                    ctx,
                    expected,
                    runtime_reader=lambda _ctx: self._matching_runtime(expected, pid=4242),
                    timeout_seconds=1,
                )

    def test_request_handoff_rejects_each_runtime_field_mismatch(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        expected = self._expected()
        overrides = {
            "handoff_protocol_version": 1,
            "handoff_transaction_id": "wrong-txn",
            "release": "1.0.24",
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "e" * 64,
            "payload_manifest_sha256": "d" * 64,
            "accepting": False,
            "draining": True,
            "handoff_state": "ready",
        }
        for field, bad_value in overrides.items():
            with self.subTest(field=field):
                runtime = self._matching_runtime(expected, **{field: bad_value})
                with (
                    mock.patch.object(
                        common, "verified_proxy_listener_pids", side_effect=[[999], [1000]]
                    ),
                    mock.patch.object(
                        control_handoff,
                        "post_ready",
                        return_value={
                            "status": "ready",
                            "transaction_id": expected["transaction_id"],
                            "child_pid": 1000,
                        },
                    ),
                    mock.patch.object(control_handoff.time, "sleep"),
                ):
                    with self.assertRaises(common.InstallError):
                        control_handoff.request(
                            ctx,
                            expected,
                            runtime_reader=lambda _ctx, snapshot=runtime: snapshot,
                            timeout_seconds=1,
                        )

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
                    mock.patch.object(
                        common, "verified_proxy_listener_pids", return_value=listeners
                    ),
                ):
                    self.assertEqual(
                        control_handoff.resolve_after_controller_failure(
                            ctx,
                            old,
                            expected,
                            runtime_reader=lambda _ctx, snapshot=runtime: snapshot,
                            timeout_seconds=1,
                            lease_seconds=1,
                        ),
                        expected_result,
                    )
        with (
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[999, 1000]),
            mock.patch.object(control_handoff.time, "monotonic", side_effect=[0.0, 1.0, 8.0]),
            mock.patch.object(control_handoff.time, "sleep"),
        ):
            self.assertEqual(
                control_handoff.resolve_after_controller_failure(
                    ctx,
                    old,
                    expected,
                    runtime_reader=lambda _ctx: finalized,
                    timeout_seconds=1,
                    lease_seconds=1,
                ),
                ("unknown", None),
            )

    def test_reload_uses_handoff_without_terminating_the_old_pid_when_supported(self):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
            ),
            mock.patch.object(control_handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control_handoff, "expected_metadata", return_value=self._expected()),
            mock.patch.object(
                control_handoff,
                "request",
                return_value={"old_pid": 1, "child_pid": 2, "release": "1.0.25"},
            ) as handoff,
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
            mock.patch.object(
                control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
            ),
            mock.patch.object(control_handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                payload, "verify_payload_manifest", return_value=(False, "hash mismatch")
            ),
            mock.patch.object(control_handoff, "request") as handoff,
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
            mock.patch.object(control_handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control_handoff, "expected_metadata", return_value=expected),
            mock.patch.object(control_handoff, "request", side_effect=KeyboardInterrupt()),
            mock.patch.object(
                control_handoff,
                "resolve_after_controller_failure",
                return_value=("finalized", finalized),
            ),
        ):
            result = control.reload(ctx, timeout_seconds=5)
        self.assertEqual(result["new_pid"], 1000)
        self.assertTrue(result["recovered_after_controller_failure"])

    def test_reload_falls_back_to_legacy_drain_and_terminate_when_runtime_lacks_handoff_support(
        self,
    ):
        ctx = self._ctx(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_runtime_metrics",
                return_value={"release": "1.0.24", "active_responses": 0, "draining": False},
            ),
            mock.patch.object(control_handoff, "runtime_supports_handoff", return_value=False),
            mock.patch.object(
                control,
                "_drain_listener_with_legacy_bootstrap",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": True, "active_responses": 0},
                },
            ),
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[54321]]),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=0.1)
        terminate.assert_called_once_with(12345)
        self.assertEqual(result, {"old_pid": 12345, "new_pid": 54321})


if __name__ == "__main__":
    unittest.main(verbosity=2)
