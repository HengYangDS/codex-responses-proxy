"""Human and machine projections of public command results."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application
from tests.cli.fixtures import invoke
from tests.lifecycle.fixtures import install_context


@pytest.mark.parametrize(
    ("command", "result"),
    [
        ("install", {}),
        ("status", {"state": "running"}),
        ("doctor", {"ok": True}),
        ("reload", {"state": "reloaded"}),
        ("rollback", {"state": "unknown"}),
        ("recover", {"state": "unknown"}),
        ("uninstall", {"state": "unknown"}),
    ],
)
def test_malformed_success_cannot_be_presented_as_completed(
    command: str, result: dict[str, object], *, mocker, capsys
) -> None:
    mocker.patch.object(application, "dispatch", return_value=result)

    code = application._execute(command, as_json=True)
    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "internal_error"


@pytest.mark.parametrize("value", [Path("/private/operator"), float("nan")])
def test_non_json_nested_evidence_is_rejected_before_projection(value: object) -> None:
    with pytest.raises(ValueError, match="finite JSON object"):
        application.outcome.admit(
            "install", {"state": "installed", "release": "4.0.5", "extra": value}
        )


@pytest.mark.parametrize(
    "override",
    [
        {"listener_pids": ["/private/operator"]},
        {"payload_integrity": {"ok": "true", "detail": "verified"}},
        {"command": {"state": 1}},
        {"command": {"state": "owned", "kind": 1, "path": "/bin/proxy"}},
        {"release": 405},
        {"runtime": []},
        {"payload_transaction": []},
    ],
)
def test_status_rejects_mistyped_nested_evidence(
    override: dict[str, object], *, mocker, capsys
) -> None:
    status: dict[str, object] = {
        "state": "running",
        "detail": "healthy",
        "release": "4.0.5",
        "payload_integrity": {"ok": True, "detail": "verified"},
        "command": {"state": "owned", "kind": "symlink", "path": "/bin/proxy"},
        "service": "running",
        "listener_pids": [321],
        "runtime": {"pid": 321},
        "payload_transaction": None,
    }
    status.update(override)

    with pytest.raises(ValueError, match="status result is invalid"):
        application.outcome.admit("status", status)
    mocker.patch.object(application, "dispatch", return_value=status)

    assert application._execute("status") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Action required" in captured.err
    assert "/private/operator" not in captured.err


def test_status_human_output_is_aligned_and_not_serialized_json(*, mocker) -> None:
    evidence = {
        "state": "running",
        "detail": "healthy",
        "release": "2.0.8",
        "payload_integrity": {"ok": True, "detail": "verified"},
        "service": "running",
        "listener_pids": [321],
        "runtime": {"pid": 321, "accepting": True},
        "payload_transaction": None,
        "command": {
            "path": "/commands/codex-responses-proxy",
            "state": "owned",
            "kind": "symlink",
        },
    }
    mocker.patch.object(application.control, "status", return_value=evidence)

    code, stdout, stderr = invoke("status")

    assert code == 0
    assert stderr == ""
    assert "Codex Responses Proxy  Status" in stdout
    assert "Release" in stdout
    assert "2.0.8" in stdout
    assert "Payload" in stdout
    assert "Verified" in stdout
    assert "Service" in stdout
    assert "Running" in stdout
    assert "Listener" in stdout
    assert "PID 321" in stdout
    assert "Command" in stdout
    assert "Owned" in stdout
    assert not stdout.lstrip().startswith("{")
    lines = stdout.splitlines()
    value_columns = {
        line.index(value)
        for line, value in (
            (next(line for line in lines if "2.0.8" in line), "2.0.8"),
            (next(line for line in lines if "Verified" in line), "Verified"),
            (next(line for line in lines if "Running" in line), "Running"),
        )
    }
    assert len(value_columns) == 1


def test_status_human_next_action_follows_the_lifecycle_state() -> None:
    base = {
        "release": "2.0.58",
        "payload_integrity": {"ok": True, "detail": "verified"},
        "service": "running",
        "listener_pids": [321],
        "runtime": {"pid": 321, "accepting": True},
        "command": {"state": "owned", "kind": "symlink"},
    }

    invalid = application.presentation.render(
        "status",
        {
            **base,
            "state": "invalid",
            "payload_transaction": {
                "state": "invalid",
                "detail": "payload transaction journal is missing",
            },
        },
    )
    recoverable = application.presentation.render(
        "status",
        {
            **base,
            "state": "recovery_required",
            "payload_transaction": {"state": "committed"},
        },
    )

    assert "codex-responses-proxy status --json" in invalid
    assert "codex-responses-proxy recover" not in invalid
    assert "codex-responses-proxy recover" in recoverable


def test_human_projection_covers_degraded_and_complete_command_results() -> None:
    degraded = application.presentation.render(
        "status",
        {
            "release": "",
            "payload_integrity": {"ok": False},
            "service": "",
            "listener_pids": [],
        },
    )
    assert "Not installed" in degraded
    assert "Action required" in degraded
    assert "codex-responses-proxy doctor" in degraded

    doctor = application.presentation.render(
        "doctor",
        {
            "next": "codex-responses-proxy reload",
            "checks": {
                "payload": {"status": "passed"},
                "listener": {
                    "status": "failed",
                },
                "ignored": "not a check",
            },
        },
    )
    assert "Payload" in doctor
    assert "Passed" in doctor
    assert "Listener" in doctor
    assert "Action required" in doctor
    assert "codex-responses-proxy reload" in doctor

    installed = application.presentation.render("install", {"runtime": {"release": "2.0.11"}})
    assert "Installed" in installed
    assert "2.0.11" in installed
    upgraded = application.presentation.render(
        "install", {"state": "upgraded", "runtime": {"release": "2.0.12"}}
    )
    assert "Upgraded" in upgraded
    assert "2.0.12" in upgraded
    assert "Reloaded" in application.presentation.render("reload", {"old_pid": 1, "new_pid": 2})
    assert "Rolled Back" in application.presentation.render(
        "recover", {"version": "2.0.11", "state": "rolled_back"}
    )
    assert "Finalized" in application.presentation.render(
        "recover", {"version": "2.0.12", "state": "finalized"}
    )
    assert "No recovery required" in application.presentation.render(
        "recover", {"state": "not_required"}
    )
    closed = application.presentation.render(
        "recover",
        {"transaction_id": "tx-closed", "version": "2.0.12", "state": "closed"},
    )
    assert "Closed" in closed
    assert "Transaction tx-closed" in closed
    assert "Release     2.0.12" in closed
    assert "Not installed" in application.presentation.render(
        "uninstall",
        {
            "state": "not_installed",
            "stopped": 0,
            "command_removed": False,
        },
    )
    assert "Purged" in application.presentation.render(
        "uninstall", {"state": "purged", "stopped": 1, "command_removed": True}
    )
    assert application.presentation.render("future", {}) == ""


def test_status_human_output_exposes_the_classification_detail() -> None:
    rendered = application.presentation.render(
        "status",
        {
            "state": "invalid",
            "detail": "payload transaction journal is missing",
            "release": "2.0.58",
            "payload_integrity": {"ok": True, "detail": "verified"},
            "service": "running",
            "listener_pids": [321],
            "runtime": None,
            "payload_transaction": {
                "state": "invalid",
                "detail": "payload transaction journal is missing",
            },
            "command": {"state": "owned", "kind": "symlink"},
        },
    )

    assert "payload transaction journal is missing" in rendered


def test_rollback_without_a_predecessor_has_matching_human_and_json_semantics(
    tmp_path: Path, *, mocker
) -> None:
    unavailable = {
        "state": "unavailable",
        "detail": "no verified predecessor is retained",
    }
    ctx = install_context(tmp_path)
    mocker.patch.object(application.runtime_context, "create", return_value=ctx)
    mocker.patch.object(application.control, "rollback", return_value=unavailable)

    json_code, json_stdout, json_stderr = invoke("rollback", "--to-release", "3.0.5", "--json")
    human_code, human_stdout, human_stderr = invoke("rollback", "--to-release", "3.0.5")

    assert json_code == human_code == 0
    assert json.loads(json_stdout) == unavailable
    assert "No verified predecessor" in human_stdout
    assert json_stderr == human_stderr == ""


def test_expected_lifecycle_failures_are_rendered_once(*, mocker) -> None:
    mocker.patch.object(
        application.runtime_context,
        "create",
        side_effect=errors.InstallError(
            "bad port",
            next_command="codex-responses-proxy status --help",
        ),
    )
    code, stdout, stderr = invoke("status", "--json")
    assert code == 2
    assert stdout == ""
    assert json.loads(stderr) == {
        "error": {
            "code": "lifecycle_error",
            "message": "bad port",
            "next": "codex-responses-proxy status --help",
        }
    }


def test_invalid_result_and_unknown_dispatch_have_explicit_boundaries() -> None:
    with pytest.raises(ValueError, match="not an object"):
        application.outcome.admit("status", None)

    with pytest.raises(ValueError, match="not implemented"):
        application.dispatch("future", port=8792)
