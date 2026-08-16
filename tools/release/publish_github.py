"""Publish one immutable GitHub-native release asset set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App

from tools.forge import tag_signature
from tools.release import assemble_assets, signing
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


def select_release(
    releases: Sequence[Mapping[str, object]], tag: str
) -> Mapping[str, object] | None:
    """Return the exact immutable release record, or ``None`` before creation."""

    matches = [release for release in releases if release.get("tag_name") == tag]
    if not matches:
        return None
    if len(matches) != 1:
        raise GitHubPublishError("duplicate GitHub release records for exact tag")
    release = matches[0]
    if not all(
        (
            isinstance(release.get("id"), int) and not isinstance(release.get("id"), bool),
            release.get("name") == f"Codex Responses Proxy {tag}",
            release.get("draft") is False,
            release.get("prerelease") is False,
            isinstance(release.get("published_at"), str) and bool(release.get("published_at")),
        )
    ):
        raise GitHubPublishError("existing GitHub release does not match exact release identity")
    return release


def verify_remote_tag(
    *,
    ref: Mapping[str, object],
    tag_object: Mapping[str, object],
    tag: str,
    tag_oid: str,
    commit_oid: str,
) -> None:
    """Bind GitHub's annotated tag API identity to local immutable Git objects."""

    reference = ref.get("object")
    target = tag_object.get("object")
    if (
        ref.get("ref") != f"refs/tags/{tag}"
        or not isinstance(reference, Mapping)
        or (reference.get("type"), reference.get("sha")) != ("tag", tag_oid)
        or tag_object.get("tag") != tag
        or tag_object.get("sha") != tag_oid
        or not isinstance(target, Mapping)
        or (target.get("type"), target.get("sha")) != ("commit", commit_oid)
    ):
        raise GitHubPublishError("GitHub release tag does not match local immutable objects")


def publish(
    *,
    repository: str,
    tag: str,
    commit_oid: str,
    run_id: int,
    checkout: Path,
    tag_trust: str,
    asset_trust: str,
    workspace: Path,
) -> str:
    """Verify source, publish one exact release, and prove downloaded byte parity."""

    if (
        not repository
        or _TAG.fullmatch(tag) is None
        or len(commit_oid) not in {40, 64}
        or run_id < 1
        or not checkout.is_dir()
        or not tag_trust.strip()
        or not asset_trust.strip()
        or (workspace.exists() and (workspace.is_symlink() or any(workspace.iterdir())))
    ):
        raise GitHubPublishError("GitHub publication inputs are invalid")
    workspace.mkdir(parents=True, exist_ok=True)
    tag_oid, checked_commit = prepare_checkout(checkout, tag, commit_oid)
    _verify_source(checkout, tag, tag_trust)
    _verify_remote_identity(repository, tag, tag_oid, checked_commit)
    existing = select_release(_release_records(repository), tag)
    source = _download_run_assets(repository, run_id, workspace / "release-assets")
    source_digests = _verify_assets(source, asset_trust)
    state = "matched"
    if existing is None:
        _create_release(repository, tag, source)
        state = "created"
    downloaded = _download_release_assets(repository, tag, workspace / "downloaded-assets")
    downloaded_digests = _verify_assets(downloaded, asset_trust)
    if downloaded_digests != source_digests or _file_bytes(downloaded) != _file_bytes(source):
        raise GitHubPublishError("GitHub release assets differ after publication")
    return state


def prepare_checkout(checkout: Path, tag: str, commit_oid: str) -> tuple[str, str]:
    """Fetch, validate, and detach one exact annotated release tag."""

    git = hosted.executable("git", GitHubPublishError)
    _run(
        (
            git,
            "-C",
            str(checkout),
            "fetch",
            "--force",
            "--no-tags",
            "origin",
            f"+refs/tags/{tag}:refs/tags/{tag}",
        ),
        "GitHub release tag is unavailable",
    )
    if _output((git, "-C", str(checkout), "cat-file", "-t", f"refs/tags/{tag}")) != "tag":
        raise GitHubPublishError("GitHub release tag is not annotated")
    tag_oid = _output((git, "-C", str(checkout), "rev-parse", f"refs/tags/{tag}^{{tag}}"))
    target = _output((git, "-C", str(checkout), "rev-parse", f"refs/tags/{tag}^{{commit}}"))
    if target != commit_oid:
        raise GitHubPublishError("GitHub release tag differs from the verified commit")
    _run(
        (git, "-C", str(checkout), "checkout", "--detach", target),
        "GitHub release checkout failed",
    )
    return tag_oid, target


def _verify_source(checkout: Path, tag: str, trust: str) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-responses-proxy-github-tag-trust-") as name:
        anchor = Path(name) / "allowed-signers"
        anchor.write_text(trust.rstrip("\n") + "\n", encoding="utf-8")
        try:
            tag_signature.verify(checkout, tag, "github", anchor)
        except tag_signature.TagSignatureError as error:
            raise GitHubPublishError("GitHub release tag signature is invalid") from error
    # Keep the active repository environment; resolving a venv executable
    # escapes it to the system interpreter on hosted runners.
    python = Path(sys.executable)
    _run(
        (
            str(python),
            str(checkout / "tools/release/metadata.py"),
            "--provider",
            "github",
            "--tag",
            tag,
        ),
        "GitHub release metadata is invalid",
        cwd=checkout,
    )


