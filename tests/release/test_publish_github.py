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


def test_release_record_selection_is_exact_and_fail_closed(subtests) -> None:
    matching = {
        "id": 7,
        "tag_name": "v1.2.3",
        "name": "Codex Responses Proxy v1.2.3",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-08-09T00:00:00Z",
    }
    assert publish_github.select_release([matching], "v1.2.3") == matching
    assert publish_github.select_release([], "v1.2.3") is None
    for records in (
        [matching, matching],
        [{**matching, "name": "wrong"}],
        [{**matching, "published_at": None}],
    ):
        with subtests.test(records=records), pytest.raises(publish_github.GitHubPublishError):
            publish_github.select_release(records, "v1.2.3")


def test_remote_annotated_tag_is_bound_to_local_objects() -> None:
    tag_oid, commit_oid = "b" * 40, "a" * 40
    publish_github.verify_remote_tag(
        ref={"ref": "refs/tags/v1.2.3", "object": {"type": "tag", "sha": tag_oid}},
        tag_object={
            "tag": "v1.2.3",
            "sha": tag_oid,
            "object": {"type": "commit", "sha": commit_oid},
        },
        tag="v1.2.3",
        tag_oid=tag_oid,
        commit_oid=commit_oid,
    )
    with pytest.raises(publish_github.GitHubPublishError):
        publish_github.verify_remote_tag(
            ref={"ref": "refs/tags/v1.2.3", "object": {"type": "commit", "sha": tag_oid}},
            tag_object={},
            tag="v1.2.3",
            tag_oid=tag_oid,
            commit_oid=commit_oid,
        )


def test_publish_owns_download_validation_creation_and_byte_parity(tmp_path: Path, mocker) -> None:
    source, downloaded = tmp_path / "source", tmp_path / "downloaded"
    source.mkdir()
    downloaded.mkdir()
    (source / "SHA256SUMS").write_bytes(b"checksums")
    (source / "SHA256SUMS.sig").write_bytes(b"signature")
    (downloaded / "SHA256SUMS").write_bytes(b"checksums")
    (downloaded / "SHA256SUMS.sig").write_bytes(b"signature")
    mocker.patch.object(publish_github, "prepare_checkout", return_value=("b" * 40, "a" * 40))
    mocker.patch.object(publish_github, "_verify_source")
    mocker.patch.object(publish_github, "_verify_remote_identity")
    mocker.patch.object(publish_github, "_release_records", return_value=[])
    mocker.patch.object(publish_github, "_download_run_assets", return_value=source)
    mocker.patch.object(
        publish_github,
        "_verify_assets",
        side_effect=(
            {"SHA256SUMS": "1", "SHA256SUMS.sig": "2"},
            {"SHA256SUMS": "1", "SHA256SUMS.sig": "2"},
        ),
    )
    create = mocker.patch.object(publish_github, "_create_release")
    mocker.patch.object(publish_github, "_download_release_assets", return_value=downloaded)

    assert (
        publish_github.publish(
            repository="team/proxy",
            tag="v1.2.3",
            commit_oid="a" * 40,
            run_id=42,
            checkout=tmp_path,
            tag_trust="tag trust",
            asset_trust="asset trust",
            workspace=tmp_path / "workspace",
        )
        == "created"
    )
    create.assert_called_once()


def test_prepare_checkout_is_the_public_exact_tag_owner(tmp_path: Path, mocker) -> None:
    run = mocker.patch.object(publish_github, "_run")
    output = mocker.patch.object(
        publish_github,
        "_output",
        side_effect=("tag", "b" * 40, "a" * 40),
    )

    assert publish_github.prepare_checkout(tmp_path, "v1.2.3", "a" * 40) == (
        "b" * 40,
        "a" * 40,
    )
    assert run.call_count == 2
    assert output.call_count == 3


def test_release_validation_preserves_the_active_environment(tmp_path: Path, mocker) -> None:
    """Do not resolve a virtual-environment interpreter into the host Python."""

    host_python = tmp_path / "host-python"
    host_python.write_text("", encoding="utf-8")
    environment_python = tmp_path / "environment-python"
    environment_python.symlink_to(host_python)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    mocker.patch.object(publish_github.sys, "executable", str(environment_python))
    mocker.patch.object(publish_github.tag_signature, "verify")
    run = mocker.patch.object(publish_github, "_run")

    publish_github._verify_source(checkout, "v1.2.3", "trust")

    assert run.call_count == 2
    assert all(call.args[0][0] == str(environment_python) for call in run.call_args_list)
