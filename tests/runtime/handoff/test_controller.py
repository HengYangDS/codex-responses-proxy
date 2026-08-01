#!/usr/bin/env python3
"""Installed same-payload reload wiring for the rolling-handoff protocol."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.deployment import handoff
from codex_responses_proxy import errors
from codex_responses_proxy.supervision import process
from codex_responses_proxy.payload import projection as payload_projection
from tests.runtime.handoff.fixtures import Response
from tests.runtime.handoff.fixtures import expected_metadata
from tests.runtime.handoff.fixtures import idle_runtime
from tests.deployment.fixtures import install_context
from tests.runtime.handoff.fixtures import matching_health
from tests.runtime.handoff.fixtures import ready_ack
from codex_responses_proxy.commands import control


class TestControllerHandoffWiring(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def test_runtime_supports_handoff_requires_a_complete_available_identity(self):
        incomplete = idle_runtime()
        incomplete.pop("serving_payload_sha256")
        for runtime, supported in (
            (idle_runtime(), True),
            (
                idle_runtime(
                    handoff_state="finalized",
                    handoff_transaction_id="txn-previous-finalized",
                ),
                True,
            ),
            *(
                (runtime, False)
                for runtime in (
                    {"handoff_protocol_version": 1},
                    {"handoff_protocol_version": 2},
                    incomplete,
                    idle_runtime(accepting=False),
                    idle_runtime(draining=True),
                    idle_runtime(handoff_state="ready"),
                    {},
                    None,
                    {"release": "1.0.24"},
                )
            ),
        ):
            with self.subTest(runtime=runtime, supported=supported):
                self.assertIs(handoff.runtime_supports_handoff(runtime), supported)

    def test_request_handoff_converges_without_terminating_the_old_listener(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        for name, listeners in (
            ("direct", [[999], [1000]]),
            ("transient dual listener", [[999], [999, 1000], [999, 1000], [1000]]),
        ):
            with self.subTest(case=name):
                with (
                    mock.patch.object(
                        process, "verified_proxy_listener_pids", side_effect=listeners
                    ),
                    mock.patch.object(handoff, "post_ready", return_value=ready_ack(expected)),
                    mock.patch.object(handoff.time, "sleep"),
                    mock.patch.object(process, "terminate_pid") as terminate,
                ):
                    result = handoff.request(
                        ctx,
                        expected,
                        runtime_reader=lambda _ctx: matching_health(1000, expected),
                        timeout_seconds=5,
                    )
                    self.assertEqual((result["old_pid"], result["child_pid"]), (999, 1000))
                    terminate.assert_not_called()

    def test_request_handoff_rejects_invalid_listener_ownership_or_control_conflict(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        cases = (
            ("ambiguous listener", [888, 999], None, "exactly one verified"),
            (
                "in-progress conflict",
                [999],
                errors.InstallError("handoff control returned HTTP 409"),
                "409",
            ),
        )
        for name, listeners, failure, message in cases:
            with self.subTest(case=name):
                with (
                    mock.patch.object(
                        process, "verified_proxy_listener_pids", return_value=listeners
                    ),
                    mock.patch.object(handoff, "post_ready", side_effect=failure),
                    self.assertRaisesRegex(errors.InstallError, message),
                ):
                    handoff.request(
                        ctx,
                        expected,
                        runtime_reader=lambda _ctx: None,
                        timeout_seconds=1,
                    )

    def test_handoff_post_requires_a_complete_protocol_v2_ready_acknowledgement(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        valid = ready_ack(expected)
        opener = mock.Mock()
        with mock.patch.object(handoff.urllib.request, "build_opener", return_value=opener):
            opener.open.return_value = Response(valid)
            self.assertEqual(handoff.post_ready(ctx, expected)["child_pid"], 1000)
            for field, bad_value in (
                ("ok", False),
                ("state", "preparing"),
                ("protocol_version", 1),
                ("transaction_id", "wrong"),
                ("child_pid", 0),
            ):
                with self.subTest(field=field):
                    opener.open.return_value = Response({**valid, field: bad_value})
                    with self.assertRaises(errors.InstallError):
                        handoff.post_ready(ctx, expected)

    def test_expected_metadata_reads_and_validates_each_release_identity(self):
        root = Path(self.tempdir.name)
        manifest_path = root / payload_projection.PAYLOAD_MANIFEST_FILENAME

        with self.assertRaisesRegex(errors.InstallError, "VERSION"):
            handoff.expected_metadata(str(root))
        (root / "VERSION").write_text("\n", encoding="utf-8")
        with self.assertRaisesRegex(errors.InstallError, "no release version"):
            handoff.expected_metadata(str(root))

        (root / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        for payload in (
            b"not-json",
            b"{}",
            json.dumps(
                {
                    "serving_payload_sha256": "bad",
                    "release_receipt_sha256": "f" * 64,
                }
            ).encode(),
            json.dumps(
                {
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "BAD",
                }
            ).encode(),
        ):
            manifest_path.write_bytes(payload)
            with self.assertRaises(errors.InstallError):
                handoff.expected_metadata(str(root))

        manifest_path.write_text(
            json.dumps(
                {
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "f" * 64,
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(handoff.uuid, "uuid4", return_value=mock.Mock(hex="txn-fixed")):
            metadata = handoff.expected_metadata(str(root))
        self.assertEqual(metadata["transaction_id"], "txn-fixed")
        self.assertEqual(metadata["release"], "1.0.25")
        self.assertEqual(metadata["manifest_sha256"], handoff._sha256_file(str(manifest_path)))

    def test_post_ready_bounds_timing_and_rejects_transport_or_response_failures(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        valid = json.dumps(ready_ack(expected)).encode()
        opener = mock.Mock()
        with mock.patch.object(handoff.urllib.request, "build_opener", return_value=opener):
            opener.open.return_value = Response(valid)
            handoff.post_ready(ctx, expected, lease_seconds=0.1, timeout_seconds=999)
            request = opener.open.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(body["lease_seconds"], 1)
            self.assertEqual(body["timeout_seconds"], 120)

            failures = (
                (Response(valid, status=500), "returned HTTP 500"),
                (Response(b"x" * (handoff._MAX_BODY_BYTES + 1)), "response is too large"),
                (Response(b"[]"), "invalid response"),
            )
            for response, message in failures:
                with self.subTest(message=message):
                    opener.open.side_effect = None
                    opener.open.return_value = response
                    with self.assertRaisesRegex(errors.InstallError, message):
                        handoff.post_ready(ctx, expected)

            conflict_body = io.BytesIO(b"conflict")
            for failure, message in (
                (
                    urllib.error.HTTPError("url", 409, "conflict", Message(), conflict_body),
                    "HTTP 409",
                ),
                (urllib.error.URLError("offline"), "unavailable"),
                (ValueError("bad timeout"), "unavailable"),
            ):
                with self.subTest(failure=type(failure).__name__):
                    opener.open.side_effect = failure
                    with self.assertRaisesRegex(errors.InstallError, message):
                        handoff.post_ready(ctx, expected)
            self.assertTrue(conflict_body.closed)

        oversized = expected_metadata(release="x" * handoff._MAX_BODY_BYTES)
        with self.assertRaisesRegex(errors.InstallError, "request payload is too large"):
            handoff.post_ready(ctx, oversized)

    def test_request_handoff_rejects_a_wrong_child_pid_in_the_health_snapshot(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        with (
            mock.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]]),
            mock.patch.object(
                handoff,
                "post_ready",
                return_value=ready_ack(expected),
            ),
            mock.patch.object(handoff.time, "sleep"),
        ):
            with self.assertRaises(errors.InstallError):
                handoff.request(
                    ctx,
                    expected,
                    runtime_reader=lambda _ctx: matching_health(1000, expected, pid=4242),
                    timeout_seconds=1,
                )

    def test_request_handoff_rejects_each_runtime_field_mismatch(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        with (
            mock.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]]),
            mock.patch.object(handoff, "post_ready", return_value={"child_pid": 1000}),
            self.assertRaisesRegex(errors.InstallError, "did not match"),
        ):
            handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=1,
            )
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
                runtime = matching_health(1000, expected, **{field: bad_value})
                with (
                    mock.patch.object(
                        process, "verified_proxy_listener_pids", side_effect=[[999], [1000]]
                    ),
                    mock.patch.object(
                        handoff,
                        "post_ready",
                        return_value=ready_ack(expected),
                    ),
                    mock.patch.object(handoff.time, "sleep"),
                ):
                    with self.assertRaises(errors.InstallError):
                        handoff.request(
                            ctx,
                            expected,
                            runtime_reader=lambda _ctx, snapshot=runtime: snapshot,
                            timeout_seconds=1,
                        )

    def test_request_handoff_times_out_before_the_child_listener_converges(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        with (
            mock.patch.object(process, "verified_proxy_listener_pids", return_value=[999]),
            mock.patch.object(
                handoff,
                "post_ready",
                return_value={"child_pid": 1000},
            ),
            mock.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 10.0]),
            mock.patch.object(handoff.time, "sleep"),
            self.assertRaisesRegex(errors.InstallError, "did not converge"),
        ):
            handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=1,
                lease_seconds=1,
            )

    def test_wait_for_rollback_accepts_only_the_exact_resumed_runtime_and_times_out(self):
        ctx = install_context(Path(self.tempdir.name))
        old = idle_runtime()
        mismatches = (
            None,
            idle_runtime(pid=123),
            idle_runtime(serving_payload_sha256="c" * 64),
            idle_runtime(release_receipt_sha256="c" * 64),
            idle_runtime(payload_manifest_sha256="c" * 64),
            idle_runtime(handoff_protocol_version=1),
            idle_runtime(handoff_state="finalized"),
            idle_runtime(handoff_transaction_id="txn"),
            idle_runtime(accepting=False),
            idle_runtime(draining=True),
        )
        runtimes = iter((*mismatches, old))
        listeners = ([123], *([[999]] * (len(mismatches) + 1)))
        with (
            mock.patch.object(process, "verified_proxy_listener_pids", side_effect=listeners),
            mock.patch.object(handoff.time, "monotonic", side_effect=range(20)),
            mock.patch.object(handoff.time, "sleep"),
        ):
            self.assertEqual(
                handoff.wait_for_rollback(
                    ctx,
                    old,
                    runtime_reader=lambda _ctx: next(runtimes),
                    timeout_seconds=20,
                ),
                old,
            )

        with (
            mock.patch.object(process, "verified_proxy_listener_pids", return_value=[1000]),
            mock.patch.object(handoff.time, "monotonic", side_effect=[0.0, 0.1, 0.2]),
            mock.patch.object(handoff.time, "sleep"),
            self.assertRaisesRegex(errors.InstallError, "did not resume"),
        ):
            handoff.wait_for_rollback(
                ctx,
                old,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_failure_resolver_classifies_finalized_rolled_back_and_unknown_states(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        finalized = matching_health(1000, expected, pid=1000, handoff_state="finalized")
        cases = (
            ("finalized", [1000], finalized, ("finalized", finalized)),
            ("rolled_back", [999], old, ("rolled_back", old)),
        )
        for name, listeners, runtime, expected_result in cases:
            with self.subTest(name=name):
                with (
                    mock.patch.object(
                        process, "verified_proxy_listener_pids", return_value=listeners
                    ),
                ):
                    self.assertEqual(
                        handoff.resolve_after_controller_failure(
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
            mock.patch.object(process, "verified_proxy_listener_pids", return_value=[999, 1000]),
            mock.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 8.0]),
            mock.patch.object(handoff.time, "sleep"),
        ):
            self.assertEqual(
                handoff.resolve_after_controller_failure(
                    ctx,
                    old,
                    expected,
                    runtime_reader=lambda _ctx: finalized,
                    timeout_seconds=1,
                    lease_seconds=1,
                ),
                ("unknown", None),
            )

    def test_failure_resolver_ignores_non_mapping_and_non_integer_runtime_pids(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        runtimes = iter((None, {"pid": True}, matching_health(1000, expected, pid=1000)))
        with (
            mock.patch.object(
                process,
                "verified_proxy_listener_pids",
                side_effect=[[999, 1000], [999, 1000], [1000]],
            ),
            mock.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 2.0, 3.0]),
            mock.patch.object(handoff.time, "sleep"),
        ):
            self.assertEqual(
                handoff.resolve_after_controller_failure(
                    ctx,
                    old,
                    expected,
                    runtime_reader=lambda _ctx: next(runtimes),
                    timeout_seconds=10,
                    lease_seconds=1,
                )[0],
                "finalized",
            )

    def test_digest_helpers_reject_noncanonical_values_and_hash_large_files(self):
        for value in (None, "a" * 63, "g" * 64, "A" * 64):
            with self.subTest(value=value):
                self.assertFalse(handoff._valid_sha256(value))
        self.assertTrue(handoff._valid_sha256("a" * 64))

        path = Path(self.tempdir.name) / "large.bin"
        path.write_bytes(b"a" * (1024 * 1024 + 1))
        self.assertEqual(len(handoff._sha256_file(str(path))), 64)

    def test_reload_uses_handoff_without_terminating_the_old_pid_when_supported(self):
        ctx = install_context(Path(self.tempdir.name))
        with (
            mock.patch.object(
                control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
            ),
            mock.patch.object(handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                payload_projection, "verify_payload_manifest", return_value=(True, "ok")
            ),
            mock.patch.object(handoff, "expected_metadata", return_value=expected_metadata()),
            mock.patch.object(
                handoff,
                "request",
                return_value={"old_pid": 1, "child_pid": 2, "release": "1.0.25"},
            ) as request_handoff,
            mock.patch.object(process, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=5)
        request_handoff.assert_called_once()
        terminate.assert_not_called()
        self.assertEqual(result, {"old_pid": 1, "new_pid": 2})

    def test_reload_rejects_v2_handoff_when_installed_payload_integrity_fails(self):
        ctx = install_context(Path(self.tempdir.name))
        with (
            mock.patch.object(
                control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
            ),
            mock.patch.object(handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                payload_projection,
                "verify_payload_manifest",
                return_value=(False, "hash mismatch"),
            ),
            mock.patch.object(handoff, "request") as request_handoff,
        ):
            with self.assertRaisesRegex(errors.InstallError, "integrity"):
                control.reload(ctx, timeout_seconds=5)
        request_handoff.assert_not_called()

    def test_reload_recovers_a_finalized_result_after_controller_failure(self):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        finalized = matching_health(1000, expected, pid=1000, handoff_state="finalized")
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=old),
            mock.patch.object(handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                payload_projection, "verify_payload_manifest", return_value=(True, "ok")
            ),
            mock.patch.object(handoff, "expected_metadata", return_value=expected),
            mock.patch.object(handoff, "request", side_effect=KeyboardInterrupt()),
            mock.patch.object(
                handoff,
                "resolve_after_controller_failure",
                return_value=("finalized", finalized),
            ),
        ):
            result = control.reload(ctx, timeout_seconds=5)
        self.assertEqual(result["new_pid"], 1000)
        self.assertTrue(result["recovered_after_controller_failure"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
