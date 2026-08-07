"""Released deployment orchestration contracts."""

from __future__ import annotations

import tempfile
import urllib.error
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import install, transaction
from codex_responses_proxy.lifecycle.deployment import apply
from codex_responses_proxy.lifecycle.supervision import process
from tests.lifecycle.fixtures import install_context


class FakeTransaction:
    """Behavioral double for the payload transaction protocol."""

    def __init__(self) -> None:
        self.expected = {
            "transaction_id": "txn-release",
            "release": "1.2.3",
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


def as_transaction(value: FakeTransaction) -> transaction.PayloadTransaction:
    return cast("transaction.PayloadTransaction", value)


class FakeServiceAdapter:
    def __init__(self, *, failure: BaseException | None = None, mocker) -> None:
        self.install_mock = mocker.Mock(side_effect=failure)

    def install(self, ctx) -> None:
        self.install_mock(ctx)


class TestReleasedDeployment:
    def setup_method(self) -> None:
        self.ctx = install_context(Path(tempfile.mkdtemp()))

    @staticmethod
    def current_runtime(**changes: object) -> dict[str, object]:
        value: dict[str, object] = {
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
        payload = FakeTransaction()
        service = FakeServiceAdapter(mocker=mocker)
        runtime = self.successor(pid=123)
        mocker.patch.object(process, "listener_pids", return_value=[])
        mocker.patch.object(apply, "wait_for_serving_runtime", return_value=runtime)

        result = self.deploy(payload, None, adapter=service, mocker=mocker)

        assert result == {"mode": "fresh-install", "runtime": runtime}
        assert payload.events == ["commit", ("finalize", runtime)]
        service.install_mock.assert_called_once_with(self.ctx)

    def test_current_upgrade_uses_handoff_without_service_replacement(self, *, mocker) -> None:
        payload = FakeTransaction()
        current = self.current_runtime()
        runtime = self.successor()
        service = FakeServiceAdapter(mocker=mocker)
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])
        request = mocker.patch.object(apply, "request_handoff", return_value=runtime)

        result = self.deploy(payload, current, adapter=service, mocker=mocker)

        assert result == {"mode": "upgrade", "runtime": runtime}
        assert payload.events == ["commit", ("finalize", runtime)]
        request.assert_called_once()
        service.install_mock.assert_not_called()

    def test_incompatible_or_unverified_runtime_refuses_before_write(
        self, subtests, *, mocker
    ) -> None:
        for current, listeners, message in (
            (cast("dict[str, object]", {"pid": 111}), [111], "incompatible"),
            (self.current_runtime(), [], "identity"),
            (self.current_runtime(pid=True), [True], "identity"),
        ):
            with subtests.test(message=message):
                payload = FakeTransaction()
                mocker.patch.object(process, "verified_proxy_listener_pids", return_value=listeners)
                with pytest.raises(errors.InstallError, match=message):
                    self.deploy(payload, current, mocker=mocker)
                assert payload.events == []

    def test_fresh_failure_rolls_back(self, *, mocker) -> None:
        payload = FakeTransaction()
        service = FakeServiceAdapter(failure=errors.InstallError("service failed"), mocker=mocker)
        mocker.patch.object(process, "listener_pids", return_value=[])
        with pytest.raises(errors.InstallError, match="service failed"):
            self.deploy(payload, None, adapter=service, mocker=mocker)
        assert payload.events == ["commit", "rollback"]

    def test_upgrade_failure_rolls_back_or_preserves_unknown_outcome(self, *, mocker) -> None:
        current = self.current_runtime()
        mocker.patch.object(process, "verified_proxy_listener_pids", return_value=[111])

        rolled_back = FakeTransaction()
        mocker.patch.object(
            apply, "request_handoff", side_effect=errors.InstallError("handoff failed")
        )
        with pytest.raises(errors.InstallError, match="handoff failed"):
            self.deploy(rolled_back, current, mocker=mocker)
        assert rolled_back.events == ["commit", "rollback"]

        unknown = FakeTransaction()
        mocker.patch.object(
            apply,
            "request_handoff",
            side_effect=apply.UnknownDeploymentOutcome("outcome unknown"),
        )
        with pytest.raises(apply.UnknownDeploymentOutcome, match="outcome unknown"):
            self.deploy(unknown, current, mocker=mocker)
        assert unknown.events == ["commit", ("preserve", "outcome unknown")]

    def test_request_handoff_resolves_finalized_rolled_back_and_unknown(
        self, subtests, *, mocker
    ) -> None:
        current = self.current_runtime()
        expected = FakeTransaction().expected
        successor = self.successor()
        for response, resolution, expected_result in (
            ({"runtime": successor}, None, successor),
            ({"runtime": None}, ("finalized", successor), successor),
        ):
            with subtests.test(resolution=resolution):
                mocker.patch.object(apply.handoff, "request", return_value=response)
                mocker.patch.object(
                    apply.handoff, "resolve_after_controller_failure", return_value=resolution
                )
                assert (
                    apply.request_handoff(
                        self.ctx,
                        expected,
                        current=current,
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
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

        mocker.patch.object(
            apply.handoff, "resolve_after_controller_failure", return_value=("unknown", None)
        )
        with pytest.raises(apply.UnknownDeploymentOutcome):
            apply.request_handoff(
                self.ctx,
                expected,
                current=current,
                runtime_reader=lambda _ctx: current,
                timeout_seconds=1,
            )

    def test_wait_for_serving_runtime_requires_exact_identity(self, *, mocker) -> None:
        expected = FakeTransaction().expected
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

        opener = mocker.Mock()
        mocker.patch.object(apply.urllib.request, "build_opener", return_value=opener)
        opener.open.return_value = Response(200, b'{"pid": 222}')
        assert apply.read_runtime(self.ctx) == {"pid": 222}
        for response in (Response(204, b""), Response(200, b"[]"), Response(200, b"bad")):
            opener.open.return_value = response
            assert apply.read_runtime(self.ctx) is None
        opener.open.side_effect = urllib.error.URLError("offline")
        assert apply.read_runtime(self.ctx) is None


def test_install_has_no_json_publication_proof_loader() -> None:
    assert not hasattr(install, "publication_proof_from_file")
