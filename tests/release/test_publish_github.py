"""GitHub-native release publication contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.release import publish_github


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _release_checkout(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    subprocess.run(("git", "init", "-q", "-b", "dev", str(repository)), check=True)
    _git(repository, "config", "core.hooksPath", "/dev/null")
    _git(repository, "config", "user.name", "Release Test")
    _git(repository, "config", "user.email", "release@example.test")
    (repository / "tracked.txt").write_text("accepted\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-qm", "test: accepted source")
    commit_oid = _git(repository, "rev-parse", "HEAD")
    _git(repository, "tag", "-a", "v1.2.3", "-m", "release v1.2.3")
    (repository / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(repository, "add", "staged.txt")
    (repository / "tracked.txt").write_text("working\n", encoding="utf-8")
    (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    return repository, commit_oid


def _checkout_state(repository: Path) -> tuple[str, ...]:
    return (
        _git(repository, "symbolic-ref", "HEAD"),
        _git(repository, "rev-parse", "HEAD"),
        _git(repository, "status", "--porcelain=v1"),
        _git(repository, "diff", "--cached", "--binary"),
        _git(repository, "diff", "--binary"),
        (repository / "untracked.txt").read_text(encoding="utf-8"),
    )


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
        with (
            subtests.test(records=records),
            pytest.raises(publish_github.GitHubPublishError),
        ):
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
            ref={
                "ref": "refs/tags/v1.2.3",
                "object": {"type": "commit", "sha": tag_oid},
            },
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
    mocker.patch.object(publish_github, "_local_tag_identity", return_value=("b" * 40, "a" * 40))
    mocker.patch.object(publish_github, "_verify_source")
    mocker.patch.object(publish_github, "_verify_remote_identity")
    mocker.patch.object(publish_github, "_release_records", return_value=[])
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
            checkout=tmp_path,
            tag_trust="tag trust",
            asset_trust="asset trust",
            source=source,
            workspace=tmp_path / "workspace",
        )
        == "created"
    )
    create.assert_called_once()
    assert not hasattr(publish_github, "wait_for_verify")


def test_local_tag_identity_reads_exact_objects(tmp_path: Path, mocker) -> None:
    output = mocker.patch.object(
        publish_github,
        "_output",
        side_effect=("tag", "b" * 40, "a" * 40),
    )

    assert publish_github._local_tag_identity(tmp_path, "v1.2.3", "a" * 40) == (
        "b" * 40,
        "a" * 40,
    )
    assert output.call_count == 3


def test_release_checkout_verification_preserves_repository_state(tmp_path: Path) -> None:
    repository, commit_oid = _release_checkout(tmp_path)
    before = _checkout_state(repository)

    assert publish_github._local_tag_identity(repository, "v1.2.3", commit_oid)[1] == commit_oid

    assert _checkout_state(repository) == before


def test_release_checkout_mismatch_fails_without_repository_state_change(tmp_path: Path) -> None:
    repository, _ = _release_checkout(tmp_path)
    before = _checkout_state(repository)

    with pytest.raises(
        publish_github.GitHubPublishError,
        match="release tag differs from the verified commit",
    ):
        publish_github._local_tag_identity(repository, "v1.2.3", "0" * 40)

    assert _checkout_state(repository) == before


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

    assert run.call_count == 1
    assert all(call.args[0][0] == str(environment_python) for call in run.call_args_list)
