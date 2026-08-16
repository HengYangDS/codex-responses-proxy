"""Enforce aggregate coverage floors and semantic-package observation."""

from __future__ import annotations

import json
import sys
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Protocol

from cyclopts import App, Parameter

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE_POLICY = ROOT / ".config/checks/architecture/policy.toml"
_POLICY_KEYS = {
    "minimum_percent",
    "comparison",
    "threshold_scopes",
    "package_observation",
    "metrics",
    "owner",
    "source",
    "risk_model",
    "measurement",
    "false_positive_cost",
    "remediation",
    "review_condition",
}


class CoverageData(Protocol):
    """Minimal coverage.py surface needed to load and report current data."""

    def load(self) -> None: ...

    def json_report(self, *, outfile: str) -> float: ...


def _ratio_gaps(
    totals: Mapping[str, Any],
    floor: float,
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
    if actual < threshold:
        return [f"{label}_coverage_below_floor:{actual:.2f}<{threshold:.2f}"]
    return []


def branch_gaps(totals: Mapping[str, Any], floor: float) -> list[str]:
    """Return a gap when exact branch coverage is absent or below ``floor``."""

    return _ratio_gaps(
        totals,
        floor,
        total_key="num_branches",
        covered_key="covered_branches",
        label="branch",
        missing_gap="branch_coverage_requires_measured_branches",
    )


def statement_gaps(totals: Mapping[str, Any], floor: float) -> list[str]:
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


def _semantic_package(path: str, package_marker: str) -> str | None:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    try:
        index = parts.index(package_marker)
    except ValueError:
        return None
    relative = parts[index + 1 :]
    return relative[0] if len(relative) > 1 else "root"


def _package_gap(package: str, gap: str) -> str:
    """Qualify one stable aggregate gap with its semantic package."""

    reason, separator, detail = gap.partition(":")
    return f"package_{reason}:{package}{separator}{detail}"


def package_totals(files: Mapping[str, Any], package_marker: str) -> dict[str, dict[str, int]]:
    """Aggregate exact coverage counts by the declared semantic package root."""

    totals: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {
            "num_statements": 0,
            "covered_lines": 0,
            "num_branches": 0,
            "covered_branches": 0,
        }
    )
    for path, detail in files.items():
        package = _semantic_package(path, package_marker)
        summary = detail.get("summary") if isinstance(detail, dict) else None
        if package is None or not isinstance(summary, dict):
            continue
        for key in totals[package]:
            value = summary.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[package][key] += value

    return {package: totals[package] for package in sorted(totals)}


def package_gaps(totals: Mapping[str, Mapping[str, int]]) -> list[str]:
    """Require non-zero execution evidence for every semantic package."""

    gaps: list[str] = []
    for package in sorted(totals):
        package_totals = totals[package]
        if package_totals["num_statements"] <= 0:
            gaps.append(f"package_statement_coverage_requires_measured_statements:{package}")
        elif package_totals["covered_lines"] <= 0:
            gaps.append(f"package_statement_coverage_unobserved:{package}")
        if package_totals["num_branches"] > 0 and package_totals["covered_branches"] <= 0:
            gaps.append(f"package_branch_coverage_unobserved:{package}")
    return gaps


def load_policy(path: Path) -> dict[str, Any]:
    """Load the complete coverage contract without implicit defaults."""

    policy = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(policy) != _POLICY_KEYS:
        raise ValueError("coverage policy fields do not match the canonical schema")
    floor = policy["minimum_percent"]
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 < floor <= 100:
        raise ValueError("minimum_percent must be within (0, 100]")
    if policy["comparison"] != "at-least":
        raise ValueError("comparison must be at-least")
    if policy["threshold_scopes"] != ["aggregate"]:
        raise ValueError("threshold_scopes must contain exactly aggregate")
    if policy["package_observation"] != "required":
        raise ValueError("package_observation must be required")
    if policy["metrics"] != ["statement", "branch"]:
        raise ValueError("metrics must contain statement and branch")
    rationale = (
        "owner",
        "source",
        "risk_model",
        "measurement",
        "false_positive_cost",
        "remediation",
        "review_condition",
    )
    if any(not isinstance(policy[key], str) or not policy[key].strip() for key in rationale):
        raise ValueError("coverage policy rationale fields must be non-empty")
    return policy


def package_marker(path: Path = ARCHITECTURE_POLICY) -> str:
    """Derive the Python package marker from the architecture SSOT."""

    policy = tomllib.loads(path.read_text(encoding="utf-8"))
    root = policy.get("package_root")
    if not isinstance(root, str) or not root.strip():
        raise ValueError("architecture package_root must be non-empty")
    marker = PurePosixPath(root).name
    if not marker:
        raise ValueError("architecture package_root must name a package")
    return marker


def _command(
    *,
    policy_path: Annotated[Path, Parameter(name="--policy")],
) -> int:
    """Load current coverage data and report one machine-readable verdict."""

    policy = load_policy(policy_path)
    floor = policy["minimum_percent"]
    coverage: CoverageData = import_module("coverage").Coverage()
    coverage.load()
    report = measured_report(coverage)
    totals = report["totals"]
    packages = package_totals(report.get("files", {}), package_marker())
    gaps = [
        *statement_gaps(totals, floor),
        *branch_gaps(totals, floor),
        *package_gaps(packages),
    ]
    print(
        json.dumps(
            {"ok": not gaps, "gaps": gaps, "packages": packages, **totals},
            sort_keys=True,
        )
    )
    return 0 if not gaps else 1


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run the coverage policy through the repository parser stack."""

    result = App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
