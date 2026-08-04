"""Source-side released deployment orchestration and public mutation boundary."""

from __future__ import annotations

import tempfile
import sys
import urllib.error
from pathlib import Path
from typing import TypedDict, cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import install, projection, transaction
from codex_responses_proxy.lifecycle.deployment import apply
from codex_responses_proxy.lifecycle.supervision import process
from tests.lifecycle.fixtures import install_context, write_retired_projection
import pytest

ROOT = Path(__file__).resolve().parents[2]


class FakeTransaction:
    """Small behavioral double for the payload-owned transaction protocol."""

    def __init__(self, *, release: str = "1.2.3") -> None:
        self.release = release
        self.expected = {
            "transaction_id": "txn-release",
            "release": release,
            "manifest_sha256": "b" * 64,
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "d" * 64,
        }
        self.events: list[object] = []

    def commit_projection(self) -> None:
        self.events.append("commit")

    def finalize(self, runtime: dict[str, object] | None = None) -> None:
        self.events.append(("finalize", runtime))

    def rollback(self) -> None:
        self.events.append("rollback")

    def preserve_for_recovery(self, reason: str) -> None:
        self.events.append(("preserve", reason))


def as_transaction(value: FakeTransaction) -> "transaction.PayloadTransaction":
    """Present the behavioral double through the production transaction protocol."""

    return cast("transaction.PayloadTransaction", value)


class FakeServiceAdapter:
    """Minimal controllable implementation of the service-adapter protocol."""

    def __init__(self, *, failure: BaseException | None = None, mocker) -> None:
        self.install_mock = mocker.Mock(side_effect=failure)

    def install(self, ctx) -> None:
        self.install_mock(ctx)


class InstallArguments(TypedDict, total=False):
    trust_anchor: Path
    adapter: apply.ServiceAdapter
    rollback_recovery: bool


