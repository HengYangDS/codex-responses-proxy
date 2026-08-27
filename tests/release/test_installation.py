"""Released deployment orchestration contracts."""

from __future__ import annotations

import tempfile
import urllib.error
from pathlib import Path
from typing import cast
from typing import override

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import install
from codex_responses_proxy.lifecycle import rollback as payload_rollback
from codex_responses_proxy.lifecycle import transaction
from codex_responses_proxy.lifecycle.deployment import apply
from codex_responses_proxy.lifecycle.supervision import process
from codex_responses_proxy.service import identity
from codex_responses_proxy.service import runtime as service_runtime
from tests.lifecycle.fixtures import install_context


class FakeTransaction:
    """Behavioral double for the payload transaction protocol."""

    def __init__(self, ctx, *, events: list[object] | None = None) -> None:
        """Initialize an observable payload-transaction double."""
        transaction_id = "1" * 32
        self.expected = {
            "transaction_id": transaction_id,
            "release": "1.2.3",
            "manifest_sha256": "b" * 64,
            "serving_payload_sha256": "c" * 64,
            "release_receipt_sha256": "d" * 64,
        }
        self.events = events if events is not None else []
        self.context = generation.context(ctx, transaction_id)

    def commit_projection(self) -> None:
        self.events.append("commit")

    def activate(self) -> None:
        self.events.append("activate")

    def finalize(self, runtime: dict[str, object] | None = None) -> None:
        self.events.append(("finalize", runtime))

    def rollback(self) -> None:
        self.events.append("rollback")

    def preserve_for_recovery(self, reason: str) -> None:
        self.events.append(("preserve", reason))


def as_transaction(value: FakeTransaction) -> transaction.PayloadTransaction:
    return cast("transaction.PayloadTransaction", value)


def retained_identity(release: str) -> identity.LoadedPayloadIdentity:
    """Build the identity surface needed by reverse deployment tests."""
    return identity.LoadedPayloadIdentity(
        release=release,
        serving_payload_sha256="a" * 64,
        release_receipt_sha256="b" * 64,
        manifest_sha256="c" * 64,
        root=Path("/retained") / release,
    )


class FakeServiceAdapter:
    """Record native-service calls and expose a configured executable."""

    def __init__(
        self,
        *,
        failure: BaseException | None = None,
        configured: str | None = "canonical",
        mocker,
    ) -> None:
        """Initialize the adapter with an optional installation failure."""
        self.install_mock = mocker.Mock(side_effect=failure)
        self.uninstall_mock = mocker.Mock()
        self.configured = configured
        self.running_contexts: set[str] = set()

    def install(self, ctx) -> None:
        self.install_mock(ctx)
        self.configured = "canonical"
        self.running_contexts.add(ctx.executable)

    def uninstall(self, ctx) -> None:
        self.uninstall_mock(ctx)
        self.configured = None
        self.running_contexts.discard(ctx.executable)

    def runtime_pids(self, ctx) -> list[int]:
        return [222] if ctx.executable in self.running_contexts else []

    def terminate_runtime(self, ctx, *, timeout_seconds: float) -> int:
        del timeout_seconds
        running = self.runtime_pids(ctx)
        self.running_contexts.discard(ctx.executable)
        return len(running)

    def configured_executable(self, ctx) -> str | None:
        configured = ctx.executable if self.configured == "canonical" else self.configured
        return configured if isinstance(configured, str) else None


class OrderedServiceAdapter(FakeServiceAdapter):
    """Record the service rebind in the same event stream as the transaction."""

    def __init__(self, events: list[object], *, mocker) -> None:
        super().__init__(mocker=mocker)
        self.events = events

    @override
    def install(self, ctx) -> None:
        self.events.append("service-install")
        super().install(ctx)

    @override
    def uninstall(self, ctx) -> None:
        self.events.append("service-uninstall")
        super().uninstall(ctx)