def _verify_remote_identity(repository: str, tag: str, tag_oid: str, commit_oid: str) -> None:
    gh = hosted.executable("gh", GitHubPublishError)
    ref = _api_mapping((gh, "api", f"repos/{repository}/git/ref/tags/{tag}"))
    tag_object = _api_mapping((gh, "api", f"repos/{repository}/git/tags/{tag_oid}"))
    verify_remote_tag(
        ref=ref,
        tag_object=tag_object,
        tag=tag,
        tag_oid=tag_oid,
        commit_oid=commit_oid,
    )


def _release_records(repository: str) -> list[Mapping[str, object]]:
    gh = hosted.executable("gh", GitHubPublishError)
    value = hosted.api_json(
        (gh, "api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100"),
        unavailable="GitHub release records are unavailable",
        error_type=GitHubPublishError,
    )
    if not isinstance(value, list):
        raise GitHubPublishError("GitHub release records are malformed")
    releases: list[Mapping[str, object]] = []
    for page in value:
        if not isinstance(page, list) or any(not isinstance(item, Mapping) for item in page):
            raise GitHubPublishError("GitHub release records are malformed")
        releases.extend(page)
    return releases


def _download_run_assets(repository: str, run_id: int, target: Path) -> Path:
    gh = hosted.executable("gh", GitHubPublishError)
    _run(
        (
            gh,
            "run",
            "download",
            str(run_id),
            "--repo",
            repository,
            "--name",
            "release-assets",
            "--dir",
            str(target),
        ),
        "GitHub Verify release assets are unavailable",
    )
    return target


def _verify_assets(root: Path, trust: str) -> dict[str, str]:
    try:
        signing.verify(assets=root, trust=trust)
        return assemble_assets.verify(root)
    except (signing.SignatureError, OSError, ValueError) as error:
        raise GitHubPublishError("GitHub release assets are invalid") from error


def _create_release(repository: str, tag: str, assets: Path) -> None:
    gh = hosted.executable("gh", GitHubPublishError)
    names = sorted(path for path in assets.iterdir() if path.is_file())
    if not names:
        raise GitHubPublishError("GitHub release asset set is empty")
    _run(
        (
            gh,
            "release",
            "create",
            tag,
            "--repo",
            repository,
            "--verify-tag",
            "--title",
            f"Codex Responses Proxy {tag}",
            "--generate-notes",
            *(str(path) for path in names),
        ),
        "GitHub release creation failed",
    )


def _download_release_assets(repository: str, tag: str, target: Path) -> Path:
    gh = hosted.executable("gh", GitHubPublishError)
    target.mkdir(parents=True, exist_ok=False)
    _run(
        (
            gh,
            "release",
            "download",
            tag,
            "--repo",
            repository,
            "--dir",
            str(target),
            "--pattern",
            "codex-responses-proxy-*",
            "--pattern",
            "SHA256SUMS*",
        ),
        "GitHub release assets cannot be downloaded",
    )
    return target


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}


def _api_mapping(command: Sequence[str]) -> Mapping[str, object]:
    value = hosted.api_json(
        command,
        unavailable="GitHub release identity is unavailable",
        error_type=GitHubPublishError,
    )
    if not isinstance(value, Mapping):
        raise GitHubPublishError("GitHub release identity is malformed")
    return value


def _run(command: Sequence[str], unavailable: str, *, cwd: Path | None = None) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitHubPublishError(unavailable) from error


def _output(command: Sequence[str]) -> str:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitHubPublishError("GitHub release Git identity is unavailable") from error


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

    @app.command(name="publish")
    def publish_command(
        *,
        repository: str,
        tag: str,
        commit_oid: str,
        run_id: int,
        checkout: Path = Path.cwd(),
        workspace: Path,
    ) -> None:
        """Publish or verify one exact GitHub release."""

        state = publish(
            repository=repository,
            tag=tag,
            commit_oid=commit_oid,
            run_id=run_id,
            checkout=checkout,
            tag_trust=os.environ.get("CODEX_RESPONSES_PROXY_GITHUB_TAG_TRUST", ""),
            asset_trust=os.environ.get("RELEASE_ASSET_TRUST", ""),
            workspace=workspace,
        )
        print(f"GitHub release {state}: {tag}")

    @app.command(name="prepare-checkout")
    def prepare_checkout_command(*, tag: str, commit_oid: str, checkout: Path = Path.cwd()) -> None:
        """Prepare one exact annotated release checkout."""

        tag_oid, target = prepare_checkout(checkout, tag, commit_oid)
        print(f"GitHub release checkout prepared: {tag_oid} -> {target}")

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
