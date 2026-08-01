"""Regression contract for retired provider-history rewriting machinery."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProviderHistoryTests(unittest.TestCase):
    """Keep publication forward-only and independent of historical identity rewriting."""

    def test_history_rewriter_is_absent_from_the_product(self) -> None:
        """Reject reintroduction of the obsolete history-rewrite implementation."""

        self.assertFalse((ROOT / "tools" / "forge" / "rewrite-provider-history.py").exists())


if __name__ == "__main__":
    unittest.main()
