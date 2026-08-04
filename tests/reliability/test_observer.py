"""Focused contracts for source-side reliability observation policy."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_VARIANT_CLASS = "input_variant_validation_error"
INPUT_VARIANT_REASON = "upstream_input_variant_validation_burst"


def _observer():
    spec = importlib.util.spec_from_file_location(
        "dmx_reliability_observer_for_focused_test",
        ROOT / "tools" / "reliability" / "observe.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status(
    *,
    release: str = "1.0.27",
    digest: str = "a" * 64,
    uptime: int = 100,
    integrity: bool = True,
    service: str = "running",
    listeners: list[int] | None = None,
    draining: bool = False,
    counters: dict[str, int] | None = None,
    upstream: dict[str, int] | None = None,
    last_failure: str | None = None,
):
    runtime = {
        "release": release,
        "serving_payload_sha256": digest,
        "uptime_seconds": uptime,
        "active_responses": 0,
        "draining": draining,
        "counters": counters or {},
        "upstream_classifications": upstream or {},
    }
    if last_failure is not None:
        runtime["last_failure"] = {"classification": last_failure, "at_unix": 1}
    return {
        "payload_integrity": {"ok": integrity, "detail": "redacted"},
        "service": service,
        "listener_pids": listeners if listeners is not None else [123],
        "runtime": runtime,
    }


class ObserverCase:
    def setup_method(self) -> None:
        self.observer = _observer()

    def delta(self, before, after, **kwargs):
        _, baseline = self.observer.evaluate(_status(**before), observed_at_unix=10)
        return self.observer.evaluate(
            _status(uptime=110, **after), baseline, observed_at_unix=20, **kwargs
        )[0]


class TestInputVariantObservation(ObserverCase):
    """Keep the exact input-variant class separate from generic validation."""

    def _evaluate_delta(self, count: int):
        return self.delta(
            {"upstream": {INPUT_VARIANT_CLASS: 7}},
            {"upstream": {INPUT_VARIANT_CLASS: 7 + count}},
        )

    def test_one_or_two_exact_input_variant_events_require_observation(self, subtests):
        for count in (1, 2):
            with subtests.test(count=count):
                report = self._evaluate_delta(count)
                reasons = [
                    item for item in report["reasons"] if item["code"] == INPUT_VARIANT_REASON
                ]
                assert report["state"] == "observe"
                assert [item["severity"] for item in reasons] == ["observe"]
                assert report["deltas"]["upstream_classifications"] == {INPUT_VARIANT_CLASS: count}

    def test_three_exact_input_variant_events_are_an_incident(self):
        report = self._evaluate_delta(3)
        reasons = [item for item in report["reasons"] if item["code"] == INPUT_VARIANT_REASON]
        assert report["state"] == "incident"
        assert [item["severity"] for item in reasons] == ["incident"]

    def test_unknown_validation_class_is_not_treated_as_input_variant(self):
        report = self.delta(
            {"upstream": {"validation_error": 4}}, {"upstream": {"validation_error": 7}}
        )
        assert report["state"] == "healthy"
        assert report["reasons"] == []
        assert report["deltas"]["upstream_classifications"] == {"validation_error": 3}


class TestReliabilityWindowPolicy(ObserverCase):
    """Keep lifetime counters distinct from bounded observation windows."""

    def test_first_snapshot_does_not_reclassify_lifetime_counts_as_an_incident(self) -> None:
        report, baseline = self.observer.evaluate(
            _status(
                counters={"streams_failed": 7},
                upstream={"empty_response": 23},
                last_failure="wire_failure_recovery_exhausted",
            ),
            observed_at_unix=1000,
        )
        assert report["state"] == "observe"
        assert report["window"]["comparison"] == "baseline_absent"
        assert report["deltas"] == {"counters": {}, "upstream_classifications": {}}
        assert baseline["upstream_classifications"]["empty_response"] == 23

    def test_upstream_empty_response_threshold_is_windowed_and_explicit(self) -> None:
        observe = self.delta(
            {"upstream": {"empty_response": 10}}, {"upstream": {"empty_response": 11}}
        )
        incident = self.delta(
            {"upstream": {"empty_response": 10}}, {"upstream": {"empty_response": 13}}
        )
        assert observe["state"] == "observe"
        assert incident["state"] == "incident"
        assert incident["deltas"]["upstream_classifications"] == {"empty_response": 3}
        assert "upstream_empty_response_burst" in [item["code"] for item in incident["reasons"]]

    def test_upstream_5xx_and_response_failed_have_separate_thresholds(self) -> None:
        report = self.delta(
            {"upstream": {"http_503_full": 2, "response_failed": 8}},
            {"upstream": {"http_503_full": 5, "response_failed": 11}},
        )
        codes = {item["code"] for item in report["reasons"]}
        assert report["state"] == "incident"
        assert report["deltas"]["upstream_classifications"] == {
            "http_503_full": 3,
            "response_failed": 3,
        }
        assert "upstream_5xx_burst" in codes
        assert "upstream_response_failed_burst" in codes

    def test_proxy_drain_is_not_conflated_with_upstream_failure(self) -> None:
        before = {"counters": {"responses_rejected_while_draining": 4}}
        after = {"counters": {"responses_rejected_while_draining": 5}}
        incident = self.delta(before, after)
        maintenance = self.delta(before, after, allow_drain=True)
        assert incident["state"] == "incident"
        assert maintenance["state"] == "observe"
        assert "upstream_empty_response_burst" not in [item["code"] for item in incident["reasons"]]

    def test_local_stream_failure_and_payload_integrity_are_incidents(self) -> None:
        stream_report = self.delta(
            {"counters": {"streams_failed": 2}}, {"counters": {"streams_failed": 3}}
        )
        integrity_report, _ = self.observer.evaluate(
            _status(integrity=False, listeners=[]), observed_at_unix=10
        )
        assert stream_report["state"] == "incident"
        assert "local_stream_failed" in [item["code"] for item in stream_report["reasons"]]
        assert integrity_report["state"] == "incident"
        assert "payload_integrity_failed" in [item["code"] for item in integrity_report["reasons"]]
        assert "listener_cardinality" in [item["code"] for item in integrity_report["reasons"]]

    def test_changed_runtime_starts_new_window_and_state_has_no_payload_snapshot(self) -> None:
        _, baseline = self.observer.evaluate(
            _status(digest="a" * 64, upstream={"empty_response": 10}), observed_at_unix=10
        )
        report, next_baseline = self.observer.evaluate(
            _status(digest="b" * 64, uptime=1, upstream={"empty_response": 40}),
            baseline,
            observed_at_unix=20,
        )
        assert report["state"] == "observe"
        assert report["window"]["comparison"] == "runtime_identity_changed"
        assert report["deltas"]["upstream_classifications"] == {}
        assert "payload_integrity" not in next_baseline
        assert "last_failure" not in next_baseline
