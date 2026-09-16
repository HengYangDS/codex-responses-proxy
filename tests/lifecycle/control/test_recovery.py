"""Installed lifecycle recovery contracts."""

from __future__ import annotations

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import control
from codex_responses_proxy.lifecycle import generation
from tests.lifecycle.fixtures import install_context


def test_recovery_rebinds_supervision_to_the_control_generation(
    *, mocker, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = install_context(tmp_path_factory.mktemp("case"))
    control_generation = generation.context(ctx, "a" * 32)
    service = mocker.Mock()
    service.configured_executable.return_value = control_generation.executable
    mocker.patch.object(control.payload_state, "status", return_value={"state": "activated"})
    mocker.patch.object(control, "read_runtime", return_value={"pid": 7})
    recover = mocker.patch.object(control.transaction, "recover")
    mocker.patch.object(control, "adapter", return_value=service)

    def recover_and_bind(_ctx, *, runtime, bind_terminal):
        assert runtime == {"pid": 7}
        bind_terminal(control_generation)
        return {"state": "finalized", "version": "3.1.3"}

    recover.side_effect = recover_and_bind

    assert control.recover(ctx) == {"state": "finalized", "version": "3.1.3"}

    recover.assert_called_once()
    assert recover.call_args.kwargs["runtime"] == {"pid": 7}
    service.install.assert_called_once_with(control_generation)
    service.configured_executable.assert_called_once_with(control_generation)


def test_recovery_rejects_an_unproved_terminal_supervisor(
    *, mocker, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = install_context(tmp_path_factory.mktemp("case"))
    control_generation = generation.context(ctx, "a" * 32)
    service = mocker.Mock()
    service.configured_executable.return_value = None
    mocker.patch.object(control.payload_state, "status", return_value={"state": "activated"})
    mocker.patch.object(control, "read_runtime", return_value={"pid": 7})
    recover = mocker.patch.object(control.transaction, "recover")
    mocker.patch.object(control, "adapter", return_value=service)

    def recover_and_bind(_ctx, *, runtime, bind_terminal):
        assert runtime == {"pid": 7}
        bind_terminal(control_generation)

    recover.side_effect = recover_and_bind

    with pytest.raises(errors.RecoveryStateError, match="supervisor identity"):
        control.recover(ctx)


def test_recovery_no_op_does_not_touch_native_supervision(
    *, mocker, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ctx = install_context(tmp_path_factory.mktemp("case"))
    mocker.patch.object(control.payload_state, "status", return_value=None)
    mocker.patch.object(control, "read_runtime", return_value=None)
    recover = mocker.patch.object(
        control.transaction,
        "recover",
        return_value={"state": "not_required"},
    )
    native = mocker.patch.object(control, "adapter")

    assert control.recover(ctx) == {"state": "not_required"}

    recover.assert_called_once()
    native.assert_not_called()