class TestReleasedDeployment:
    def setup_method(self) -> None:
        self.ctx = install_context(Path(tempfile.mkdtemp()))

    @staticmethod
    def _runtime(**changes: object) -> dict[str, object]:
        runtime: dict[str, object] = {
            "pid": 222,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
        }
        runtime.update(changes)
        return runtime

    def _install(
        self,
        payload: FakeTransaction,
        current: dict[str, object] | None = None,
        *,
        adapter: apply.ServiceAdapter | None = None,
        timeout_seconds: float = 30.0,
        allow_legacy_bootstrap: bool = False,
        force_legacy_bootstrap: bool = False,
        force_v2_bootstrap: bool = False,
        mocker,
    ) -> dict[str, object]:
        return apply.install(
            self.ctx,
            as_transaction(payload),
            adapter=adapter or FakeServiceAdapter(mocker=mocker),
            runtime_reader=lambda _ctx: current,
            timeout_seconds=timeout_seconds,
            allow_legacy_bootstrap=allow_legacy_bootstrap,
            force_legacy_bootstrap=force_legacy_bootstrap,
            force_v2_bootstrap=force_v2_bootstrap,
        )

    @staticmethod
    def _legacy_runtime() -> dict[str, object]:
        return {"pid": 111, "release": "1.2.2", "active_responses": 0}

    @staticmethod
    def _protocol_v2_runtime() -> dict[str, object]:
        return {
            "pid": 111,
            "handoff_protocol_version": 2,
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "release": "1.2.2",
            "serving_payload_sha256": "1" * 64,
            "payload_manifest_sha256": "2" * 64,
            "release_receipt_sha256": "3" * 64,
            "accepting": True,
            "draining": False,
        }

    @staticmethod
    def _legacy_listener() -> apply.LegacyListener:
        script = "/installed/proxy/dmx_responses_proxy.py"
        projection_state = projection.HistoricalProjection(
            "1.0.26", frozenset({"proxy/dmx_responses_proxy.py"}), script
        )
        return apply.LegacyListener(projection_state, process.OwnedProcess(111, script))

    def test_fresh_install_commits_once_then_finalizes_only_after_service_proof(
        self, *, mocker
    ) -> None:
        transaction = FakeTransaction()
        runtime = self._runtime(pid=123)
        adapter = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(process, "listener_pids", return_value=[])
        mocker.patch.object(apply, "wait_for_serving_runtime", return_value=runtime)
        result = self._install(transaction, adapter=adapter, mocker=mocker)
        assert transaction.events == ["commit", ("finalize", runtime)]
        adapter.install_mock.assert_called_once_with(self.ctx)
        assert result["mode"] == "fresh-install"

    def test_protocol_v2_upgrade_uses_source_side_handoff_and_never_installed_control(
        self, *, mocker
    ) -> None:
        transaction = FakeTransaction()
        current = self._protocol_v2_runtime()
        successor = self._runtime()
        handoff = mocker.patch.object(apply, "request_handoff", return_value=successor)
        installed_control = mocker.patch.object(apply, "load_installed_control", create=True)
        result = self._install(transaction, current, mocker=mocker)
        installed_control.assert_not_called()
        handoff.assert_called_once()
        assert transaction.events == ["commit", ("finalize", successor)]
        assert result["mode"] == "protocol-v2-upgrade"

    def test_authorized_v2_bootstrap_binds_terminates_and_proves_the_exact_listener(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction()
        current = self._protocol_v2_runtime()
        successor = self._runtime()
        adapter = FakeServiceAdapter(mocker=mocker)
        old = process.OwnedProcess(111, self.ctx.executable)
        prove = mocker.patch.object(apply, "prove_v2_listener", return_value=old)
        terminate = mocker.patch.object(process, "terminate_pid", return_value=True)
        mocker.patch.object(apply, "wait_for_serving_runtime", return_value=successor)
        result = self._install(
            payload, current, adapter=adapter, force_v2_bootstrap=True, mocker=mocker
        )
        prove.assert_called_once()
        terminate.assert_called_once_with(111, expected_path=self.ctx.executable)
        adapter.install_mock.assert_called_once_with(self.ctx)
        assert payload.events == ["commit", ("finalize", successor)]
        assert result["mode"] == "protocol-v2-bootstrap"

    def test_v2_bootstrap_failure_restores_payload_and_old_runtime(self, *, mocker) -> None:
        payload = FakeTransaction()
        current = self._protocol_v2_runtime()
        adapter = FakeServiceAdapter(mocker=mocker)
        old = process.OwnedProcess(111, self.ctx.executable)
        mocker.patch.object(apply, "prove_v2_listener", return_value=old)
        mocker.patch.object(process, "terminate_pid", return_value=True)
        mocker.patch.object(
            apply,
            "wait_for_serving_runtime",
            side_effect=errors.InstallError("successor failed"),
        )
        mocker.patch.object(apply, "wait_for_legacy_runtime", return_value=current)
        with pytest.raises(errors.InstallError, match="successor failed"):
            self._install(payload, current, adapter=adapter, force_v2_bootstrap=True, mocker=mocker)
        assert payload.events == ["commit", "rollback"]
        assert adapter.install_mock.call_count == 2

    def test_v2_bootstrap_rejects_unbound_or_non_idle_listener_before_commit(
        self, subtests, *, mocker
    ) -> None:
        payload = FakeTransaction()
        current = self._protocol_v2_runtime()
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        assert apply.prove_v2_listener(self.ctx, current) == process.OwnedProcess(
            111, self.ctx.executable
        )
        cases = (
            ({**current, "pid": True}, [111]),
            (current, []),
            ({**current, "accepting": False}, [111]),
            ({**current, "handoff_state": "ready"}, [111]),
        )
        for runtime, listeners in cases:
            mocker.patch.object(process, "verified_proxy_listener_pids", return_value=listeners)
            with (
                subtests.test(runtime=runtime, listeners=listeners),
                pytest.raises(errors.InstallError),
            ):
                self._install(payload, runtime, force_v2_bootstrap=True, mocker=mocker)
        assert payload.events == []

    def test_v2_bootstrap_reports_termination_and_rollback_failures(self, *, mocker) -> None:
        current = self._protocol_v2_runtime()
        old = process.OwnedProcess(111, self.ctx.executable)
        payload = FakeTransaction()
        mocker.patch.object(apply, "prove_v2_listener", return_value=old)
        mocker.patch.object(process, "terminate_pid", return_value=False)
        with pytest.raises(errors.InstallError, match="did not terminate"):
            self._install(payload, current, force_v2_bootstrap=True, mocker=mocker)
        assert payload.events == ["commit", "rollback"]

        payload = FakeTransaction()
        mocker.patch.object(apply, "prove_v2_listener", return_value=old)
        mocker.patch.object(process, "terminate_pid", return_value=True)
        mocker.patch.object(apply, "wait_for_serving_runtime", side_effect=RuntimeError("failed"))
        mocker.patch.object(apply, "wait_for_legacy_runtime", side_effect=RuntimeError("rollback"))
        with pytest.raises(errors.InstallError, match="runtime rollback failed"):
            self._install(payload, current, force_v2_bootstrap=True, mocker=mocker)

    def test_legacy_or_unreadable_listener_refuses_before_commit_without_authorization(
        self, subtests, *, mocker
    ) -> None:
        for current, listeners in ((self._legacy_runtime(), []), (None, [111])):
            with subtests.test(current=current):
                payload = FakeTransaction()
                mocker.patch.object(process, "listener_pids", return_value=listeners)
                with pytest.raises(errors.InstallError, match="authorized legacy bootstrap"):
                    self._install(payload, current, mocker=mocker)
                assert payload.events == []

    def test_legacy_upgrade_commits_only_after_source_side_quiet_window(self, *, mocker) -> None:
        transaction = FakeTransaction()
        current = self._legacy_runtime()
        successor = self._runtime()
        adapter = FakeServiceAdapter(mocker=mocker)
        quiet = mocker.patch.object(
            apply,
            "prove_legacy_quiet_window",
            return_value=self._legacy_listener(),
        )
        mocker.patch.object(apply, "wait_for_serving_runtime", return_value=successor)
        terminate = mocker.patch.object(process, "terminate_pid", return_value=True)
        result = self._install(
            transaction, current, adapter=adapter, allow_legacy_bootstrap=True, mocker=mocker
        )
        quiet.assert_called_once()
        terminate.assert_called_once_with(
            111, expected_path="/installed/proxy/dmx_responses_proxy.py"
        )
        adapter.install_mock.assert_called_once_with(self.ctx)
        assert transaction.events == ["commit", ("finalize", successor)]
        assert result["mode"] == "legacy-bootstrap"

    def test_unknown_handoff_outcome_preserves_transaction_instead_of_rolling_back(
        self, *, mocker
    ) -> None:
        transaction = FakeTransaction()
        current = self._protocol_v2_runtime()
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=apply.UnknownDeploymentOutcome("handoff outcome is unconfirmed"),
        )
        with pytest.raises(apply.UnknownDeploymentOutcome, match="unconfirmed"):
            self._install(transaction, current, mocker=mocker)
        assert transaction.events == ["commit", ("preserve", "handoff outcome is unconfirmed")]

    def test_fresh_install_rolls_back_after_service_or_runtime_proof_failure(
        self, subtests, *, mocker
    ) -> None:
        failures = RuntimeError("service failed"), errors.InstallError("runtime timeout")
        for service_fails, failure in enumerate(failures, start=1):
            with subtests.test(failure=failure):
                payload = FakeTransaction()
                adapter = FakeServiceAdapter(
                    failure=failure if service_fails == 1 else None, mocker=mocker
                )
                mocker.patch.object(process, "listener_pids", return_value=[])
                mocker.patch.object(
                    apply,
                    "wait_for_serving_runtime",
                    side_effect=None if service_fails == 1 else failure,
                )
                with pytest.raises(type(failure)):
                    self._install(payload, adapter=adapter, mocker=mocker)
                assert payload.events == ["commit", "rollback"]

    def test_protocol_v2_failure_rolls_back_when_the_outcome_is_proven_rolled_back(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction()
        current = self._protocol_v2_runtime()
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=errors.InstallError("handoff rolled back"),
        )
        with pytest.raises(errors.InstallError, match="rolled back"):
            self._install(payload, current, mocker=mocker)
        assert payload.events == ["commit", "rollback"]

    def test_legacy_upgrade_rolls_back_after_termination_or_successor_failure(
        self, subtests, *, mocker
    ) -> None:
        failures = (
            (False, errors.InstallError("verified legacy listener did not terminate")),
            (
                True,
                errors.InstallError("successor timeout"),
            ),
        )
        for terminated, failure in failures:
            with subtests.test(failure=failure):
                payload = FakeTransaction()
                adapter = FakeServiceAdapter(mocker=mocker)
                restored = {"pid": 333, "release": "1.0.26", "accepting": True}
                mocker.patch.object(
                    apply,
                    "prove_legacy_quiet_window",
                    return_value=self._legacy_listener(),
                )
                mocker.patch.object(process, "terminate_pid", return_value=terminated)
                mocker.patch.object(
                    apply,
                    "wait_for_serving_runtime",
                    side_effect=failure if terminated else None,
                )
                rollback_runtime = mocker.patch.object(
                    apply,
                    "wait_for_legacy_runtime",
                    return_value=restored,
                )
                with pytest.raises(type(failure), match=str(failure)):
                    self._install(
                        payload,
                        self._legacy_runtime(),
                        adapter=adapter,
                        allow_legacy_bootstrap=True,
                        mocker=mocker,
                    )
                assert payload.events == ["commit", "rollback"]
                assert adapter.install_mock.call_count == 2 * int(terminated)
                assert rollback_runtime.call_count == int(terminated)

    def test_legacy_upgrade_rolls_back_when_supervision_replacement_fails(self, *, mocker) -> None:
        payload = FakeTransaction()
        adapter = FakeServiceAdapter(mocker=mocker)
        adapter.install_mock.side_effect = [RuntimeError("service replacement failed"), None]
        mocker.patch.object(
            apply,
            "prove_legacy_quiet_window",
            return_value=self._legacy_listener(),
        )
        mocker.patch.object(process, "terminate_pid", return_value=True)
        mocker.patch.object(apply, "wait_for_legacy_runtime")
        with pytest.raises(RuntimeError, match="service replacement failed"):
            self._install(
                payload,
                self._legacy_runtime(),
                adapter=adapter,
                allow_legacy_bootstrap=True,
                mocker=mocker,
            )
        assert payload.events == ["commit", "rollback"]
        assert adapter.install_mock.call_count == 2

    def test_legacy_upgrade_reports_failed_runtime_rollback(self, *, mocker) -> None:
        payload = FakeTransaction()
        adapter = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(
            apply,
            "prove_legacy_quiet_window",
            return_value=self._legacy_listener(),
        )
        mocker.patch.object(process, "terminate_pid", return_value=True)
        mocker.patch.object(
            apply,
            "wait_for_serving_runtime",
            side_effect=errors.InstallError("successor timeout"),
        )
        mocker.patch.object(
            apply,
            "wait_for_legacy_runtime",
            side_effect=errors.InstallError("rollback timeout"),
        )
        with pytest.raises(errors.InstallError, match="runtime rollback failed: rollback timeout"):
            self._install(
                payload,
                self._legacy_runtime(),
                adapter=adapter,
                allow_legacy_bootstrap=True,
                mocker=mocker,
            )
        assert payload.events == ["commit", "rollback"]

    def test_schema_one_bootstrap_binds_integrity_listener_and_termination_to_old_entrypoint(
        self, *, mocker
    ) -> None:
        write_retired_projection(self.ctx, version="1.0.26", schema=1)
        legacy_script = str(Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py"))
        mocker.patch.object(process, "listener_pids", return_value=[111])
        mocker.patch.object(
            process,
            "process_argv",
            return_value=[sys.executable, legacy_script],
        )
        listener = apply.prove_legacy_quiet_window(
            self.ctx,
            runtime_reader=lambda _ctx: {"active_responses": 0},
            timeout_seconds=0,
            force=True,
        )
        assert listener == apply.LegacyListener(
            projection.HistoricalProjection(
                "1.0.26", frozenset(projection._RETIRED_RUNTIME_FILES[1]), legacy_script
            ),
            process.OwnedProcess(111, legacy_script),
        )

    def test_force_legacy_bootstrap_never_bypasses_historical_manifest_integrity(self) -> None:
        write_retired_projection(self.ctx, version="1.0.26", schema=1)
        Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py").write_bytes(b"tampered")
        with pytest.raises(errors.InstallError, match="integrity"):
            apply.prove_legacy_quiet_window(
                self.ctx,
                runtime_reader=lambda _ctx: {"active_responses": 0},
                timeout_seconds=0,
                force=True,
            )

    def test_request_handoff_accepts_direct_or_recovered_successor_runtime(
        self, subtests, *, mocker
    ) -> None:
        current = self._protocol_v2_runtime()
        expected = FakeTransaction().expected
        finalized = {"pid": 222, "release": "1.2.3"}
        for request_result, resolution in (
            ({"runtime": finalized}, None),
            ({"runtime": None}, ("finalized", finalized)),
        ):
            with subtests.test(resolution=resolution):
                mocker.patch.object(apply.handoff, "request", return_value=request_result)
                resolver = mocker.patch.object(
                    apply.handoff,
                    "resolve_after_controller_failure",
                    return_value=resolution,
                )
                result = apply.request_handoff(
                    self.ctx,
                    expected,
                    current=current,
                    runtime_reader=lambda _ctx: current,
                    timeout_seconds=0.5,
                )
                assert result == finalized
                assert resolver.call_count == int(resolution is not None)

    def test_request_handoff_reraises_the_original_error_after_proven_rollback(
        self, *, mocker
    ) -> None:
        current = self._protocol_v2_runtime()
        error = errors.InstallError("original handoff failure")
        mocker.patch.object(apply.handoff, "request", side_effect=error)
        mocker.patch.object(
            apply.handoff,
            "resolve_after_controller_failure",
            return_value=("rolled_back", current),
        )
        with pytest.raises(errors.InstallError, match="original handoff failure"):
            apply.request_handoff(
                self.ctx,
                FakeTransaction().expected,
                current=current,
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

    def test_legacy_quiet_window_covers_integrity_listener_force_change_idle_and_timeout(
        self, subtests, *, mocker
    ) -> None:
        def prove(
            runtime_reader: apply.RuntimeReader = lambda _ctx: None,
            *,
            timeout: float = 1,
            force: bool = False,
        ) -> apply.LegacyListener:
            return apply.prove_legacy_quiet_window(
                self.ctx,
                runtime_reader=runtime_reader,
                timeout_seconds=timeout,
                force=force,
            )

        legacy_script = str(Path(self.ctx.install_dir, "proxy", "dmx_responses_proxy.py"))
        verified_manifest = projection.HistoricalProjection(
            "1.0.26", frozenset({"proxy/dmx_responses_proxy.py"}), legacy_script
        )
        mocker.patch.object(
            projection,
            "verify_historical_projection",
            side_effect=errors.InstallError("bad"),
        )

        with pytest.raises(errors.InstallError, match="integrity"):
            prove()

        for listeners in ([], [111, 222]):
            mocker.patch.object(
                projection, "verify_historical_projection", return_value=verified_manifest
            )
            mocker.patch.object(process, "verified_listener_pids", return_value=listeners)
            with (
                subtests.test(listeners=listeners),
                pytest.raises(errors.InstallError, match="exactly one"),
            ):
                prove()
        mocker.patch.object(
            projection, "verify_historical_projection", return_value=verified_manifest
        )
        mocker.patch.object(process, "verified_listener_pids", return_value=[111])
        assert prove(
            lambda _ctx: {"active_responses": 9}, timeout=0, force=True
        ) == apply.LegacyListener(verified_manifest, process.OwnedProcess(111, legacy_script))
        mocker.patch.object(
            projection, "verify_historical_projection", return_value=verified_manifest
        )
        mocker.patch.object(process, "verified_listener_pids", side_effect=[[111], [222]])
        mocker.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1])

        with pytest.raises(errors.InstallError, match="changed"):
            prove(lambda _ctx: {"active_responses": 0})

        readings: list[dict[str, object]] = (
            [{"active_responses": value} for value in (1, 0, True, 0)]
            + [{"release": "1.2.2"}]
            + [{"active_responses": 0}] * 2
        )
        clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 6.0, 6.1, 6.2])
        mocker.patch.object(
            projection, "verify_historical_projection", return_value=verified_manifest
        )
        mocker.patch.object(process, "verified_listener_pids", return_value=[111])
        mocker.patch.object(
            apply.time,
            "monotonic",
            side_effect=lambda: next(clock),
        )
        mocker.patch.object(apply.time, "sleep")
        assert prove(lambda _ctx: readings.pop(0), timeout=10) == apply.LegacyListener(
            verified_manifest, process.OwnedProcess(111, legacy_script)
        )
        mocker.patch.object(
            projection, "verify_historical_projection", return_value=verified_manifest
        )
        mocker.patch.object(process, "verified_listener_pids", return_value=[111])
        mocker.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2])
        mocker.patch.object(apply.time, "sleep")

        with pytest.raises(errors.InstallError, match="did not remain idle"):
            prove(lambda _ctx: {"active_responses": 1}, timeout=0.15)

    def test_wait_for_serving_runtime_rejects_each_identity_and_pid_shape_then_times_out(
        self, *, mocker
    ) -> None:
        expected = FakeTransaction().expected
        matching: dict[str, object] = {
            "pid": 222,
            "release": expected["release"],
            "serving_payload_sha256": expected["serving_payload_sha256"],
            "payload_manifest_sha256": expected["manifest_sha256"],
            "release_receipt_sha256": expected["release_receipt_sha256"],
            "accepting": True,
            "draining": False,
        }
        snapshots: list[dict[str, object] | None] = [
            None,
            {**matching, "pid": True},
            {**matching, "pid": 0},
            {**matching, "pid": 222},
            {**matching, "pid": 111},
            {**matching, "release": "wrong"},
            {**matching, "serving_payload_sha256": "wrong"},
            {**matching, "payload_manifest_sha256": "wrong"},
            {**matching, "release_receipt_sha256": "wrong"},
            {**matching, "accepting": False},
            {**matching, "draining": True},
            matching,
        ]
        listener_snapshots = [[], [True], [0], [999], [111], *[[222]] * 7]
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=listener_snapshots)
        mocker.patch.object(apply.time, "sleep")
        mocker.patch.object(
            apply.time,
            "monotonic",
            side_effect=map(float, range(13)),
        )
        assert (
            apply.wait_for_serving_runtime(
                self.ctx,
                expected,
                runtime_reader=lambda _ctx: snapshots.pop(0),
                timeout_seconds=20,
                old_pid=111,
            )
            == matching
        )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[])
        mocker.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2])
        mocker.patch.object(apply.time, "sleep")

        with pytest.raises(errors.InstallError, match="SERVING identity"):
            apply.wait_for_serving_runtime(
                self.ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_wait_for_legacy_runtime_requires_exact_accepting_process_identity(
        self, *, mocker
    ) -> None:
        matching: dict[str, object] = {
            "pid": 222,
            "release": "1.0.26",
            "accepting": True,
        }
        snapshots: list[dict[str, object] | None] = [
            None,
            {**matching, "pid": True},
            {**matching, "pid": 0},
            {**matching, "pid": 999},
            {**matching, "release": "wrong"},
            {**matching, "accepting": False},
            matching,
        ]
        mocker.patch.object(
            process,
            "verified_listener_pids",
            side_effect=[[], [True], [0], [222], [222], [222], [222]],
        )
        mocker.patch.object(apply.time, "monotonic", side_effect=map(float, range(8)))
        mocker.patch.object(apply.time, "sleep")
        assert (
            apply.wait_for_legacy_runtime(
                self.ctx,
                release="1.0.26",
                entrypoint="/installed/proxy/dmx_responses_proxy.py",
                runtime_reader=lambda _ctx: snapshots.pop(0),
                timeout_seconds=10,
            )
            == matching
        )
        mocker.patch.object(process, "verified_listener_pids", return_value=[])
        mocker.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2])
        mocker.patch.object(apply.time, "sleep")
        with pytest.raises(errors.InstallError, match="historical listener rollback"):
            apply.wait_for_legacy_runtime(
                self.ctx,
                release="1.0.26",
                entrypoint="/installed/proxy/dmx_responses_proxy.py",
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_read_runtime_accepts_only_http_200_json_objects(self, *, mocker) -> None:
        class Response:
            def __init__(self, status: int, payload: bytes) -> None:
                self.status = status
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        opener = mocker.Mock()
        mocker.patch.object(apply.urllib.request, "build_opener", return_value=opener)
        opener.open.return_value = Response(200, b'{"pid": 222}')
        assert apply.read_runtime(self.ctx) == {"pid": 222}
        opener.open.return_value = Response(204, b"")
        assert apply.read_runtime(self.ctx) is None
        opener.open.return_value = Response(200, b"[]")
        assert apply.read_runtime(self.ctx) is None
        opener.open.return_value = Response(200, b"not-json")
        assert apply.read_runtime(self.ctx) is None
        opener.open.side_effect = urllib.error.URLError("offline")
        assert apply.read_runtime(self.ctx) is None


class TestInstallComposition:
    """Keep native artifact admission and installation free of Forge proof loaders."""

    def test_install_has_no_json_publication_proof_loader(self) -> None:
        assert not hasattr(install, "publication_proof_from_file")
