"""Contracts for machine-readable performance evidence admission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _policy(path: Path, *, maximum: float = 1.0) -> Path:
    path.write_text(
        "[execution]\nminimum_latency_samples = 2\nminimum_memory_samples = 2\npercentile = 95\n"
        "[budgets.maximum_seconds]\n"
        f"metric = {maximum}\n"
        "[budgets.maximum_bytes]\n"
        "memory = 1024\n",
        encoding="utf-8",
    )
    return path


def _suite(path: Path, name: str, value: float, *, unit: str = "second") -> Path:
    path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "metadata": {"name": name, "unit": unit},
                "benchmarks": [
                    {
                        "runs": [
                            {
                                "values": [value, value],
                                "metadata": {"loops": 1},
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestPerformanceEvidence:
    """Admit complete declared metrics and reject ambiguous evidence."""

    def test_accepts_complete_evidence_within_budget(self, tmp_path: Path) -> None:
        from tools.performance.verify import verify

        verify(
            policy=_policy(tmp_path / "policy.toml"),
            latency=_suite(tmp_path / "latency.json", "metric", 0.5),
            memory=_suite(tmp_path / "memory.json", "memory", 512, unit="byte"),
        )

    @pytest.mark.parametrize(
        ("maximum", "observed"),
        [(1.0, 1.1), (-1.0, 0.5)],
    )
    def test_rejects_exceeded_or_invalid_budget(
        self, tmp_path: Path, maximum: float, observed: float
    ) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import verify

        policy = _policy(tmp_path / "policy.toml", maximum=maximum)
        with pytest.raises(PerformanceError):
            verify(
                policy=policy,
                latency=_suite(tmp_path / "latency.json", "metric", observed),
                memory=_suite(tmp_path / "memory.json", "memory", 512, unit="byte"),
            )

    def test_rejects_missing_and_undeclared_metrics(self, tmp_path: Path) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import verify

        with pytest.raises(PerformanceError, match=r"missing.*undeclared"):
            verify(
                policy=_policy(tmp_path / "policy.toml"),
                latency=_suite(tmp_path / "latency.json", "other", 0.5),
                memory=_suite(tmp_path / "memory.json", "memory", 512, unit="byte"),
            )

    @pytest.mark.parametrize("maximum", [True, float("nan"), float("inf")])
    def test_rejects_non_finite_or_boolean_budgets(self, maximum: object) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import _budgets

        with pytest.raises(PerformanceError, match="invalid"):
            _budgets({"maximum_seconds": {"metric": maximum}}, "maximum_seconds")

    @pytest.mark.parametrize("group", [None, {}, []])
    def test_requires_declared_budget_groups(self, group: object) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import _budgets

        with pytest.raises(PerformanceError, match="section is invalid"):
            _budgets({"maximum_seconds": group}, "maximum_seconds")

    def test_requires_budgets_after_valid_execution_policy(self, tmp_path: Path) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import verify

        policy = _policy(tmp_path / "policy.toml")
        policy.write_text(policy.read_text().split("[budgets.")[0])
        with pytest.raises(PerformanceError, match="budgets are unavailable"):
            verify(policy=policy, latency=tmp_path / "missing", memory=tmp_path / "missing")

    @pytest.mark.parametrize("values", [[0.1, float("nan")], [0.1, float("inf")], [-0.1, 0.1]])
    def test_rejects_non_finite_or_negative_measurements(self, values, tmp_path, mocker) -> None:
        from tools.performance import verify

        benchmark = mocker.Mock()
        benchmark.get_unit.return_value = "second"
        benchmark.get_name.return_value = "metric"
        benchmark.get_values.return_value = values
        mocker.patch.object(verify.pyperf.BenchmarkSuite, "load", return_value=[benchmark])
        with pytest.raises(verify.PerformanceError, match="invalid"):
            verify._measurements(
                tmp_path / "unused", unit="second", minimum_samples=2, percentile=95
            )

    @pytest.mark.parametrize(("unit", "minimum"), [("byte", 2), ("second", 3)])
    def test_rejects_wrong_unit_and_short_distributions(self, unit, minimum, tmp_path) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import _measurements

        with pytest.raises(PerformanceError, match=r"unit mismatch|too few samples"):
            _measurements(
                _suite(tmp_path / "sample.json", "metric", 0.1),
                unit=unit,
                minimum_samples=minimum,
                percentile=95,
            )

    @pytest.mark.parametrize(
        "document",
        [
            "",
            "[execution]\n",
            "[execution]\nminimum_latency_samples=true\nminimum_memory_samples=2\npercentile=95\n",
        ],
    )
    def test_rejects_incomplete_or_boolean_execution_policy(self, document, tmp_path) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import verify

        policy = tmp_path / "policy.toml"
        policy.write_text(document)
        with pytest.raises(PerformanceError, match="policy"):
            verify(policy=policy, latency=tmp_path / "missing", memory=tmp_path / "missing")

    def test_cli_reports_bad_policy_without_traceback(self, tmp_path, capsys) -> None:
        from tools.performance.verify import main

        with pytest.raises(SystemExit) as stopped:
            main(
                ("--policy", str(tmp_path / "absent"), "--latency", "unused", "--memory", "unused")
            )
        assert stopped.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "No such file" in captured.err

    @pytest.mark.parametrize(
        "field", ["minimum_latency_samples", "minimum_memory_samples", "percentile"]
    )
    def test_execution_counts_require_integers_not_booleans(self, field, tmp_path) -> None:
        from tools.performance.verify import PerformanceError
        from tools.performance.verify import verify

        policy = _policy(tmp_path / "policy.toml")
        original = f"{field} = "
        lines = policy.read_text().splitlines()
        policy.write_text(
            "\n".join(f"{field} = true" if line.startswith(original) else line for line in lines)
        )
        with pytest.raises(PerformanceError, match="distribution policy"):
            verify(
                policy=policy,
                latency=_suite(tmp_path / "latency", "metric", 0.5),
                memory=_suite(tmp_path / "memory", "memory", 512, unit="byte"),
            )
