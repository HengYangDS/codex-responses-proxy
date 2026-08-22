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
        from tools.performance.verify import PerformanceError, verify

        policy = _policy(tmp_path / "policy.toml", maximum=maximum)
        with pytest.raises(PerformanceError):
            verify(
                policy=policy,
                latency=_suite(tmp_path / "latency.json", "metric", observed),
                memory=_suite(tmp_path / "memory.json", "memory", 512, unit="byte"),
            )

    def test_rejects_missing_and_undeclared_metrics(self, tmp_path: Path) -> None:
        from tools.performance.verify import PerformanceError, verify

        with pytest.raises(PerformanceError, match=r"missing.*undeclared"):
            verify(
                policy=_policy(tmp_path / "policy.toml"),
                latency=_suite(tmp_path / "latency.json", "other", 0.5),
                memory=_suite(tmp_path / "memory.json", "memory", 512, unit="byte"),
            )
