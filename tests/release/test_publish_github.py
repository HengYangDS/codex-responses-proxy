"""GitHub-native release publication contracts."""

from __future__ import annotations

from pathlib import Path

from tools.release import publish_github
import pytest


def _run(*, status: str = "completed", conclusion: str | None = "success") -> dict[str, object]:
    return {
        "id": 42,
        "path": ".github/workflows/verify.yml",
        "event": "push",
        "head_branch": "v1.2.3",
        "head_sha": "a" * 40,
        "status": status,
        "conclusion": conclusion,
    }


def test_exact_verify_run_is_selected_fail_closed(subtests) -> None:
    expected = publish_github.VerifyRun(tag="v1.2.3", commit_oid="a" * 40)
    assert publish_github.select_verify_run([_run()], expected) == 42
    for runs in (
        [],
        [_run(), _run()],
        [_run(conclusion="failure")],
        [{**_run(), "head_sha": "b" * 40}],
    ):
        with subtests.test(runs=runs), pytest.raises(publish_github.GitHubPublishError):
            publish_github.select_verify_run(runs, expected)


def test_wait_for_verify_run_is_bounded_and_writes_one_output(tmp_path: Path, *, mocker) -> None:
    output = tmp_path / "github-output"
    calls = iter(([_run(status="in_progress", conclusion=None)], [_run()]))
    mocker.patch.object(publish_github, "_verify_runs", side_effect=lambda _repo: next(calls))
    sleep = mocker.patch.object(publish_github.time, "sleep")

    assert (
        publish_github.wait_for_verify(
            repository="team/proxy",
            expected=publish_github.VerifyRun(tag="v1.2.3", commit_oid="a" * 40),
            output=output,
            timeout_seconds=30,
            poll_seconds=1,
        )
        == 42
    )
    assert output.read_text(encoding="utf-8") == "run-id=42\n"
    sleep.assert_called_once_with(1)
