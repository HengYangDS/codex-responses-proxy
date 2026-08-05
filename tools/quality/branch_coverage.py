#!/usr/bin/env python3
"""Enforce independent statement and branch coverage floors."""

from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
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


def measured_report(coverage: CoverageData) -> dict[str, Any]:
    """Return the exact configured coverage report."""

    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "coverage.json"
        coverage.json_report(outfile=str(report))
        return json.loads(report.read_text(encoding="utf-8"))


def _semantic_package(path: str) -> str | None:
    marker = "codex_responses_proxy/"
    normalized = path.replace("\\", "/")
    if marker not in normalized:
        return None
    relative = normalized.split(marker, 1)[1]
    return relative.split("/", 1)[0] if "/" in relative else "root"


def _package_gap(package: str, gap: str) -> str:
    """Qualify one stable aggregate gap with its semantic package."""

    reason, separator, detail = gap.partition(":")
    return f"package_{reason}:{package}{separator}{detail}"


def package_gaps(files: Mapping[str, Any], floor: int | float) -> list[str]:
    """Require statement and branch coverage above the floor per semantic package."""

    totals: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {
            "num_statements": 0,
            "covered_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
        }
    )
    for path, detail in files.items():
        package = _semantic_package(path)
        summary = detail.get("summary") if isinstance(detail, dict) else None
        if package is None or not isinstance(summary, dict):
            continue
        for key in totals[package]:
            value = summary.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[package][key] += value

    gaps: list[str] = []
    for package in sorted(totals):
        package_totals = totals[package]
        for gap in statement_gaps(package_totals, floor):
            gaps.append(_package_gap(package, gap))
        if package_totals["num_branches"]:
            for gap in branch_gaps(package_totals, floor):
                gaps.append(_package_gap(package, gap))
    return gaps


def main() -> int:
    """Load current coverage data and report one machine-readable verdict."""

    coverage: CoverageData = import_module("coverage").Coverage()
    coverage.load()
    report = measured_report(coverage)
    totals = report["totals"]
    gaps = [
        *statement_gaps(totals, coverage.config.fail_under),
        *branch_gaps(totals, coverage.config.fail_under),
        *package_gaps(report.get("files", {}), coverage.config.fail_under),
    ]
    print(json.dumps({"ok": not gaps, "gaps": gaps, **totals}, sort_keys=True))
    return 0 if not gaps else 1


if __name__ == "__main__":
    sys.exit(main())
