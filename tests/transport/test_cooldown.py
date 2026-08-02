#!/usr/bin/env python3
"""Unit contracts for provider-neutral bounded failure cooldowns."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import Message
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.transport import cooldown


class CooldownTests(unittest.TestCase):
    def setUp(self) -> None:
        cooldown.reset_for_test()

    def test_cache_evicts_and_expires_without_retaining_payloads(self) -> None:
        cooldown.remember_failure("expired", now=10.0)
        self.assertTrue(cooldown.has_failure_for_test("expired"))
        self.assertEqual(cooldown.remaining("expired", now=40.0), 0)
        for index in range(4):
            cooldown.remember_failure(f"key-{index}", capacity=3, now=100.0 + index)
        self.assertEqual(cooldown.failure_count_for_test(), 3)
        self.assertFalse(cooldown.has_failure_for_test("key-0"))

    def test_retry_after_supports_delta_date_and_bounded_fallback(self) -> None:
        delta = Message()
        delta["Retry-After"] = "7"
        self.assertEqual(cooldown.retry_after_seconds(delta, now=datetime.now(UTC)), 7)

        dated = Message()
        dated["Retry-After"] = "Sun, 02 Aug 2026 04:26:45 GMT"
        now = datetime(2026, 8, 2, 4, 26, 35, tzinfo=UTC)
        self.assertEqual(cooldown.retry_after_seconds(dated, now=now), 10)

        for value in (None, "invalid", "-1", "0"):
            headers = Message()
            if value is not None:
                headers["Retry-After"] = value
            with self.subTest(value=value):
                self.assertEqual(cooldown.retry_after_seconds(headers, now=now), 5)

        for value in ("301", "99999", "9" * 10_000):
            headers = Message()
            headers["Retry-After"] = value
            with self.subTest(value=value[:20]):
                self.assertEqual(cooldown.retry_after_seconds(headers, now=now), 300)

    def test_later_shorter_failure_does_not_shorten_an_active_cooldown(self) -> None:
        cooldown.remember_failure("provider:ucloud", cooldown_seconds=300, now=10.0)
        cooldown.remember_failure("provider:ucloud", cooldown_seconds=5, now=11.0)
        self.assertEqual(cooldown.remaining("provider:ucloud", now=12.0), 298.0)


if __name__ == "__main__":
    unittest.main()
