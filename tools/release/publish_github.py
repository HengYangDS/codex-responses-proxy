"""Publish one immutable GitHub-native release asset set."""

from __future__ import annotations

import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App

from tools.release.publication import hosted
from tools.release.publication.git import _TAG


class GitHubPublishError(RuntimeError):
    """GitHub publication failed or conflicts with immutable identity."""


class _VerifyRunPending(GitHubPublishError):
    """The exact Verify run has not reached a terminal state."""


@dataclass(frozen=True, slots=True)
class VerifyRun:
    """Exact tag and commit identity expected from the Verify workflow."""

    tag: str
    commit_oid: str


def select_verify_run(runs: Sequence[Mapping[str, object]], expected: VerifyRun) -> int:
    """Return one exact successful Verify run id or fail closed."""

    matches = [
        run
        for run in runs
        if run.get("path") == ".github/workflows/verify.yml"
        and run.get("event") == "push"
        and run.get("head_branch") == expected.tag
        and run.get("head_sha") == expected.commit_oid
    ]
    if not matches:
        raise _VerifyRunPending("exact tag Verify run is not available")
    if len(matches) != 1:
        raise GitHubPublishError("exact tag Verify run is ambiguous")
    run = matches[0]
    if run.get("status") != "completed":
        raise _VerifyRunPending("exact tag Verify run is still running")
    if run.get("conclusion") != "success":
        raise GitHubPublishError("exact tag Verify run did not succeed")
    run_id = run.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        raise GitHubPublishError("exact tag Verify run has no stable id")
    return run_id


def wait_for_verify(
    *,
    repository: str,
    expected: VerifyRun,
    output: Path,
    timeout_seconds: float,
    poll_seconds: float,
) -> int:
    """Wait boundedly for one exact successful Verify run and export its id."""

    if (
        not repository
        or _TAG.fullmatch(expected.tag) is None
        or len(expected.commit_oid) not in {40, 64}
        or timeout_seconds <= 0
        or poll_seconds <= 0
    ):
        raise GitHubPublishError("GitHub verification inputs are invalid")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            run_id = select_verify_run(_verify_runs(repository), expected)
        except _VerifyRunPending:
            if time.monotonic() >= deadline:
                raise GitHubPublishError("exact tag Verify run timed out") from None
            time.sleep(poll_seconds)
            continue
        if output.is_symlink() or not output.parent.is_dir():
            raise GitHubPublishError("GitHub output path is unavailable")
        with output.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"run-id={run_id}\n")
        return run_id


def _verify_runs(repository: str) -> list[Mapping[str, object]]:
    """Read every Verify workflow run through the GitHub CLI."""

    gh = hosted.executable("gh", GitHubPublishError)
    value = hosted.api_json(
        (
            gh,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repository}/actions/workflows/verify.yml/runs?per_page=100",
        ),
        unavailable="GitHub Verify workflow runs are unavailable",
        error_type=GitHubPublishError,
    )
    if not isinstance(value, list):
        raise GitHubPublishError("GitHub Verify workflow response is malformed")
    runs: list[Mapping[str, object]] = []
    for page in value:
        if not isinstance(page, Mapping) or not isinstance(page.get("workflow_runs"), list):
            raise GitHubPublishError("GitHub Verify workflow response is malformed")
        for run in page["workflow_runs"]:
            if not isinstance(run, Mapping):
                raise GitHubPublishError("GitHub Verify workflow response is malformed")
            runs.append(run)
    return runs


def _app() -> App:
    app = App(help=__doc__, result_action="return_value")

    @app.command(name="wait-verify")
    def wait_verify_command(
        *,
        repository: str,
        tag: str,
        commit_oid: str,
        output: Path,
        timeout_seconds: float = 2400,
        poll_seconds: float = 10,
    ) -> None:
        """Wait for the exact successful tag verification run."""

        run_id = wait_for_verify(
            repository=repository,
            expected=VerifyRun(tag=tag, commit_oid=commit_oid),
            output=output,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        print(f"GitHub Verify run accepted: {run_id}")

    return app


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run publication through the repository parser stack."""

    try:
        _app()(tuple(sys.argv[1:] if argv is None else argv))
    except (GitHubPublishError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
