#!/usr/bin/env python3
"""Unit contracts for process-local proxy runtime state."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from typing import Protocol
from typing import cast
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proxy"))

try:
    import runtime_state
finally:
    sys.path.pop(0)


class _Semaphore(Protocol):
    """Minimal response-capacity contract exercised by admission tests."""

    def acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        """Try to acquire capacity under the requested blocking policy."""

    def release(self) -> None:
        """Return one unit of capacity."""


class _UnavailableSemaphore:
    """Test double for one exhausted response-capacity gate."""

    def acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        del blocking, timeout
        return False

    def release(self) -> None:
        raise AssertionError("an unavailable semaphore must not be released")


class RuntimeStateTests(unittest.TestCase):
    """Exercise the runtime owner without importing the HTTP proxy entrypoint."""

    def setUp(self) -> None:
        runtime_state.reset_for_test()

    def test_admission_closes_drain_race_and_tracks_active_requests(self) -> None:
        """Admission and drain share one atomic owner rather than proxy globals."""
        disposition, active = runtime_state.admit_response(timeout=0)
        self.assertEqual(disposition, "acquired")
        self.assertEqual(active, 1)
        self.assertEqual(runtime_state.drain_snapshot(), (False, 0, 1))

        started = runtime_state.set_draining(True, lease_seconds=30)
        self.assertTrue(started["draining"])
        blocked, blocked_active = runtime_state.admit_response(timeout=0)
        self.assertEqual(blocked, "draining")
        self.assertEqual(blocked_active, 1)

        self.assertEqual(runtime_state.release_response_slot(), 0)
        stopped = runtime_state.set_draining(False)
        self.assertFalse(stopped["draining"])

    def test_queue_timeout_is_distinct_from_drain_rejection(self) -> None:
        """Admission reports capacity timeout separately from a closed drain gate."""
        original = runtime_state._RESPONSE_SEMAPHORE
        runtime_state._RESPONSE_SEMAPHORE = cast(
            "threading.BoundedSemaphore", cast("_Semaphore", _UnavailableSemaphore())
        )
        try:
            disposition, active = runtime_state.admit_response(timeout=0)
        finally:
            runtime_state._RESPONSE_SEMAPHORE = original
        self.assertEqual(disposition, "timeout")
        self.assertEqual(active, 0)

    def test_status_is_secret_free_and_uses_injected_identity(self) -> None:
        """Status owns mutable metrics while the proxy supplies release identity."""
        runtime_state.record_counter("responses_received")
        runtime_state.record_upstream_classification("validation_error")
        runtime_state.record_failure("upstream_transport_error")

        status = runtime_state.status(
            release="1.2.3",
            serving_payload_sha256="a" * 64,
            release_receipt_sha256="b" * 64,
            runtime_identity={"pid": 42, "accepting": True},
        )

        self.assertEqual(status["release"], "1.2.3")
        self.assertEqual(status["serving_payload_sha256"], "a" * 64)
        self.assertEqual(status["release_receipt_sha256"], "b" * 64)
        self.assertEqual(status["pid"], 42)
        self.assertEqual(cast("dict[str, int]", status["counters"])["responses_received"], 1)
        self.assertEqual(status["upstream_classifications"], {"validation_error": 1})
        self.assertEqual(
            cast("dict[str, object]", status["last_failure"])["classification"],
            "upstream_transport_error",
        )
        self.assertNotIn("private", repr(status).lower())

    def test_logging_redacts_secrets_and_bounds_retention(self) -> None:
        """The runtime owner writes only bounded secret-safe operational lines."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proxy.log"
            old_path = runtime_state.LOG_PATH
            old_max = runtime_state.LOG_MAX_BYTES
            old_backups = runtime_state.LOG_BACKUP_COUNT
            runtime_state.LOG_PATH = str(path)
            runtime_state.LOG_MAX_BYTES = 4096
            runtime_state.LOG_BACKUP_COUNT = 0
            try:
                with mock.patch.object(runtime_state.sys.stderr, "write"):
                    runtime_state.log(
                        "authorization: Bearer private-token "
                        "encrypted=gAAAA-secret "
                        "path=/v1/responses?prompt=private"
                    )
            finally:
                runtime_state.LOG_PATH = old_path
                runtime_state.LOG_MAX_BYTES = old_max
                runtime_state.LOG_BACKUP_COUNT = old_backups

            text = path.read_text(encoding="utf-8")
            self.assertNotIn("private-token", text)
            self.assertNotIn("gAAAA-secret", text)
            self.assertLessEqual(
                max(len(line.encode("utf-8")) for line in text.splitlines()),
                runtime_state.LOG_LINE_MAX_BYTES + 96,
            )

    def test_empty_response_cooldown_is_bounded_and_expires(self) -> None:
        """Cooldown state evicts expired entries and never grows past capacity."""
        runtime_state.remember_empty_response_failure("expired", now=10.0)
        self.assertTrue(runtime_state.has_empty_response_failure_for_test("expired"))
        self.assertEqual(
            runtime_state.empty_response_cooldown_remaining(
                "expired",
                cooldown_seconds=30,
                now=40.0,
            ),
            0,
        )

        for index in range(4):
            runtime_state.remember_empty_response_failure(
                f"key-{index}",
                capacity=3,
                cooldown_seconds=30,
                now=100.0 + index,
            )
        self.assertEqual(runtime_state.empty_response_failure_count_for_test(), 3)
        self.assertEqual(
            runtime_state.empty_response_cooldown_remaining(
                "key-0",
                cooldown_seconds=30,
                now=104.0,
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
