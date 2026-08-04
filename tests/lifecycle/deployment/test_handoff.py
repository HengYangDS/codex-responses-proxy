"""Installed same-payload reload wiring for the rolling-handoff protocol."""

from __future__ import annotations

from contextlib import ExitStack

import io
import json
import tempfile
import urllib.error
from email.message import Message
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import inventory
from tests.lifecycle.fixtures import install_context
from tests.service.handoff.fixtures import (
    Response,
    expected_metadata,
    idle_runtime,
    matching_health,
    ready_ack,
)
import pytest

ROOT = Path(__file__).resolve().parents[3]


class TestControllerHandoffWiring:
    def setup_method(self):
        self._cleanups = ExitStack()
        self.tempdir = tempfile.TemporaryDirectory()
        self._cleanups.callback(self.tempdir.cleanup)

    def teardown_method(self) -> None:
        self._cleanups.close()

    def test_runtime_supports_handoff_requires_a_complete_available_identity(self, subtests):
        incomplete = idle_runtime()
        incomplete.pop("serving_payload_sha256")
        for runtime, supported in (
            (idle_runtime(), True),
            (
                idle_runtime(
                    handoff_state="finalized",
                    handoff_transaction_id="txn-previous-finalized",
                ),
                True,
            ),
            *(
                (runtime, False)
                for runtime in (
                    {"handoff_protocol_version": 1},
                    {"handoff_protocol_version": 2},
                    incomplete,
                    idle_runtime(accepting=False),
                    idle_runtime(draining=True),
                    idle_runtime(handoff_state="ready"),
                    {},
                    None,
                    {"release": "1.0.24"},
                )
            ),
        ):
            with subtests.test(runtime=runtime, supported=supported):
                assert handoff.runtime_supports_handoff(runtime) is supported

    def test_request_handoff_converges_without_terminating_the_old_listener(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        for name, listeners in (
            ("direct", [[999], [1000]]),
            ("transient dual listener", [[999], [999, 1000], [999, 1000], [1000]]),
        ):
            with subtests.test(case=name):
                mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=listeners)
                mocker.patch.object(handoff, "post_ready", return_value=ready_ack(expected))
                mocker.patch.object(handoff.time, "sleep")
                terminate = mocker.patch.object(process, "terminate_pid")
                result = handoff.request(
                    ctx,
                    expected,
                    runtime_reader=lambda _ctx: matching_health(1000, expected),
                    timeout_seconds=5,
                )
                assert (result["old_pid"], result["child_pid"]) == (999, 1000)
                terminate.assert_not_called()

    def test_request_handoff_rejects_invalid_listener_ownership_or_control_conflict(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        cases = (
            ("ambiguous listener", [888, 999], None, "exactly one verified"),
            (
                "in-progress conflict",
                [999],
                errors.InstallError("handoff control returned HTTP 409"),
                "409",
            ),
        )
        for name, listeners, failure, message in cases:
            with subtests.test(case=name):
                mocker.patch.object(process, "verified_proxy_listener_pids", return_value=listeners)
                mocker.patch.object(handoff, "post_ready", side_effect=failure)
                with pytest.raises(errors.InstallError, match=message):
                    handoff.request(
                        ctx,
                        expected,
                        runtime_reader=lambda _ctx: None,
                        timeout_seconds=1,
                    )

    def test_handoff_post_requires_a_complete_protocol_v2_ready_acknowledgement(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        valid = ready_ack(expected)
        opener = mocker.Mock()
        mocker.patch.object(handoff.urllib.request, "build_opener", return_value=opener)
        opener.open.return_value = Response(valid)
        assert handoff.post_ready(ctx, expected)["child_pid"] == 1000
        for field, bad_value in (
            ("ok", False),
            ("state", "preparing"),
            ("protocol_version", 1),
            ("transaction_id", "wrong"),
            ("child_pid", 0),
        ):
            with subtests.test(field=field):
                opener.open.return_value = Response({**valid, field: bad_value})
                with pytest.raises(errors.InstallError):
                    handoff.post_ready(ctx, expected)

    def test_expected_metadata_reads_and_validates_each_release_identity(self, *, mocker):
        root = Path(self.tempdir.name)
        manifest_path = root / inventory.MANIFEST_FILENAME

        with pytest.raises(errors.InstallError, match="VERSION"):
            handoff.expected_metadata(str(root))
        (root / "VERSION").write_text("\n", encoding="utf-8")
        with pytest.raises(errors.InstallError, match="no release version"):
            handoff.expected_metadata(str(root))

        (root / "VERSION").write_text("1.0.25\n", encoding="utf-8")
        for payload in (
            b"not-json",
            b"{}",
            json.dumps(
                {
                    "serving_payload_sha256": "bad",
                    "release_receipt_sha256": "f" * 64,
                }
            ).encode(),
            json.dumps(
                {
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "BAD",
                }
            ).encode(),
        ):
            manifest_path.write_bytes(payload)
            with pytest.raises(errors.InstallError):
                handoff.expected_metadata(str(root))

        manifest_path.write_text(
            json.dumps(
                {
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "f" * 64,
                }
            ),
            encoding="utf-8",
        )
        mocker.patch.object(handoff.uuid, "uuid4", return_value=mocker.Mock(hex="txn-fixed"))
        metadata = handoff.expected_metadata(str(root))
        assert metadata["transaction_id"] == "txn-fixed"
        assert metadata["release"] == "1.0.25"
        assert metadata["manifest_sha256"] == handoff._sha256_file(str(manifest_path))

    def test_post_ready_bounds_timing_and_rejects_transport_or_response_failures(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        valid = json.dumps(ready_ack(expected)).encode()
        opener = mocker.Mock()
        mocker.patch.object(handoff.urllib.request, "build_opener", return_value=opener)
        opener.open.return_value = Response(valid)
        handoff.post_ready(ctx, expected, lease_seconds=0.1, timeout_seconds=999)
        request = opener.open.call_args.args[0]
        body = json.loads(request.data)
        assert body["lease_seconds"] == 1
        assert body["timeout_seconds"] == 120

        failures = (
            (Response(valid, status=500), "returned HTTP 500"),
            (Response(b"x" * (handoff._MAX_BODY_BYTES + 1)), "response is too large"),
            (Response(b"[]"), "invalid response"),
        )
        for response, message in failures:
            with subtests.test(message=message):
                opener.open.side_effect = None
                opener.open.return_value = response
                with pytest.raises(errors.InstallError, match=message):
                    handoff.post_ready(ctx, expected)

        conflict_body = io.BytesIO(b"conflict")
        for failure, message in (
            (
                urllib.error.HTTPError("url", 409, "conflict", Message(), conflict_body),
                "HTTP 409",
            ),
            (urllib.error.URLError("offline"), "unavailable"),
            (ValueError("bad timeout"), "unavailable"),
        ):
            with subtests.test(failure=type(failure).__name__):
                opener.open.side_effect = failure
                with pytest.raises(errors.InstallError, match=message):
                    handoff.post_ready(ctx, expected)
        assert conflict_body.closed

        oversized = expected_metadata(release="x" * handoff._MAX_BODY_BYTES)
        with pytest.raises(errors.InstallError, match="request payload is too large"):
            handoff.post_ready(ctx, oversized)

    def test_request_handoff_rejects_a_wrong_child_pid_in_the_health_snapshot(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]])
        mocker.patch.object(
            handoff,
            "post_ready",
            return_value=ready_ack(expected),
        )
        mocker.patch.object(handoff.time, "sleep")
        with pytest.raises(errors.InstallError):
            handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: matching_health(1000, expected, pid=4242),
                timeout_seconds=1,
            )

    def test_request_handoff_rejects_each_runtime_field_mismatch(self, subtests, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]])
        mocker.patch.object(handoff, "post_ready", return_value={"child_pid": 1000})
        with pytest.raises(errors.InstallError, match="did not match"):
            handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=1,
            )
        overrides = {
            "handoff_protocol_version": 1,
            "handoff_transaction_id": "wrong-txn",
            "release": "1.0.24",
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "e" * 64,
            "payload_manifest_sha256": "d" * 64,
            "accepting": False,
            "draining": True,
            "handoff_state": "ready",
        }
        for field, bad_value in overrides.items():
            with subtests.test(field=field):
                runtime = matching_health(1000, expected, **{field: bad_value})
                mocker.patch.object(
                    process, "verified_proxy_listener_pids", side_effect=[[999], [1000]]
                )
                mocker.patch.object(
                    handoff,
                    "post_ready",
                    return_value=ready_ack(expected),
                )
                mocker.patch.object(handoff.time, "sleep")
                with pytest.raises(errors.InstallError):
                    handoff.request(
                        ctx,
                        expected,
                        runtime_reader=lambda _ctx, snapshot=runtime: snapshot,
                        timeout_seconds=1,
                    )

    def test_request_handoff_times_out_before_the_child_listener_converges(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[999])
        mocker.patch.object(
            handoff,
            "post_ready",
            return_value={"child_pid": 1000},
        )
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 10.0])
        mocker.patch.object(handoff.time, "sleep")
        with pytest.raises(errors.InstallError, match="did not converge"):
            handoff.request(
                ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=1,
                lease_seconds=1,
            )

    def test_wait_for_rollback_accepts_only_the_exact_resumed_runtime_and_times_out(
        self, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        old = idle_runtime()
        mismatches = (
            None,
            idle_runtime(pid=123),
            idle_runtime(serving_payload_sha256="c" * 64),
            idle_runtime(release_receipt_sha256="c" * 64),
            idle_runtime(payload_manifest_sha256="c" * 64),
            idle_runtime(handoff_protocol_version=1),
            idle_runtime(handoff_state="finalized"),
            idle_runtime(handoff_transaction_id="txn"),
            idle_runtime(accepting=False),
            idle_runtime(draining=True),
        )
        runtimes = iter((*mismatches, old))
        listeners = ([123], *([[999]] * (len(mismatches) + 1)))
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=listeners)
        mocker.patch.object(handoff.time, "monotonic", side_effect=range(20))
        mocker.patch.object(handoff.time, "sleep")
        assert (
            handoff.wait_for_rollback(
                ctx, old, runtime_reader=lambda _ctx: next(runtimes), timeout_seconds=20
            )
            == old
        )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[1000])
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 0.1, 0.2])
        mocker.patch.object(handoff.time, "sleep")

        with pytest.raises(errors.InstallError, match="did not resume"):
            handoff.wait_for_rollback(
                ctx,
                old,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_failure_resolver_classifies_finalized_rolled_back_and_unknown_states(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        finalized = matching_health(1000, expected, pid=1000, handoff_state="finalized")
        cases = (
            ("finalized", [1000], finalized, ("finalized", finalized)),
            ("rolled_back", [999], old, ("rolled_back", old)),
        )
        for name, listeners, runtime, expected_result in cases:
            with subtests.test(name=name):
                mocker.patch.object(process, "verified_proxy_listener_pids", return_value=listeners)
                assert (
                    handoff.resolve_after_controller_failure(
                        ctx,
                        old,
                        expected,
                        runtime_reader=lambda _ctx, snapshot=runtime: snapshot,
                        timeout_seconds=1,
                        lease_seconds=1,
                    )
                    == expected_result
                )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[999, 1000])
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 8.0])
        mocker.patch.object(handoff.time, "sleep")
        assert handoff.resolve_after_controller_failure(
            ctx,
            old,
            expected,
            runtime_reader=lambda _ctx: finalized,
            timeout_seconds=1,
            lease_seconds=1,
        ) == ("unknown", None)

    def test_failure_resolver_ignores_non_mapping_and_non_integer_runtime_pids(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        runtimes = iter((None, {"pid": True}, matching_health(1000, expected, pid=1000)))
        mocker.patch.object(
            process,
            "verified_proxy_listener_pids",
            side_effect=[[999, 1000], [999, 1000], [1000]],
        )
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 2.0, 3.0])
        mocker.patch.object(handoff.time, "sleep")
        assert (
            handoff.resolve_after_controller_failure(
                ctx,
                old,
                expected,
                runtime_reader=lambda _ctx: next(runtimes),
                timeout_seconds=10,
                lease_seconds=1,
            )[0]
            == "finalized"
        )

    def test_digest_helpers_reject_noncanonical_values_and_hash_large_files(self, subtests):
        for value in (None, "a" * 63, "g" * 64, "A" * 64):
            with subtests.test(value=value):
                assert not handoff._valid_sha256(value)
        assert handoff._valid_sha256("a" * 64)

        path = Path(self.tempdir.name) / "large.bin"
        path.write_bytes(b"a" * (1024 * 1024 + 1))
        assert len(handoff._sha256_file(str(path))) == 64

    def test_reload_uses_handoff_without_terminating_the_old_pid_when_supported(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        mocker.patch.object(
            control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
        )
        mocker.patch.object(handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            payload_projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(handoff, "expected_metadata", return_value=expected_metadata())
        request_handoff = mocker.patch.object(
            handoff,
            "request",
            return_value={"old_pid": 1, "child_pid": 2, "release": "1.0.25"},
        )
        terminate = mocker.patch.object(process, "terminate_pid")
        result = control.reload(ctx, timeout_seconds=5)
        request_handoff.assert_called_once()
        terminate.assert_not_called()
        assert result == {"old_pid": 1, "new_pid": 2}

    def test_reload_rejects_v2_handoff_when_installed_payload_integrity_fails(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        mocker.patch.object(
            control, "_runtime_metrics", return_value={"handoff_protocol_version": 2}
        )
        mocker.patch.object(handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            payload_projection,
            "verify_payload_manifest",
            return_value=(False, "hash mismatch"),
        )
        request_handoff = mocker.patch.object(handoff, "request")
        with pytest.raises(errors.InstallError, match="integrity"):
            control.reload(ctx, timeout_seconds=5)
        request_handoff.assert_not_called()

    def test_reload_recovers_a_finalized_result_after_controller_failure(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        finalized = matching_health(1000, expected, pid=1000, handoff_state="finalized")
        mocker.patch.object(control, "_runtime_metrics", return_value=old)
        mocker.patch.object(handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            payload_projection, "verify_payload_manifest", return_value=(True, "ok")
        )
        mocker.patch.object(handoff, "expected_metadata", return_value=expected)
        mocker.patch.object(handoff, "request", side_effect=KeyboardInterrupt())
        mocker.patch.object(
            handoff,
            "resolve_after_controller_failure",
            return_value=("finalized", finalized),
        )
        result = control.reload(ctx, timeout_seconds=5)
        assert result["new_pid"] == 1000
        assert result["recovered_after_controller_failure"]
