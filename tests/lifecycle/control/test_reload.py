"""Installed lifecycle reload contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import generation
from codex_responses_proxy.lifecycle import state as payload_state
from codex_responses_proxy.lifecycle.supervision import process
from tests.lifecycle.fixtures import install_context


def test_control_reads_bounded_runtime_and_recovers_finalized_reload(
    subtests, *, mocker, tmp_path_factory: pytest.TempPathFactory
):
    ctx = install_context(tmp_path_factory.mktemp("case"))
    Path(ctx.install_dir).mkdir(parents=True)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"pid": 7}'

    open_request = mocker.patch.object(
        control.loopback,
        "open_request",
        return_value=Response(),
    )
    assert control.read_runtime(ctx) == {"pid": 7}
    open_request.side_effect = OSError("offline")
    assert control.read_runtime(ctx) is None
    open_request.side_effect = None
    open_request.return_value = Response()
    open_request.return_value.status = 503
    assert control.read_runtime(ctx) is None

    runtime = {"pid": 7}
    expected = {"transaction_id": "tx"}
    mocker.patch.object(control, "read_runtime", return_value=runtime)
    mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
    mocker.patch.object(control.projection, "verify_payload_manifest", return_value=(True, "ok"))
    mocker.patch.object(control.handoff, "expected_metadata", return_value=expected)
    mocker.patch.object(
        control.handoff,
        "capture_source_listener",
        return_value=control.process.OwnedProcess(7, ctx.executable, 1.0),
    )
    mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
    mocker.patch.object(
        control.handoff,
        "resolve_after_controller_failure",
        return_value=("finalized", {"pid": 8}),
    )
    assert control.reload(ctx) == {
        "state": "reloaded",
        "old_pid": 7,
        "new_pid": 8,
        "transaction_id": "tx",
        "recovered_after_controller_failure": True,
    }
    mocker.patch.object(control, "read_runtime", return_value=runtime)
    mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
    mocker.patch.object(
        control.projection,
        "verify_payload_manifest",
        return_value=(False, "tampered"),
    )

    with pytest.raises(errors.InstallError, match="tampered"):
        control.reload(ctx)

    for resolution, expected_error in (
        ("unknown", errors.InstallError),
        ("rolled_back", OSError),
    ):
        mocker.patch.object(control, "read_runtime", return_value=runtime)
        mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
        mocker.patch.object(
            control.projection,
            "verify_payload_manifest",
            return_value=(True, "ok"),
        )
        mocker.patch.object(control.handoff, "expected_metadata", return_value=expected)
        mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
        mocker.patch.object(
            control.handoff,
            "resolve_after_controller_failure",
            return_value=(resolution, None),
        )
        with subtests.test(resolution=resolution), pytest.raises(expected_error):
            control.reload(ctx)


def test_reload_reads_handoff_identity_from_selected_generation(tmp_path, *, mocker):
    stable = install_context(tmp_path)
    Path(stable.install_dir).mkdir(parents=True)
    ctx = generation.context(stable, "a" * 32)
    runtime = {"pid": 7}
    expected = {"transaction_id": "tx"}
    mocker.patch.object(control.payload_state, "read_installed", return_value={})
    mocker.patch.object(control.payload_state, "status", return_value=None)
    mocker.patch.object(control, "read_runtime", return_value=runtime)
    mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
    mocker.patch.object(
        control.projection,
        "verify_payload_manifest",
        return_value=(True, "ok"),
    )
    expected_metadata = mocker.patch.object(
        control.handoff,
        "expected_metadata",
        return_value=expected,
    )
    mocker.patch.object(
        control.handoff,
        "capture_source_listener",
        return_value=control.process.OwnedProcess(7, ctx.executable, 1.0),
    )
    mocker.patch.object(
        control.handoff,
        "request",
        return_value={"old_pid": 7, "child_pid": 8},
    )

    assert control.reload(ctx)["new_pid"] == 8
    expected_metadata.assert_called_once_with(ctx.payload_dir)


def test_status_and_reload_bound_unobservable_failures(
    *, mocker, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = install_context(tmp_path_factory.mktemp("case"))
    Path(ctx.install_dir).mkdir(parents=True)
    current_error = errors.InstallError("current manifest invalid")
    mocker.patch.object(control.projection, "verify_payload_manifest", side_effect=current_error)
    mocker.patch.object(
        control,
        "adapter",
        side_effect=errors.InstallError("service unavailable"),
    )
    mocker.patch.object(control.process, "verified_proxy_listener_pids", return_value=[])
    evidence = control.status(ctx)
    assert evidence["payload_integrity"] == {
        "ok": False,
        "detail": str(current_error),
    }
    assert evidence["service"] == "unknown"

    mocker.patch.object(
        control,
        "adapter",
        side_effect=errors.ProductAssemblyError("product assembly incomplete"),
    )
    with pytest.raises(errors.ProductAssemblyError, match="product assembly incomplete"):
        control.status(ctx)

    mocker.patch.object(control, "read_runtime", return_value={"pid": 7})
    mocker.patch.object(control.handoff, "runtime_supports_handoff", return_value=True)
    mocker.patch.object(control.projection, "verify_payload_manifest", return_value=(True, "ok"))
    mocker.patch.object(control.handoff, "expected_metadata", return_value={"transaction_id": "tx"})
    mocker.patch.object(
        control.handoff,
        "capture_source_listener",
        return_value=control.process.OwnedProcess(7, ctx.executable, 1.0),
    )
    mocker.patch.object(control.handoff, "request", side_effect=OSError("lost response"))
    mocker.patch.object(
        control.handoff,
        "resolve_after_controller_failure",
        side_effect=RuntimeError("resolution unavailable"),
    )
    with pytest.raises(errors.InstallError, match="outcome is unconfirmed"):
        control.reload(ctx)


def test_reload_requires_installation_and_resolved_transaction_state(
    tmp_path: Path, *, mocker, subtests
) -> None:
    ctx = install_context(tmp_path)

    with subtests.test(state="absent"), pytest.raises(errors.NotInstalledError):
        control.reload(ctx)

    Path(ctx.install_dir).mkdir(parents=True)
    for transaction_state, expected in (
        ({"state": "invalid"}, errors.RecoveryStateError),
        ({"state": "prepared"}, errors.RecoveryRequiredError),
    ):
        mocker.patch.object(payload_state, "status", return_value=transaction_state)
        with (
            subtests.test(state=transaction_state["state"]),
            pytest.raises(expected),
        ):
            control.reload(ctx)


def test_reload_refuses_incompatible_listener_without_mutation(
    *, mocker, tmp_path_factory: pytest.TempPathFactory
):
    ctx = install_context(tmp_path_factory.mktemp("case"))
    Path(ctx.install_dir).mkdir(parents=True)
    mocker.patch.object(control, "read_runtime", return_value={"pid": 12345})
    terminate = mocker.patch.object(process, "terminate_pid")
    with pytest.raises(errors.InstallError, match="not healthy enough to reload"):
        control.reload(ctx)
    terminate.assert_not_called()
