"""Focused contracts for source-side reliability observation policy."""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

from tools.reliability import observe

INPUT_VARIANT_CLASS = "input_variant_validation_error"
INPUT_VARIANT_REASON = "upstream_input_variant_validation_burst"


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
        self.observer = observe

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

    def test_first_snapshot_does_not_reclassify_lifetime_counts_as_an_incident(
        self,
    ) -> None:
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

    def test_changed_runtime_starts_new_window_and_state_has_no_payload_snapshot(
        self,
    ) -> None:
        _, baseline = self.observer.evaluate(
            _status(digest="a" * 64, upstream={"empty_response": 10}),
            observed_at_unix=10,
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

    @pytest.mark.parametrize(("count", "state"), [(1, "observe"), (3, "incident")])
    def test_upstream_stream_server_errors_share_the_response_failure_window(self, count, state):
        report = self.delta(
            {"upstream": {"sse_server_error": 9}},
            {"upstream": {"sse_server_error": 9 + count}},
        )
        assert report["state"] == state
        reasons = [
            item for item in report["reasons"] if item["code"] == "upstream_response_failed_burst"
        ]
        assert len(reasons) == 1
        assert reasons[0]["severity"] == state

    def test_unclassified_stream_failure_is_not_assumed_transient(self):
        report = self.delta({}, {"upstream": {"sse_unknown": 10}})
        assert report["state"] == "healthy"
        assert report["reasons"] == []


class TestObservationBoundaries(ObserverCase):
    @pytest.mark.parametrize(
        ("key", "value"),
        [("runtime", None), ("payload_integrity", {}), ("service", 4), ("listener_pids", [True])],
    )
    def test_rejects_malformed_status_envelopes(self, key, value):
        status = _status()
        status[key] = value
        with pytest.raises(self.observer.ObservationError):
            self.observer.normalize_status(status)

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("release", ""),
            ("serving_payload_sha256", "bad"),
            ("draining", 1),
            ("active_responses", True),
            ("uptime_seconds", -1),
            ("counters", []),
            ("counters", {"": 0}),
            ("upstream_classifications", {"x" * 97: 1}),
        ],
    )
    def test_rejects_invalid_runtime_fields(self, key, value):
        status = _status()
        status["runtime"][key] = value
        with pytest.raises(self.observer.ObservationError):
            self.observer.normalize_status(status)

    @pytest.mark.parametrize("value", [None, [], 0])
    def test_requires_a_status_object(self, value):
        with pytest.raises(self.observer.ObservationError, match="JSON object"):
            self.observer.normalize_status(value)

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"uptime_seconds": True}, "baseline_invalid"),
            ({"uptime_seconds": 200}, "runtime_restarted"),
            ({"counters": []}, "baseline_invalid"),
        ],
    )
    def test_incomparable_baselines_do_not_fabricate_incidents(self, changes, reason):
        _, baseline = self.observer.evaluate(_status(), observed_at_unix=10)
        baseline.update(changes)
        report, _ = self.observer.evaluate(_status(), baseline, observed_at_unix=20)
        assert report["window"]["comparison"] == reason
        assert report["deltas"] == {"counters": {}, "upstream_classifications": {}}

    @pytest.mark.parametrize("old", [True, -1, 2])
    def test_counter_history_cannot_be_invalid_or_reversed(self, old):
        with pytest.raises(self.observer.ObservationError):
            self.observer._delta({"streams_failed": 1}, {"streams_failed": old})

    @pytest.mark.parametrize(("service", "severity"), [(None, "observe"), ("stopped", "incident")])
    def test_service_and_maintenance_have_distinct_meaning(self, service, severity):
        report, _ = self.observer.evaluate(
            _status(service=service, draining=True), observed_at_unix=10
        )
        reasons = {item["code"]: item for item in report["reasons"]}
        assert reasons["service_not_running"]["severity"] == severity
        assert reasons["drain_active"]["severity"] == "observe"

    def test_cli_persists_only_normalized_baseline_and_accepts_stdin(
        self, tmp_path, mocker, capsys
    ):
        state = tmp_path / "state" / "baseline.json"
        status = _status()
        status["private"] = "do-not-persist"
        mocker.patch.object(sys, "stdin", io.StringIO(json.dumps(status)))
        assert self.observer.main(["--state", str(state)]) == 0
        first = json.loads(capsys.readouterr().out)
        assert first["state"] == "observe"
        assert "do-not-persist" not in state.read_text()
        assert not list(state.parent.glob(".baseline.json.*"))
        source = tmp_path / "status.json"
        source.write_text(json.dumps(_status(uptime=110)))
        assert self.observer.main(["--status-file", str(source), "--state", str(state)]) == 0
        second = json.loads(capsys.readouterr().out)
        assert second["state"] == "healthy"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission-bit contract")
    def test_state_has_private_posix_permissions(self, tmp_path):
        state = tmp_path / "state" / "baseline.json"
        _, baseline = self.observer.evaluate(_status(), observed_at_unix=10)
        self.observer._write_state(state, baseline)
        assert state.stat().st_mode & 0o777 == 0o600
        assert state.parent.stat().st_mode & 0o777 == 0o700

    @pytest.mark.parametrize(
        "document", ["{", "[]", '{"schema_version":2}', '{"schema_version":1}']
    )
    def test_state_file_validation_rejects_invalid_baselines(self, document, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(document)
        with pytest.raises(self.observer.ObservationError):
            self.observer._load_state(path)

    @pytest.mark.parametrize("version", [True, 1.0, "1"])
    def test_state_schema_requires_integer(self, version, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"schema_version": version, "baseline": {}}))
        with pytest.raises(self.observer.ObservationError, match="schema"):
            self.observer._load_state(path)

    def test_dangling_state_symlink_is_rejected(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.symlink_to(tmp_path / "absent")
        with pytest.raises(self.observer.ObservationError, match="regular file"):
            self.observer._load_state(path)

    def test_failed_state_replacement_retains_previous_file_and_removes_scratch(
        self, tmp_path, mocker
    ):
        path = tmp_path / "baseline.json"
        path.write_bytes(b"previous")
        mocker.patch.object(self.observer.os, "replace", side_effect=OSError("injected"))
        with pytest.raises(OSError, match="injected"):
            self.observer._write_state(path, {})
        assert path.read_bytes() == b"previous"
        assert sorted(tmp_path.iterdir()) == [path]

    def test_state_symlink_never_overwrites_its_target(self, tmp_path):
        target = tmp_path / "target"
        target.write_bytes(b"preserve")
        link = tmp_path / "link"
        link.symlink_to(target)
        with pytest.raises(self.observer.ObservationError):
            self.observer._write_state(link, {})
        assert target.read_bytes() == b"preserve"

    def test_cli_bad_input_returns_error_without_baseline_write(self, tmp_path, capsys):
        source = tmp_path / "invalid.json"
        source.write_text("{")
        state = tmp_path / "state.json"
        assert self.observer.main(["--status-file", str(source), "--state", str(state)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "status snapshot is unreadable" in captured.err
        assert not state.exists()

    def test_state_directory_and_invalid_identity_are_rejected(self, tmp_path):
        with pytest.raises(self.observer.ObservationError, match="regular file"):
            self.observer._load_state(tmp_path)
        with pytest.raises(self.observer.ObservationError, match="runtime must be an object"):
            self.observer._runtime_identity({"runtime": None})

    def test_state_permission_failure_closes_descriptor_and_removes_temporary_file(
        self, tmp_path, mocker
    ):
        path = tmp_path / "state.json"
        close = mocker.spy(self.observer.os, "close")
        mocker.patch.object(self.observer.os, "chmod", side_effect=PermissionError("injected"))
        with pytest.raises(PermissionError, match="injected"):
            self.observer._write_state(path, {})
        close.assert_called_once()
        assert list(tmp_path.iterdir()) == []

    def test_snapshot_without_state_uses_clock_and_never_persists(self, mocker, capsys):
        mocker.patch.object(sys, "stdin", io.StringIO(json.dumps(_status())))
        mocker.patch.object(self.observer.time, "time", return_value=123.5)
        write = mocker.patch.object(self.observer, "_write_state")
        assert self.observer.main([]) == 0
        assert json.loads(capsys.readouterr().out)["observed_at_unix"] == 123
        write.assert_not_called()

    def test_future_baseline_time_is_not_a_negative_observation_window(self):
        _, baseline = self.observer.evaluate(_status(), observed_at_unix=100)
        report, _ = self.observer.evaluate(_status(), baseline, observed_at_unix=90)
        assert report["window"]["comparable"]
        assert "seconds" not in report["window"]

    def test_equal_counter_is_not_a_new_event(self):
        assert self.observer._delta({"x": 2}, {"x": 2}) == {}
