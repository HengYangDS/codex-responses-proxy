#!/usr/bin/env python3
"""Unit contracts for secret-free runtime telemetry."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.replay.request import ProjectionMetrics
from codex_responses_proxy.runtime import telemetry


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        telemetry.reset_for_test()

    def test_status_composes_structured_metrics_without_retaining_content(self) -> None:
        telemetry.record_counter("responses_received")
        telemetry.record_upstream_classification("validation_error")
        telemetry.record_failure("upstream_transport_error")
        telemetry.record_sanitization(
            ProjectionMetrics(reasoning_items=2, encrypted_blocks=3, local_image_items=4)
        )
        status = telemetry.status(
            release="1.2.3",
            serving_payload_sha256=None,
            release_receipt_sha256=None,
            admission={"active_responses": 1, "draining": False},
            runtime_identity={"pid": 42},
        )
        counters = cast("dict[str, int]", status["counters"])
        self.assertEqual(
            (
                status["release"],
                status["pid"],
                counters["responses_received"],
                counters["encrypted_replayed_reasoning_items_stripped"],
                counters["encrypted_content_blocks_stripped"],
                counters["unreplayable_images_stripped"],
                status["upstream_classifications"],
            ),
            ("1.2.3", 42, 1, 2, 3, 4, {"validation_error": 1}),
        )
        self.assertNotIn("private", repr(status).lower())


if __name__ == "__main__":
    unittest.main()
