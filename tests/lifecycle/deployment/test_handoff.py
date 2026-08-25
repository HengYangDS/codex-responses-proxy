"""Installed same-payload reload wiring for the rolling-handoff protocol."""

from __future__ import annotations

import io
import json
import tempfile
import urllib.error
from collections.abc import Iterator
from contextlib import ExitStack
from email.message import Message
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import projection as payload_projection
from codex_responses_proxy.lifecycle.deployment import handoff
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import inventory
from codex_responses_proxy.service import runtime as service_runtime
from tests.lifecycle.fixtures import install_context
from tests.service.handoff.fixtures import Response
from tests.service.handoff.fixtures import expected_metadata
from tests.service.handoff.fixtures import idle_runtime
from tests.service.handoff.fixtures import matching_health
from tests.service.handoff.fixtures import ready_ack

ROOT = Path(__file__).resolve().parents[3]


def admit_successor(mocker, ctx, *, pid: int = 1000) -> process.OwnedProcess:
    """Admit one exact handoff-child generation for controller tests."""
    owned = process.OwnedProcess(pid, ctx.executable, 1.0)
    mocker.patch.object(process, "wait_for_executable", return_value=owned)
    mocker.patch.object(process, "owned_process_alive", return_value=True)
    return owned


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
        cases: list[tuple[dict[str, object] | None, bool]] = [
            (idle_runtime(), True),
            (
                idle_runtime(
                    handoff_state="finalized",
                    handoff_transaction_id="txn-previous-finalized",
                    handoff_capabilities=["repeatable"],
                ),
                True,
            ),
        ]
        unsupported: list[dict[str, object] | None] = [
            {"handoff_protocol_version": 1},
            {"handoff_protocol_version": 2},
            incomplete,
            idle_runtime(accepting=False),
            idle_runtime(draining=True),
            idle_runtime(handoff_state="ready"),
            {},
            None,
            {"release": "1.0.24"},
            idle_runtime(
                handoff_state="finalized",
                handoff_transaction_id="txn-legacy-finalized",
                handoff_capabilities=None,
            ),
        ]
        cases.extend((runtime, False) for runtime in unsupported)
        for runtime, supported in cases:
            with subtests.test(runtime=runtime, supported=supported):
                assert handoff.runtime_supports_handoff(runtime) is supported

    def test_deployment_strategy_requires_complete_identity_and_explicit_repeatability(
        self, subtests
    ) -> None:
        finalized = idle_runtime(
            handoff_state="finalized",
            handoff_transaction_id="txn-previous-finalized",
        )
        cases = (
            (idle_runtime(), "handoff"),
            ({**finalized, "handoff_capabilities": ["repeatable"]}, "handoff"),
            ({**finalized, "handoff_capabilities": None}, "native_generation"),
            ({**finalized, "serving_payload_sha256": None}, "unsupported"),
            ({**finalized, "accepting": False}, "unsupported"),
        )

        for runtime, expected in cases:
            with subtests.test(runtime=runtime):
                assert handoff.deployment_strategy(runtime) == expected

    def test_request_handoff_converges_without_terminating_the_old_listener(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        admit_successor(mocker, ctx)
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
                    runtime_reader=lambda _ctx: matching_health(
                        1000, expected, handoff_state="finalized"
                    ),
                    timeout_seconds=5,
                )
                assert (result["old_pid"], result["child_pid"]) == (999, 1000)
                terminate.assert_not_called()

    def test_request_handoff_waits_for_finalized_successor_identity(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        admit_successor(mocker, ctx)
        serving = matching_health(1000, expected)
        finalized = matching_health(1000, expected, handoff_state="finalized")
        mocker.patch.object(
            process,
            "verified_proxy_listener_pids",
            side_effect=[[999], [1000], [1000]],
        )
        mocker.patch.object(handoff, "post_ready", return_value=ready_ack(expected))
        runtime_reader = mocker.Mock(side_effect=[serving, finalized])
        mocker.patch.object(handoff.time, "sleep")

        result = handoff.request(
            ctx,
            expected,
            runtime_reader=runtime_reader,
            timeout_seconds=5,
        )

        assert result["runtime"] == finalized
        assert runtime_reader.call_count == 2

    def test_request_handoff_uses_process_and_protocol_identity_not_tcp_owner_projection(
        self, *, mocker
    ):
        """Treat the OS TCP-owner table as observation, not handoff authority."""
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        owned = process.OwnedProcess(1000, ctx.executable, 1.0)
        listeners = mocker.patch.object(
            process,
            "verified_proxy_listener_pids",
            side_effect=([999], [999]),
        )
        capture = mocker.patch.object(process, "wait_for_executable", return_value=owned)
        alive = mocker.patch.object(process, "owned_process_alive", return_value=True)
        mocker.patch.object(handoff, "post_ready", return_value=ready_ack(expected))
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 1.0, 10.0])
        mocker.patch.object(handoff.time, "sleep")

        result = handoff.request(
            ctx,
            expected,
            runtime_reader=lambda _ctx: matching_health(1000, expected, handoff_state="finalized"),
            timeout_seconds=1,
        )

        assert result["child_pid"] == 1000
        assert listeners.call_count == 1
        capture.assert_called_once_with(
            1000,
            ctx.executable,
            roles={service_runtime.HANDOFF_CHILD_MODE},
            timeout_seconds=1,
        )
        alive.assert_called_once_with(owned)

    def test_request_handoff_allows_ready_until_the_configured_deadline(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        admit_successor(mocker, ctx)
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]])
        ready = mocker.patch.object(handoff, "post_ready", return_value=ready_ack(expected))

        handoff.request(
            ctx,
            expected,
            runtime_reader=lambda _ctx: matching_health(1000, expected, handoff_state="finalized"),
            timeout_seconds=30,
        )

        assert ready.call_args.kwargs["timeout_seconds"] == 30

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
        open_request = mocker.patch.object(
            handoff.loopback,
            "open_request",
            return_value=Response(valid),
        )
        assert handoff.post_ready(ctx, expected)["child_pid"] == 1000
        for field, bad_value in (
            ("ok", False),
            ("state", "preparing"),
            ("protocol_version", 1),
            ("transaction_id", "wrong"),
            ("child_pid", 0),
        ):
            with subtests.test(field=field):
                open_request.return_value = Response({**valid, field: bad_value})
                with pytest.raises(errors.InstallError):
                    handoff.post_ready(ctx, expected)

    def test_expected_metadata_reads_and_validates_each_release_identity(self, *, mocker):
        root = Path(self.tempdir.name)
        manifest_path = root / inventory.MANIFEST_FILENAME

        for payload in (
            b"not-json",
            b"{}",
            json.dumps(
                {
                    "release": "1.0.25",
                    "serving_payload_sha256": "bad",
                    "release_receipt_sha256": "f" * 64,
                }
            ).encode(),
            json.dumps(
                {
                    "release": "1.0.25",
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "BAD",
                }
            ).encode(),
            json.dumps(
                {
                    "release": "",
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "f" * 64,
                }
            ).encode(),
        ):
            manifest_path.write_bytes(payload)
            with pytest.raises(errors.InstallError):
                handoff.expected_metadata(str(root))

        manifest_path.write_text(
            json.dumps(
                {
                    "release": "1.0.25",
                    "serving_payload_sha256": "a" * 64,
                    "release_receipt_sha256": "f" * 64,
                }
            ),
            encoding="utf-8",
        )
        (root / "VERSION").write_text("0.0.1\n", encoding="utf-8")
        mocker.patch.object(handoff.uuid, "uuid4", return_value=mocker.Mock(hex="txn-fixed"))
        metadata = handoff.expected_metadata(str(root))
        assert metadata["transaction_id"] == "txn-fixed"
        assert metadata["release"] == "1.0.25"
        assert metadata["manifest_sha256"] == handoff.digest.sha256_file(manifest_path)

    def test_post_ready_bounds_timing_and_rejects_transport_or_response_failures(
        self, subtests, *, mocker
    ):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        valid = json.dumps(ready_ack(expected)).encode()
        open_request = mocker.patch.object(
            handoff.loopback,
            "open_request",
            return_value=Response(valid),
        )
        handoff.post_ready(ctx, expected, lease_seconds=0.1, timeout_seconds=999)
        request = open_request.call_args.args[0]
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
                open_request.side_effect = None
                open_request.return_value = response
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
                open_request.side_effect = failure
                with pytest.raises(errors.InstallError, match=message):
                    handoff.post_ready(ctx, expected)
        assert conflict_body.closed

        oversized = expected_metadata(release="x" * handoff._MAX_BODY_BYTES)
        with pytest.raises(errors.InstallError, match="request payload is too large"):
            handoff.post_ready(ctx, oversized)

    def test_request_handoff_rejects_a_wrong_child_pid_in_the_health_snapshot(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        admit_successor(mocker, ctx)
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]])
        mocker.patch.object(
            handoff,
            "post_ready",
            return_value=ready_ack(expected),
        )
        mocker.patch.object(handoff.time, "sleep")
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 0.0, 100.0])
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
        admit_successor(mocker, ctx)
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[999], [1000]])
        mocker.patch.object(handoff, "post_ready", return_value={"child_pid": 1000})
        mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 0.0, 100.0])
        with pytest.raises(errors.InstallError, match="did not converge"):
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
                mocker.patch.object(handoff.time, "monotonic", side_effect=[0.0, 0.0, 100.0])
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
        admit_successor(mocker, ctx)
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
                successor = process.OwnedProcess(1000, ctx.executable, 1.0)
                mocker.patch.object(
                    process,
                    "capture_executable",
                    return_value=successor if name == "finalized" else None,
                )
                mocker.patch.object(process, "owned_process_alive", return_value=True)
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
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[999])
        successor = process.OwnedProcess(1000, ctx.executable, 1.0)
        mocker.patch.object(process, "capture_executable", return_value=successor)
        mocker.patch.object(process, "owned_process_alive", return_value=True)
        assert handoff.resolve_after_controller_failure(
            ctx,
            old,
            expected,
            runtime_reader=lambda _ctx: finalized,
            timeout_seconds=1,
            lease_seconds=1,
        ) == ("finalized", finalized)

    def test_failure_resolver_ignores_non_mapping_and_non_integer_runtime_pids(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        expected = expected_metadata()
        old = idle_runtime()
        invalid_runtime: dict[str, object] = {"pid": True}
        runtimes: Iterator[dict[str, object] | None] = iter(
            (
                None,
                invalid_runtime,
                matching_health(1000, expected, pid=1000, handoff_state="finalized"),
            )
        )
        mocker.patch.object(
            process,
            "verified_proxy_listener_pids",
            side_effect=[[999, 1000], [999, 1000], [1000]],
        )
        successor = process.OwnedProcess(1000, ctx.executable, 1.0)
        mocker.patch.object(process, "capture_executable", return_value=successor)
        mocker.patch.object(process, "owned_process_alive", return_value=True)
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
                assert not handoff.digest.is_sha256(value)
        assert handoff.digest.is_sha256("a" * 64)

        path = Path(self.tempdir.name) / "large.bin"
        path.write_bytes(b"a" * (1024 * 1024 + 1))
        assert len(handoff.digest.sha256_file(path)) == 64

    def test_reload_uses_handoff_without_terminating_the_old_pid_when_supported(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        Path(ctx.install_dir).mkdir(parents=True)
        mocker.patch.object(control, "read_runtime", return_value={"handoff_protocol_version": 2})
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
        assert result == {"state": "reloaded", "old_pid": 1, "new_pid": 2}

    def test_reload_rejects_v2_handoff_when_installed_payload_integrity_fails(self, *, mocker):
        ctx = install_context(Path(self.tempdir.name))
        Path(ctx.install_dir).mkdir(parents=True)
        mocker.patch.object(control, "read_runtime", return_value={"handoff_protocol_version": 2})
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
        Path(ctx.install_dir).mkdir(parents=True)
        expected = expected_metadata()
        old = idle_runtime()
        finalized = matching_health(1000, expected, pid=1000, handoff_state="finalized")
        mocker.patch.object(control, "read_runtime", return_value=old)
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
