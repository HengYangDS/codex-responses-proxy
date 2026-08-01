#!/usr/bin/env python3
"""Unit contracts for provider-neutral bounded failure cooldowns."""

from __future__ import annotations

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
        self.assertEqual(cooldown.remaining("expired", cooldown_seconds=30, now=40.0), 0)
        for index in range(4):
            cooldown.remember_failure(f"key-{index}", capacity=3, now=100.0 + index)
        self.assertEqual(cooldown.failure_count_for_test(), 3)
        self.assertFalse(cooldown.has_failure_for_test("key-0"))


if __name__ == "__main__":
    unittest.main()
