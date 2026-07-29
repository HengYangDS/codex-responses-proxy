#!/usr/bin/env python3
"""Unit contracts for process-local proxy runtime state."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import state  # noqa: E402


class _Semaphore:
    def __init__(self, acquired: bool, drain: bool = False):
        self.acquired, self.drain, self.releases = acquired, drain, 0

    def acquire(self, **_kwargs) -> bool:
        if self.drain:
            state.set_draining(True, lease_seconds=30)
        return self.acquired

    def release(self) -> None:
        self.releases += 1


class RuntimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        state.reset_for_test()

    def test_admission_is_bounded_and_fail_closed_during_drain_races(self) -> None:
        self.assertEqual(state.admit_response(timeout=0), ("acquired", 1))
        self.assertEqual(state.drain_snapshot(), (False, 0, 1))
        self.assertTrue(state.set_draining(True, lease_seconds=30)["draining"])
        self.assertEqual(state.admit_response(timeout=0), ("draining", 1))
        self.assertEqual(state.release_response_slot(), 0)
        state.set_draining(False)
        for semaphore, expected in (
            (_Semaphore(False), ("timeout", 0)),
            (_Semaphore(True, True), ("draining", 0)),
        ):
            with (
                self.subTest(expected=expected),
                mock.patch.object(state, "_RESPONSE_SEMAPHORE", semaphore),
            ):
                self.assertEqual(state.admit_response(timeout=0), expected)
            self.assertEqual(semaphore.releases, expected == ("draining", 0))
            state.set_draining(False)

    def test_status_and_scalar_helpers_are_secret_safe_and_bounded(self) -> None:
        for raw, expected in (("invalid", 7), ("99", 9), ("-5", 1)):
            with mock.patch.dict(state.os.environ, {"SETTING": raw}):
                self.assertEqual(state.bounded_env_int("SETTING", 7, 1, 9), expected)
        self.assertEqual(
            state.safe_request_path("/v1/private path?secret=value"), "/v1/private_path"
        )
        self.assertEqual(state.safe_request_path("relative?secret=value"), "/invalid-path")
        with mock.patch.object(state.urllib.parse, "urlsplit", side_effect=ValueError):
            self.assertEqual(state.safe_request_path("private"), "/invalid-path")
        self.assertEqual(
            (state.safe_exception_label(ValueError("private")), state.safe_exception_label(None)),
            ("ValueError", "UnknownError"),
        )
        self.assertEqual(
            (state.is_loopback_client("::1"), state.is_loopback_client("invalid")), (True, False)
        )
        for value, expected in ((None, 30), ("invalid", 30), ("0", 1), ("9999", 900)):
            self.assertEqual(state.bounded_drain_lease_seconds(value), expected)
        state.record_counter("responses_received")
        state.record_upstream_classification("validation_error")
        state.record_failure("upstream_transport_error")
        status = state.status(
            release="1.2.3",
            serving_payload_sha256=None,
            release_receipt_sha256=None,
            runtime_identity={"pid": 42},
        )
        self.assertEqual(
            (
                status["release"],
                status["pid"],
                cast("dict[str, int]", status["counters"])["responses_received"],
                status["upstream_classifications"],
            ),
            ("1.2.3", 42, 1, {"validation_error": 1}),
        )
        self.assertNotIn("private", repr(status).lower())

    def test_counters_handlers_ids_and_sanitization_are_bounded(self) -> None:
        self.assertEqual((state.next_request_id(), state.next_request_id()), (1, 2))
        self.assertEqual(
            (
                state.begin_handler(),
                state.active_handlers(),
                state.end_handler(),
                state.end_handler(),
            ),
            (1, 1, 0, 0),
        )
        state.record_counter("responses_received", 0)
        state.record_sanitization(
            "reasoning_items=2 malformed_encrypted_blocks=invalid local_image_items=-3"
        )
        counters = cast(
            "dict[str, int]",
            state.status(
                release="1",
                serving_payload_sha256=None,
                release_receipt_sha256=None,
                runtime_identity={},
            )["counters"],
        )
        self.assertEqual(
            (
                counters["encrypted_replayed_reasoning_items_stripped"],
                counters["encrypted_malformed_blocks_stripped"],
                counters["unreplayable_images_stripped"],
            ),
            (2, 0, 0),
        )
        self.assertEqual(state.sanitization_count("no counts", "reasoning_items"), 0)

    def test_cooldown_evicts_and_expires_without_retaining_content(self) -> None:
        state.remember_empty_response_failure("expired", now=10.0)
        self.assertTrue(state.has_empty_response_failure_for_test("expired"))
        self.assertEqual(
            state.empty_response_cooldown_remaining("expired", cooldown_seconds=30, now=40.0), 0
        )
        for index in range(4):
            state.remember_empty_response_failure(f"key-{index}", capacity=3, now=100.0 + index)
        self.assertEqual(state.empty_response_failure_count_for_test(), 3)
        self.assertFalse(state.has_empty_response_failure_for_test("key-0"))

    def test_drain_lease_expiry_is_observable(self) -> None:
        with mock.patch.object(state.time, "monotonic", side_effect=[10.0, 10.0, 12.1, 12.1]):
            state.set_draining(True, lease_seconds=2)
            self.assertEqual(state.drain_snapshot(), (False, 2, 0))
        counters = cast(
            "dict[str, int]",
            state.status(
                release="1",
                serving_payload_sha256=None,
                release_receipt_sha256=None,
                runtime_identity={},
            )["counters"],
        )
        self.assertEqual(counters["drain_leases_expired"], 1)

    def test_logging_redacts_and_bounds_retention_without_becoming_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proxy.log"
            with (
                mock.patch.object(state, "LOG_PATH", str(path)),
                mock.patch.object(state, "LOG_MAX_BYTES", 16),
                mock.patch.object(state, "LOG_BACKUP_COUNT", 2),
                mock.patch.object(state.sys.stderr, "write"),
            ):
                state.log("authorization: Bearer private-token encrypted=gAAAA-secret" + "x" * 2048)
                text = path.read_text()
                self.assertNotIn("private-token", text)
                self.assertNotIn("gAAAA-secret", text)
                path.write_text("x" * 17)
                state.log("rotation")
                self.assertIn("discarded_oversized_bytes=17", path.read_text())
                path.write_text("x" * 12)
                (path.parent / "proxy.log.1").write_text("y" * 17)
                state.log("backup rotation")
                self.assertTrue((path.parent / "proxy.log.1").exists())
                with mock.patch.object(state, "LOG_BACKUP_COUNT", 0):
                    path.write_text("x" * 12)
                    state.log("no backups")
                with mock.patch.object(Path, "exists", return_value=False):
                    path.write_text("x" * 12)
                    state.log("no prior backup")
                (path.parent / "proxy.log.1").write_text("y" * 12)
                path.write_text("x" * 12)
                state.log("retained backup")
                path.write_text("short")
                self.assertEqual(state._rotate_log_if_needed(path, 1), 0)
                with mock.patch.object(Path, "lstat", side_effect=OSError):
                    self.assertEqual(state._rotate_log_if_needed(path, 1), 0)
                path.unlink()
                path.mkdir()
                state.log("ignored errors")
                with mock.patch.object(state.sys.stderr, "write", side_effect=OSError):
                    state.log("stderr error")


if __name__ == "__main__":
    unittest.main()
