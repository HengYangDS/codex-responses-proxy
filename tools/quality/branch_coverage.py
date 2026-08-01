#!/usr/bin/env python3
"""Enforce independent statement and branch coverage floors."""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Mapping
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol


class CoverageConfig(Protocol):
    """Coverage settings consumed by this independent branch gate."""

    @property
    def fail_under(self) -> int | float: ...


class CoverageData(Protocol):
    """Minimal coverage.py surface needed to load and report current data."""

    @property
    def config(self) -> CoverageConfig: ...

    def load(self) -> None: ...

    def json_report(self, *, outfile: str) -> float: ...


def _ratio_gaps(
    totals: Mapping[str, Any],
    floor: int | float,
    *,
    total_key: str,
    covered_key: str,
    label: str,
    missing_gap: str,
) -> list[str]:
    """Validate one exact measured ratio and report its stable coverage gap."""

    total = totals.get(total_key)
    covered = totals.get(covered_key)
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total <= 0
        or isinstance(covered, bool)
        or not isinstance(covered, int)
        or not 0 <= covered <= total
    ):
        return [missing_gap]
    threshold = Decimal(str(floor))
    actual = Decimal(covered * 100) / Decimal(total)
    if actual <= threshold:
        return [f"{label}_coverage_not_strictly_above_floor:{actual:.2f}<={threshold:.2f}"]
    return []


def branch_gaps(totals: Mapping[str, Any], floor: int | float) -> list[str]:
    """Return a gap when exact branch coverage is absent or below ``floor``."""

    return _ratio_gaps(
        totals,
        floor,
        total_key="num_branches",
        covered_key="covered_branches",
        label="branch",
        missing_gap="branch_coverage_requires_measured_branches",
    )


def statement_gaps(totals: Mapping[str, Any], floor: int | float) -> list[str]:
    """Return a gap when exact statement coverage is absent or below ``floor``."""

    return _ratio_gaps(
        totals,
        floor,
        total_key="num_statements",
        covered_key="covered_lines",
        label="statement",
        missing_gap="statement_coverage_requires_measured_statements",
    )


def measured_totals(coverage: CoverageData) -> dict[str, int]:
    """Return branch counts from the same configured coverage report scope."""

    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "coverage.json"
        coverage.json_report(outfile=str(report))
        total = json.loads(report.read_text(encoding="utf-8"))["totals"]
    return {
        "num_statements": total["num_statements"],
        "covered_lines": total["covered_lines"],
        "num_branches": total["num_branches"],
        "covered_branches": total["covered_branches"],
    }


def main() -> int:
    """Load current coverage data and report one machine-readable verdict."""

    coverage: CoverageData = import_module("coverage").Coverage()
    coverage.load()
    totals = measured_totals(coverage)
    gaps = [
        *statement_gaps(totals, coverage.config.fail_under),
        *branch_gaps(totals, coverage.config.fail_under),
    ]
    print(json.dumps({"ok": not gaps, "gaps": gaps, **totals}, sort_keys=True))
    return 0 if not gaps else 1


if __name__ == "__main__":
    sys.exit(main())