class TestReleasedDeployment:
    def setup_method(self) -> None:
        self.ctx = install_context(Path(tempfile.mkdtemp()))

    @pytest.fixture(autouse=True)
    def _admit_current_listener(self, mocker) -> None:
        """Model the exact predecessor process identity used by every upgrade."""
        mocker.patch.object(
            process,
            "capture_executable",
            return_value=process.OwnedProcess(111, self.ctx.executable, 1.0),
        )
        mocker.patch.object(process, "listener_pids", return_value=[111])
        mocker.patch.object(process, "owned_process_alive", return_value=True)

    @staticmethod
    def current_runtime(**changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "pid": 111,
            "handoff_protocol_version": 2,
            "handoff_capabilities": ["selected-generation-handoff"],
            "handoff_state": "idle",
            "handoff_transaction_id": None,
            "release": "1.2.2",
            "serving_payload_sha256": "1" * 64,
            "payload_manifest_sha256": "2" * 64,
            "release_receipt_sha256": "3" * 64,
            "accepting": True,
            "draining": False,
        }
        value.update(changes)
        return value

    @staticmethod
    def successor(**changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "pid": 222,
            "release": "1.2.3",
            "serving_payload_sha256": "c" * 64,
            "payload_manifest_sha256": "b" * 64,
            "release_receipt_sha256": "d" * 64,
            "accepting": True,
            "draining": False,
        }
        value.update(changes)
        return value

    def deploy(
        self,
        payload: FakeTransaction,
        current: dict[str, object] | None,
        *,
        adapter: FakeServiceAdapter | None = None,
        timeout_seconds: float = 30,
        mocker,
    ) -> dict[str, object]:
        return apply.install(
            self.ctx,
            as_transaction(payload),
            adapter=adapter or FakeServiceAdapter(mocker=mocker),
            runtime_reader=lambda _ctx: current,
            timeout_seconds=timeout_seconds,
        )

    def test_fresh_install_commits_and_finalizes_after_runtime_proof(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        service = FakeServiceAdapter(mocker=mocker)
        runtime = self.successor(pid=123)
        mocker.patch.object(process, "listener_pids", return_value=[])
        mocker.patch.object(apply, "wait_for_serving_runtime", return_value=runtime)

        result = self.deploy(payload, None, adapter=service, mocker=mocker)

        assert result == {"state": "installed", "runtime": runtime}
        assert payload.events == ["commit", "activate", ("finalize", runtime)]
        service.install_mock.assert_called_once_with(payload.context)

    def test_current_upgrade_rebinds_supervision_before_successor_handoff(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        runtime = self.successor()
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        capture = mocker.patch.object(process, "capture_executable", return_value=source)
        request = mocker.patch.object(
            apply,
            "request_handoff",
            return_value=runtime,
        )

        result = self.deploy(payload, current, adapter=service, mocker=mocker)

        assert result == {"state": "upgraded", "runtime": runtime}
        assert payload.events == ["commit", "activate", ("finalize", runtime)]
        capture.assert_called_once_with(
            111,
            self.ctx.executable,
            roles={service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE},
        )
        request.assert_called_once_with(
            payload.context,
            payload.expected,
            current=current,
            source_listener=source,
            runtime_reader=mocker.ANY,
            timeout_seconds=30,
        )
        service.uninstall_mock.assert_called_once_with(self.ctx)
        service.install_mock.assert_called_once_with(payload.context)

    def test_finalized_legacy_runtime_uses_one_bounded_native_generation_replacement(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        runtime = self.successor()
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        capture = mocker.patch.object(process, "capture_executable", return_value=source)
        terminate = mocker.patch.object(process, "terminate_owned_process", return_value=True)
        drain = mocker.patch.object(apply.handoff, "drain_responses")
        wait = mocker.patch.object(apply, "wait_for_serving_runtime", return_value=runtime)
        request = mocker.patch.object(apply, "request_handoff")

        result = self.deploy(payload, current, adapter=service, mocker=mocker)

        assert result == {"state": "upgraded", "runtime": runtime}
        assert payload.events == ["commit", "activate", ("finalize", runtime)]
        capture.assert_called_once_with(
            111,
            self.ctx.executable,
            roles={service_runtime.LISTENER_MODE, service_runtime.HANDOFF_CHILD_MODE},
        )
        terminate.assert_called_once_with(source, timeout_seconds=30)
        drain.assert_called_once_with(
            payload.context,
            source_listener=source,
            runtime_reader=mocker.ANY,
            timeout_seconds=30,
        )
        wait.assert_called_once_with(
            payload.context,
            payload.expected,
            runtime_reader=mocker.ANY,
            timeout_seconds=30,
            old_pid=111,
        )
        request.assert_not_called()
        service.install_mock.assert_called_once_with(payload.context)

    def test_failed_native_replacement_waits_for_a_new_predecessor_runtime(self, *, mocker) -> None:
        """A dead drained PID is never reused as rollback admission authority."""
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        restored = {**current, "pid": 333}
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=source)
        mocker.patch.object(process, "terminate_owned_process", return_value=True)
        mocker.patch.object(process, "owned_process_alive", side_effect=[True, False])
        mocker.patch.object(apply.handoff, "drain_responses")
        wait = mocker.patch.object(
            apply,
            "wait_for_serving_runtime",
            side_effect=[errors.InstallError("successor unavailable"), restored],
        )
        resume = mocker.patch.object(apply.handoff, "resume_responses")

        with pytest.raises(errors.InstallError, match="successor unavailable"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == ["commit", "activate", "rollback"]
        assert service.install_mock.call_args_list == [
            mocker.call(payload.context),
            mocker.call(self.ctx),
        ]
        assert wait.call_args_list == [
            mocker.call(
                payload.context,
                payload.expected,
                runtime_reader=mocker.ANY,
                timeout_seconds=30,
                old_pid=111,
            ),
            mocker.call(
                self.ctx,
                current,
                runtime_reader=mocker.ANY,
                timeout_seconds=30,
                old_pid=111,
            ),
        ]
        resume.assert_not_called()

    def test_published_predecessor_without_selected_generation_handoff_uses_replacement(
        self, *, mocker
    ) -> None:
        """Do not ask an older listener to launch a payload outside its own root."""
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(handoff_capabilities=["repeatable"])
        runtime = self.successor()
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=source)
        terminate = mocker.patch.object(process, "terminate_owned_process", return_value=True)
        drain = mocker.patch.object(apply.handoff, "drain_responses")
        wait = mocker.patch.object(apply, "wait_for_serving_runtime", return_value=runtime)
        request = mocker.patch.object(apply, "request_handoff")

        result = self.deploy(payload, current, adapter=service, mocker=mocker)

        assert result == {"state": "upgraded", "runtime": runtime}
        drain.assert_called_once_with(
            payload.context,
            source_listener=source,
            runtime_reader=mocker.ANY,
            timeout_seconds=30,
        )
        terminate.assert_called_once_with(source, timeout_seconds=30)
        wait.assert_called_once_with(
            payload.context,
            payload.expected,
            runtime_reader=mocker.ANY,
            timeout_seconds=30,
            old_pid=111,
        )
        request.assert_not_called()

    def test_candidate_generation_is_materialized_before_the_predecessor_exits(
        self, *, mocker
    ) -> None:
        """Keep the old payload immutable while preparing its exact successor."""
        events: list[object] = []
        payload = FakeTransaction(self.ctx, events=events)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        service = OrderedServiceAdapter(events, mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=source)

        def terminate(*_args, **_kwargs):
            events.append("source-exit")
            return True

        mocker.patch.object(
            apply.handoff,
            "drain_responses",
            side_effect=lambda *_args, **_kwargs: events.append("source-drained"),
        )
        mocker.patch.object(process, "terminate_owned_process", side_effect=terminate)
        mocker.patch.object(
            apply,
            "wait_for_serving_runtime",
            side_effect=lambda *_args, **_kwargs: (
                events.append("successor-serving") or self.successor()
            ),
        )

        self.deploy(payload, current, adapter=service, mocker=mocker)

        assert events == [
            "commit",
            "source-drained",
            "service-uninstall",
            "service-install",
            "activate",
            "source-exit",
            "successor-serving",
            ("finalize", self.successor()),
        ]

    def test_generation_replacement_requires_exact_source_identity_before_write(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        service = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=None)

        with pytest.raises(errors.InstallError, match="process generation"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == []
        service.install_mock.assert_not_called()

    def test_generation_replacement_preserves_an_unconfirmed_source_exit(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=source)
        mocker.patch.object(process, "terminate_owned_process", return_value=False)
        mocker.patch.object(apply.handoff, "drain_responses")

        with pytest.raises(apply.UnknownDeploymentOutcome, match="generation replacement"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            "activate",
            ("preserve", "native generation replacement outcome is unconfirmed"),
        ]

    def test_generation_replacement_restores_predecessor_when_successor_never_serves(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime(
            handoff_capabilities=["repeatable"],
            handoff_state="finalized",
            handoff_transaction_id="txn-previous",
        )
        service = FakeServiceAdapter(mocker=mocker)
        source = process.OwnedProcess(111, self.ctx.executable, 1.0)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(process, "capture_executable", return_value=source)
        mocker.patch.object(process, "terminate_owned_process", return_value=True)
        mocker.patch.object(apply.handoff, "drain_responses")
        mocker.patch.object(
            apply,
            "wait_for_serving_runtime",
            side_effect=errors.InstallError("successor unavailable"),
        )
        mocker.patch.object(
            apply.handoff,
            "resume_responses",
            return_value=False,
        )

        with pytest.raises(
            apply.UnknownDeploymentOutcome,
            match="could not restore predecessor admission",
        ):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            "activate",
            (
                "preserve",
                "native supervisor rollback could not restore predecessor admission",
            ),
        ]
        assert service.uninstall_mock.call_args_list == [
            mocker.call(self.ctx),
            mocker.call(payload.context),
        ]
        assert service.install_mock.call_args_list == [
            mocker.call(payload.context),
            mocker.call(self.ctx),
        ]

    def test_candidate_processes_exit_before_payload_rollback(self, *, mocker) -> None:
        events: list[object] = []
        payload = FakeTransaction(self.ctx, events=events)
        current = self.current_runtime()
        service = OrderedServiceAdapter(events, mocker=mocker)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=errors.InstallError("successor unavailable"),
        )
        mocker.patch.object(apply.handoff, "resume_responses", return_value=True)

        def terminate(ctx, *, timeout_seconds):
            del timeout_seconds
            events.extend((("candidate-exit", 222), ("candidate-exit", 333)))
            service.running_contexts.discard(ctx.executable)
            return 2

        service.terminate_runtime = mocker.Mock(side_effect=terminate)

        with pytest.raises(errors.InstallError, match="successor unavailable"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert events == [
            "commit",
            "service-uninstall",
            "service-install",
            "activate",
            "service-uninstall",
            ("candidate-exit", 222),
            ("candidate-exit", 333),
            "service-install",
            "rollback",
        ]

    def test_current_upgrade_accepts_an_equivalent_supervisor_path(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        runtime = self.successor()
        service = FakeServiceAdapter(mocker=mocker)
        executable = Path(self.ctx.executable)
        candidate_executable = Path(payload.context.executable)
        service.configured_executable = mocker.Mock(
            side_effect=[
                str(executable.parent / ".." / executable.parent.name / executable.name),
                str(
                    candidate_executable.parent
                    / ".."
                    / candidate_executable.parent.name
                    / candidate_executable.name
                ),
            ]
        )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        request = mocker.patch.object(apply, "request_handoff", return_value=runtime)

        assert self.deploy(payload, current, adapter=service, mocker=mocker) == {
            "state": "upgraded",
            "runtime": runtime,
        }
        request.assert_called_once()

    def test_current_upgrade_refuses_an_unproved_supervisor_rebind(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.configured_executable = mocker.Mock(
            side_effect=[self.ctx.executable, None, self.ctx.executable]
        )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        request = mocker.patch.object(apply, "request_handoff")

        with pytest.raises(errors.InstallError, match="did not bind"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == ["commit", "rollback"]
        assert service.install_mock.call_args_list == [
            mocker.call(payload.context),
            mocker.call(self.ctx),
        ]
        request.assert_not_called()

    def test_supervisor_install_failure_restores_the_predecessor(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.install_mock.side_effect = [errors.InstallError("service failed"), None]
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        with pytest.raises(errors.InstallError, match="service failed"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == ["commit", "rollback"]
        assert service.uninstall_mock.call_args_list == [
            mocker.call(self.ctx),
            mocker.call(payload.context),
        ]
        assert service.install_mock.call_args_list == [
            mocker.call(payload.context),
            mocker.call(self.ctx),
        ]

    def test_unproved_supervisor_removal_restores_the_predecessor(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)

        def fail_after_removal(ctx) -> None:
            del ctx
            service.configured = None
            raise errors.InstallError("service removal is unproved")

        service.uninstall_mock.side_effect = fail_after_removal
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        with pytest.raises(errors.InstallError, match="removal is unproved"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == ["commit", "rollback"]
        service.install_mock.assert_called_once_with(self.ctx)

    def test_unrestorable_supervisor_removal_preserves_recovery_state(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.uninstall_mock.side_effect = errors.InstallError("service removal is unproved")
        service.install_mock.side_effect = errors.InstallError("predecessor failed")
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        with pytest.raises(apply.UnknownDeploymentOutcome, match="could not restore"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            (
                "preserve",
                "native supervisor removal could not restore the predecessor",
            ),
        ]

    def test_unrestorable_supervisor_replacement_preserves_recovery_state(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.install_mock.side_effect = [
            errors.InstallError("candidate failed"),
            errors.InstallError("predecessor failed"),
        ]
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        with pytest.raises(apply.UnknownDeploymentOutcome, match="could not restore"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            (
                "preserve",
                "native supervisor replacement could not restore the predecessor",
            ),
        ]

    def test_unproved_predecessor_binding_preserves_recovery_state(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.install_mock.side_effect = [
            errors.InstallError("candidate failed"),
            None,
        ]
        service.configured_executable = mocker.Mock(
            side_effect=[self.ctx.executable, "/other/predecessor"]
        )
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        with pytest.raises(apply.UnknownDeploymentOutcome, match="could not restore"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            (
                "preserve",
                "native supervisor replacement could not restore the predecessor",
            ),
        ]

    def test_upgrade_requires_the_canonical_supervisor_before_payload_mutation(
        self, *, mocker
    ) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(configured="/retired/launcher", mocker=mocker)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        request = mocker.patch.object(apply, "request_handoff")

        with pytest.raises(errors.InstallError, match="canonical executable"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == []
        service.install_mock.assert_not_called()
        request.assert_not_called()

    def test_incompatible_or_unverified_runtime_refuses_before_write(
        self, subtests, *, mocker
    ) -> None:
        for current, listeners, message in (
            (cast("dict[str, object]", {"pid": 111}), [111], "incompatible"),
            (
                self.current_runtime(
                    handoff_state="finalized",
                    handoff_transaction_id="txn-previous",
                    serving_payload_sha256=None,
                ),
                [111],
                "incompatible",
            ),
            (self.current_runtime(), [], "identity"),
            (self.current_runtime(pid=True), [True], "identity"),
        ):
            with subtests.test(message=message):
                payload = FakeTransaction(self.ctx)
                mocker.patch.object(process, "listener_pids", return_value=listeners)
                with pytest.raises(errors.InstallError, match=message):
                    self.deploy(payload, current, mocker=mocker)
                assert payload.events == []

    def test_unidentified_listener_refuses_fresh_install_before_write(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        mocker.patch.object(process, "listener_pids", return_value=[111])

        with pytest.raises(errors.InstallError, match="identity"):
            self.deploy(payload, None, mocker=mocker)

        assert payload.events == []

    def test_fresh_failure_rolls_back(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        service = FakeServiceAdapter(failure=errors.InstallError("service failed"), mocker=mocker)
        mocker.patch.object(process, "listener_pids", return_value=[])
        with pytest.raises(errors.InstallError, match="service failed"):
            self.deploy(payload, None, adapter=service, mocker=mocker)
        assert payload.events == ["commit", "rollback"]

    def test_fresh_failure_preserves_unconfirmed_candidate_cleanup(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        service = FakeServiceAdapter(failure=errors.InstallError("service failed"), mocker=mocker)
        service.uninstall_mock.side_effect = errors.InstallError("cleanup failed")
        mocker.patch.object(process, "listener_pids", return_value=[])

        with pytest.raises(apply.UnknownDeploymentOutcome, match="cleanup is unconfirmed"):
            self.deploy(payload, None, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            (
                "preserve",
                "candidate runtime cleanup is unconfirmed; transaction preserved for recovery",
            ),
        ]

    def test_upgrade_failure_rolls_back_or_preserves_unknown_outcome(self, *, mocker) -> None:
        current = self.current_runtime()
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        rolled_back = FakeTransaction(self.ctx)
        rollback_service = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(
            apply, "request_handoff", side_effect=errors.InstallError("handoff failed")
        )
        resume = mocker.patch.object(apply.handoff, "resume_responses")
        with pytest.raises(errors.InstallError, match="handoff failed"):
            self.deploy(rolled_back, current, adapter=rollback_service, mocker=mocker)
        assert rolled_back.events == ["commit", "activate", "rollback"]
        resume.assert_called_once_with(
            self.ctx,
            source_listener=process.OwnedProcess(111, self.ctx.executable, 1.0),
        )
        assert rollback_service.install_mock.call_args_list == [
            mocker.call(rolled_back.context),
            mocker.call(self.ctx),
        ]

        unknown = FakeTransaction(self.ctx)
        preserved_service = FakeServiceAdapter(mocker=mocker)
        resume.reset_mock()
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=apply.UnknownDeploymentOutcome("outcome unknown"),
        )
        with pytest.raises(apply.UnknownDeploymentOutcome, match="outcome unknown"):
            self.deploy(unknown, current, adapter=preserved_service, mocker=mocker)
        assert unknown.events == ["commit", "activate", ("preserve", "outcome unknown")]
        resume.assert_not_called()
        preserved_service.install_mock.assert_called_once_with(unknown.context)

    def test_upgrade_preserves_unconfirmed_candidate_cleanup(self, *, mocker) -> None:
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        service.uninstall_mock.side_effect = [
            None,
            errors.InstallError("cleanup failed"),
        ]
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=errors.InstallError("successor unavailable"),
        )

        with pytest.raises(apply.UnknownDeploymentOutcome, match="could not restore"):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            "activate",
            (
                "preserve",
                "native supervisor rollback could not restore the predecessor",
            ),
        ]

    def test_upgrade_preserves_a_predecessor_that_cannot_reopen_admission(self, *, mocker) -> None:
        """A restored supervisor is not a successful rollback until admission reopens."""
        payload = FakeTransaction(self.ctx)
        current = self.current_runtime()
        service = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=errors.InstallError("successor unavailable"),
        )
        mocker.patch.object(
            apply.handoff,
            "resume_responses",
            side_effect=errors.InstallError("drain release is unavailable"),
        )

        with pytest.raises(
            apply.UnknownDeploymentOutcome,
            match="could not restore predecessor admission",
        ):
            self.deploy(payload, current, adapter=service, mocker=mocker)

        assert payload.events == [
            "commit",
            "activate",
            (
                "preserve",
                "native supervisor rollback could not restore predecessor admission",
            ),
        ]

    def test_explicit_rollback_reuses_upgrade_and_projects_precise_releases(
        self, *, mocker
    ) -> None:
        retained = payload_rollback.RetainedRollback(
            root=Path("/retained/1.2.2"),
            predecessor=retained_identity("1.2.2"),
            successor=retained_identity("1.2.3"),
        )
        payload = FakeTransaction(self.ctx)
        mocker.patch.object(transaction, "begin_rollback_transaction", return_value=payload)
        install = mocker.patch.object(
            apply,
            "install",
            return_value={"state": "upgraded", "runtime": {"pid": 654}},
        )
        service = FakeServiceAdapter(mocker=mocker)

        def runtime_reader(_ctx):
            return None

        result = apply.rollback(
            self.ctx,
            retained,
            adapter=service,
            runtime_reader=runtime_reader,
            timeout_seconds=12.5,
        )

        assert result == {
            "state": "rolled_back",
            "from_release": "1.2.3",
            "to_release": "1.2.2",
            "runtime": {"pid": 654},
        }
        install.assert_called_once_with(
            self.ctx,
            payload,
            adapter=service,
            runtime_reader=runtime_reader,
            timeout_seconds=12.5,
        )

    def test_explicit_rollback_requires_an_upgrade_result(self, *, mocker) -> None:
        retained = payload_rollback.RetainedRollback(
            root=Path("/retained/1.2.2"),
            predecessor=retained_identity("1.2.2"),
            successor=retained_identity("1.2.3"),
        )
        mocker.patch.object(
            transaction,
            "begin_rollback_transaction",
            return_value=FakeTransaction(self.ctx),
        )
        mocker.patch.object(
            apply,
            "install",
            return_value={"state": "installed", "runtime": {"pid": 654}},
        )

        with pytest.raises(errors.InstallError, match="verified running successor"):
            apply.rollback(
                self.ctx,
                retained,
                adapter=FakeServiceAdapter(mocker=mocker),
                runtime_reader=lambda _ctx: None,
            )

    def test_request_handoff_resolves_finalized_rolled_back_and_unknown(
        self, subtests, *, mocker
    ) -> None:
        current = self.current_runtime()
        expected = FakeTransaction(self.ctx).expected
        successor = self.successor()
        source_listener = process.OwnedProcess(111, self.ctx.executable, 1.0)
        for response, resolution, expected_result in (
            ({"runtime": successor}, None, successor),
            ({"runtime": None}, ("finalized", successor), successor),
        ):
            with subtests.test(resolution=resolution):
                mocker.patch.object(apply.handoff, "request", return_value=response)
                mocker.patch.object(
                    apply.handoff,
                    "resolve_after_controller_failure",
                    return_value=resolution,
                )
                assert (
                    apply.request_handoff(
                        self.ctx,
                        expected,
                        current=current,
                        source_listener=source_listener,
                        runtime_reader=lambda _ctx: current,
                        timeout_seconds=1,
                    )
                    == expected_result
                )

        original = errors.InstallError("handoff failed")
        mocker.patch.object(apply.handoff, "request", side_effect=original)
        mocker.patch.object(
            apply.handoff,
            "resolve_after_controller_failure",
            return_value=("rolled_back", current),
        )
        with pytest.raises(errors.InstallError, match="handoff failed"):
            apply.request_handoff(
                self.ctx,
                expected,
                current=current,
                source_listener=source_listener,
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

        mocker.patch.object(
            apply.handoff,
            "resolve_after_controller_failure",
            return_value=("unknown", None),
        )
        with pytest.raises(apply.UnknownDeploymentOutcome):
            apply.request_handoff(
                self.ctx,
                expected,
                current=current,
                source_listener=source_listener,
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

    def test_wait_for_serving_runtime_requires_exact_identity(self, *, mocker) -> None:
        expected = FakeTransaction(self.ctx).expected
        match = self.successor()
        snapshots = [None, {**match, "pid": True}, {**match, "release": "wrong"}, match]
        mocker.patch.object(process, "verified_proxy_listener_pids", side_effect=[[], [222]])
        mocker.patch.object(apply.time, "monotonic", side_effect=map(float, range(6)))
        mocker.patch.object(apply.time, "sleep")
        assert (
            apply.wait_for_serving_runtime(
                self.ctx,
                expected,
                runtime_reader=lambda _ctx: snapshots.pop(0),
                timeout_seconds=10,
            )
            == match
        )

        mocker.patch.object(apply.time, "monotonic", side_effect=[0.0, 0.1, 0.2])
        with pytest.raises(errors.InstallError, match="SERVING identity"):
            apply.wait_for_serving_runtime(
                self.ctx,
                expected,
                runtime_reader=lambda _ctx: None,
                timeout_seconds=0.15,
            )

    def test_read_runtime_accepts_only_http_200_json_objects(self, *, mocker) -> None:
        class Response:
            def __init__(self, status: int, payload: bytes) -> None:
                self.status, self.payload = status, payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        open_request = mocker.patch.object(
            control.loopback,
            "open_request",
            return_value=Response(200, b'{"pid": 222}'),
        )
        assert control.read_runtime(self.ctx) == {"pid": 222}
        for response in (
            Response(204, b""),
            Response(200, b"[]"),
            Response(200, b"bad"),
        ):
            open_request.return_value = response
            assert control.read_runtime(self.ctx) is None
        open_request.side_effect = urllib.error.URLError("offline")
        assert control.read_runtime(self.ctx) is None


def test_install_has_no_json_publication_proof_loader() -> None:
    assert not hasattr(install, "publication_proof_from_file")


def test_install_admission_failure_closes_the_prepared_transaction(
    tmp_path: Path, *, mocker
) -> None:
    ctx = install_context(tmp_path)
    payload = mocker.Mock()
    payload.rollback_if_prepared.return_value = True
    mocker.patch.object(install, "build_context", return_value=ctx)
    mocker.patch.object(install.artifact, "admit", return_value="released")
    mocker.patch.object(install.transaction, "begin_transaction", return_value=payload)
    mocker.patch.object(
        install.apply,
        "install",
        side_effect=errors.InstallError("installed runtime identity is not verified"),
    )

    with pytest.raises(errors.InstallError, match="identity is not verified"):
        install.install_asset(
            tmp_path / "release.tar.gz",
            trust_anchor=tmp_path / "allowed-signers",
        )

    payload.rollback_if_prepared.assert_called_once_with()
