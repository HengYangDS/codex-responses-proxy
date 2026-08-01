#!/usr/bin/env python3
"""Unit contracts for process-local request admission and drain state."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.runtime import admission, telemetry


class _Semaphore:
    def __init__(self, acquired: bool, drain: bool = False):
        self.acquired, self.drain, self.releases = acquired, drain, 0

    def acquire(self, **_kwargs) -> bool:
        if self.drain:
            admission.set_draining(True, lease_seconds=30)
        return self.acquired

    def release(self) -> None:
        self.releases += 1


class AdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        admission.reset_for_test()
        telemetry.reset_for_test()

    def test_admission_is_bounded_and_fail_closed_during_drain_races(self) -> None:
        self.assertEqual(admission.admit_response(timeout=0), ("acquired", 1))
        self.assertEqual(admission.drain_snapshot(), (False, 0, 1))
        self.assertTrue(admission.set_draining(True, lease_seconds=30)["draining"])
        self.assertEqual(admission.admit_response(timeout=0), ("draining", 1))
        self.assertEqual(admission.release_response_slot(), 0)
        admission.set_draining(False)
        for semaphore, expected in (
            (_Semaphore(False), ("timeout", 0)),
            (_Semaphore(True, True), ("draining", 0)),
        ):
            with (
                self.subTest(expected=expected),
                mock.patch.object(admission, "_RESPONSE_SEMAPHORE", semaphore),
            ):
                self.assertEqual(admission.admit_response(timeout=0), expected)
            self.assertEqual(semaphore.releases, expected == ("draining", 0))
            admission.set_draining(False)

    def test_handlers_ids_loopback_and_lease_bounds_are_total(self) -> None:
        self.assertEqual((admission.next_request_id(), admission.next_request_id()), (1, 2))
        self.assertEqual(
            (
                admission.begin_handler(),
                admission.active_handlers(),
                admission.end_handler(),
                admission.end_handler(),
            ),
            (1, 1, 0, 0),
        )
        self.assertEqual(
            (admission.is_loopback_client("::1"), admission.is_loopback_client("invalid")),
            (True, False),
        )
        for value, expected in ((None, 30), ("invalid", 30), ("0", 1), ("9999", 900)):
            self.assertEqual(admission.bounded_drain_lease_seconds(value), expected)

    def test_drain_lease_expiry_is_observable(self) -> None:
        with mock.patch.object(admission.time, "monotonic", side_effect=[10.0, 10.0, 12.1, 12.1]):
            admission.set_draining(True, lease_seconds=2)
            self.assertEqual(admission.drain_snapshot(), (False, 2, 0))
        counters = cast(
            "dict[str, int]",
            telemetry.status(
                release="1",
                serving_payload_sha256=None,
                release_receipt_sha256=None,
                admission=admission.snapshot(),
                runtime_identity={},
            )["counters"],
        )
        self.assertEqual(counters["drain_leases_expired"], 1)


if __name__ == "__main__":
    unittest.main()
