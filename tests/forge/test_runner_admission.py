"""Contracts for pre-push hosted runner admission."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools" / "forge" / "runner_admission.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("runner_admission", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gitlab_requires_an_online_unpaused_eligible_runner() -> None:
    admission = _load()
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


def test_github_requires_actions_and_both_active_workflows() -> None:
    admission = _load()
    workflows = [
        {"path": ".github/workflows/verify.yml", "state": "active"},
        {"path": ".github/workflows/release.yml", "state": "active"},
    ]
    assert admission.github_ready(workflows, {"enabled": True})
    assert not admission.github_ready(workflows, {"enabled": False})
    assert not admission.github_ready(workflows[:1], {"enabled": True})
    assert not admission.github_ready(
        [{**workflows[0], "state": "disabled_manually"}, workflows[1]], {"enabled": True}
    )


def test_gitlab_encodes_namespaced_project_coordinates(monkeypatch) -> None:
    admission = _load()
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
