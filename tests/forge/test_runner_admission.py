"""Contracts for pre-push hosted runner admission."""

from __future__ import annotations

import json
import subprocess

import pytest

from tools.forge import runner_admission as admission


def test_gitlab_requires_an_online_unpaused_eligible_runner() -> None:
    ready = {
        "active": True,
        "runner_type": "project_type",
        "online": True,
        "paused": False,
        "run_untagged": True,
        "access_level": "not_protected",
        "tag_list": ["linux"],
    }
    assert admission.gitlab_ready([ready])
    for field, value in (
        ("active", False),
        ("runner_type", "group_type"),
        ("online", False),
        ("paused", True),
        ("run_untagged", False),
    ):
        assert not admission.gitlab_ready([{**ready, field: value}])
    assert not admission.gitlab_ready([{**ready, "access_level": "invalid"}])
    assert admission.gitlab_ready([ready], "linux")
    assert not admission.gitlab_ready([ready], "windows")


def test_github_requires_actions_and_the_active_verification_workflow() -> None:
    workflows = [{"path": ".github/workflows/verify.yml", "state": "active"}]
    assert admission.github_ready(workflows, {"enabled": True})
    assert not admission.github_ready(workflows, {"enabled": False})
    assert not admission.github_ready(
        [{**workflows[0], "state": "disabled_manually"}],
        {"enabled": True},
    )


def test_gitlab_encodes_namespaced_project_coordinates(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def command(*args: str) -> object:
        calls.append(args)
        if args[-1].startswith("projects/"):
            return [{"id": 35}]
        return {
            "id": 35,
            "active": True,
            "runner_type": "project_type",
            "online": True,
            "paused": False,
            "run_untagged": False,
            "access_level": "ref_protected",
            "tag_list": ["docker-linux-amd64"],
        }

    monkeypatch.setattr(admission, "_command", command)
    assert admission._gitlab("dig/misc/tools/proxy", "docker-linux-amd64")["ready"] is True
    assert calls[0][-1] == "projects/dig%2Fmisc%2Ftools%2Fproxy/runners?per_page=100"


@pytest.mark.parametrize("output", ["invalid", '{"ready": true}'])
def test_command_requires_parseable_evidence(output, mocker):
    run = mocker.patch.object(
        admission.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            [],
            0,
            stdout=output,
        ),
    )
    if output == "invalid":
        with pytest.raises(admission.AdmissionError, match="unavailable"):
            admission._command("gh", "api")
    else:
        assert admission._command("gh", "api") == {"ready": True}
    assert run.call_count == 1


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.CalledProcessError(1, ["gh"])])
def test_command_translates_transport_failure(failure, mocker):
    mocker.patch.object(admission.subprocess, "run", side_effect=failure)
    with pytest.raises(admission.AdmissionError, match="unavailable"):
        admission._command("gh", "api")


@pytest.mark.parametrize("value", [None, {"workflows": []}])
def test_inventory_requires_a_record_list(value):
    with pytest.raises(admission.AdmissionError, match="malformed"):
        admission._records(value)


@pytest.mark.parametrize("value", [None, {1: "invalid"}])
def test_object_evidence_requires_string_keys(value):
    with pytest.raises(admission.AdmissionError, match="malformed"):
        admission._mapping(value)


@pytest.mark.parametrize("enabled", [False, True])
def test_github_observation_checks_both_workflow_and_permission(enabled, mocker):
    command = mocker.patch.object(
        admission,
        "_command",
        side_effect=[
            {"workflows": [{"path": ".github/workflows/verify.yml", "state": "active"}]},
            {"enabled": enabled},
        ],
    )
    if enabled:
        assert admission._github("team/repo") == {
            "provider": "github",
            "ready": True,
            "workflow_count": 1,
        }
    else:
        with pytest.raises(admission.AdmissionError, match="disabled"):
            admission._github("team/repo")
    assert command.call_count == 2


def test_gitlab_empty_runner_inventory_is_not_ready(mocker):
    mocker.patch.object(admission, "_command", return_value=[])
    with pytest.raises(admission.AdmissionError, match="no online"):
        admission._gitlab("team/repo", None)


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_cli_uses_selected_provider_and_serializes_evidence(provider, mocker, capsys):
    report = {"provider": provider, "ready": True}
    selected = mocker.patch.object(admission, f"_{provider}", return_value=report)
    admission.main(("--provider", provider, "--repository", "team/repo", "--json"))
    assert json.loads(capsys.readouterr().out) == report
    assert selected.call_count == 1
    selected.side_effect = admission.AdmissionError("unavailable")
    with pytest.raises(SystemExit) as stopped:
        admission.main(("--provider", provider, "--repository", "team/repo"))
    assert stopped.value.code == 1
    assert "unavailable" in capsys.readouterr().err
