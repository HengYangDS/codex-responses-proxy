"""Provider-neutral release publication command contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.release import publish


def test_github_command_dispatches_verified_inputs_without_secret_arguments(
    tmp_path: Path, mocker
) -> None:
    adapter = mocker.patch.object(publish.publish_github, "publish", return_value="created")
    mocker.patch.dict(
        publish.os.environ,
        {
            "CODEX_RESPONSES_PROXY_GITHUB_TAG_TRUST": "tag trust",
            "RELEASE_ASSET_TRUST": "asset trust",
        },
        clear=True,
    )

    publish.main(
        (
            "github",
            "--repository",
            "team/proxy",
            "--tag",
            "v1.2.3",
            "--commit-oid",
            "a" * 40,
            "--assets",
            str(tmp_path / "assets"),
            "--workspace",
            str(tmp_path / "workspace"),
            "--checkout",
            str(tmp_path),
        )
    )

    adapter.assert_called_once_with(
        repository="team/proxy",
        tag="v1.2.3",
        commit_oid="a" * 40,
        checkout=tmp_path,
        tag_trust="tag trust",
        asset_trust="asset trust",
        source=tmp_path / "assets",
        workspace=tmp_path / "workspace",
    )


@pytest.mark.parametrize(
    ("kind", "variable", "token"),
    [
        (publish.publish_gitlab.CredentialKind.JOB_TOKEN, "CI_JOB_TOKEN", "job token"),
        (
            publish.publish_gitlab.CredentialKind.PRIVATE_TOKEN,
            "CODEX_RESPONSES_PROXY_GITLAB_PRIVATE_TOKEN",
            "private token",
        ),
    ],
)
def test_gitlab_command_reads_only_the_declared_credential(
    tmp_path: Path, mocker, kind: publish.publish_gitlab.CredentialKind, variable: str, token: str
) -> None:
    adapter = mocker.patch.object(publish.publish_gitlab, "publish", return_value="matched")
    mocker.patch.dict(
        publish.os.environ,
        {
            "CI_JOB_TOKEN": "unused job token",
            "CODEX_RESPONSES_PROXY_GITLAB_PRIVATE_TOKEN": "unused private token",
            variable: token,
            "RELEASE_ASSET_TRUST": "asset trust",
        },
        clear=True,
    )

    publish.main(
        (
            "gitlab",
            "--api-base",
            "https://gitlab.example/api/v4",
            "--project-id",
            "453",
            "--tag",
            "v1.2.3",
            "--assets",
            str(tmp_path / "assets"),
            "--credential-kind",
            kind.value,
        )
    )

    adapter.assert_called_once_with(
        api_base="https://gitlab.example/api/v4",
        project_id=453,
        tag="v1.2.3",
        token=token,
        credential_kind=kind,
        source=tmp_path / "assets",
        trust="asset trust",
    )


def test_command_fails_closed_without_provider_credentials(tmp_path: Path, mocker) -> None:
    mocker.patch.dict(publish.os.environ, {}, clear=True)

    with pytest.raises(SystemExit) as failure:
        publish.main(
            (
                "gitlab",
                "--api-base",
                "https://gitlab.example/api/v4",
                "--project-id",
                "453",
                "--tag",
                "v1.2.3",
                "--assets",
                str(tmp_path),
                "--credential-kind",
                "job-token",
            )
        )

    assert failure.value.code == 1


def test_provider_adapters_do_not_expose_parallel_command_roots() -> None:
    assert not hasattr(publish.publish_github, "main")
    assert not hasattr(publish.publish_github, "_app")
    assert not hasattr(publish.publish_gitlab, "main")
    assert not hasattr(publish.publish_gitlab, "_command")


def test_dual_command_projects_the_same_bundle_to_both_peers(tmp_path: Path, mocker) -> None:
    github = mocker.patch.object(publish, "_github")
    gitlab = mocker.patch.object(publish, "_gitlab")
    assets = tmp_path / "assets"
    workspace = tmp_path / "workspace"

    publish._both(
        github_repository="team/proxy",
        gitlab_api_base="https://gitlab.example/api/v4",
        gitlab_project_id=453,
        tag="v1.2.3",
        commit_oid="a" * 40,
        assets=assets,
        workspace=workspace,
        gitlab_credential_kind=publish.publish_gitlab.CredentialKind.JOB_TOKEN,
        checkout=tmp_path,
    )

    github.assert_called_once_with(
        repository="team/proxy",
        tag="v1.2.3",
        commit_oid="a" * 40,
        assets=assets,
        workspace=workspace,
        checkout=tmp_path,
    )
    gitlab.assert_called_once_with(
        api_base="https://gitlab.example/api/v4",
        project_id=453,
        tag="v1.2.3",
        assets=assets,
        credential_kind=publish.publish_gitlab.CredentialKind.JOB_TOKEN,
    )


def test_dual_command_attempts_both_peers_before_reporting_failure(tmp_path: Path, mocker) -> None:
    mocker.patch.object(
        publish,
        "_github",
        side_effect=publish.publish_github.GitHubPublishError("github unavailable"),
    )
    gitlab = mocker.patch.object(publish, "_gitlab")

    with pytest.raises(publish.PublicationError, match="github unavailable"):
        publish._both(
            github_repository="team/proxy",
            gitlab_api_base="https://gitlab.example/api/v4",
            gitlab_project_id=453,
            tag="v1.2.3",
            commit_oid="a" * 40,
            assets=tmp_path / "assets",
            workspace=tmp_path / "workspace",
            gitlab_credential_kind=publish.publish_gitlab.CredentialKind.JOB_TOKEN,
        )

    gitlab.assert_called_once()
