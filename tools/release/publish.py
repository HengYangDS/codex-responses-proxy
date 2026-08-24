"""Publish one immutable signed bundle through a selected Forge adapter."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cyclopts import App

from codex_responses_proxy import product_identity
from tools.release import publish_github
from tools.release import publish_gitlab


class PublicationError(RuntimeError):
    """One or more selected Forge publications did not complete."""


def _github(
    *,
    repository: str,
    tag: str,
    commit_oid: str,
    assets: Path,
    workspace: Path,
    checkout: Path | None = None,
) -> None:
    """Publish or verify one exact GitHub release."""
    state = publish_github.publish(
        repository=repository,
        tag=tag,
        commit_oid=commit_oid,
        checkout=checkout or Path.cwd(),
        tag_trust=os.environ.get(product_identity.environment_name("GITHUB_TAG_TRUST"), ""),
        asset_trust=os.environ.get("RELEASE_ASSET_TRUST", ""),
        source=assets,
        workspace=workspace,
    )
    print(f"GitHub release {state}: {tag}")


def _gitlab(
    *,
    api_base: str,
    project_id: int,
    tag: str,
    assets: Path,
    credential_kind: publish_gitlab.CredentialKind,
) -> None:
    """Publish or verify one exact GitLab release."""
    token_variable = (
        "CI_JOB_TOKEN"
        if credential_kind is publish_gitlab.CredentialKind.JOB_TOKEN
        else product_identity.environment_name("GITLAB_PRIVATE_TOKEN")
    )
    token = os.environ.get(token_variable, "")
    trust = os.environ.get("RELEASE_ASSET_TRUST", "")
    if not token or not trust:
        raise publish_gitlab.GitLabPublishError(
            f"GitLab {credential_kind.value} credential or release trust is unavailable"
        )
    state = publish_gitlab.publish(
        api_base=api_base,
        project_id=project_id,
        tag=tag,
        token=token,
        credential_kind=credential_kind,
        source=assets,
        trust=trust,
    )
    print(f"GitLab release {state}: {tag}")


def _both(
    *,
    github_repository: str,
    gitlab_api_base: str,
    gitlab_project_id: int,
    tag: str,
    commit_oid: str,
    assets: Path,
    workspace: Path,
    gitlab_credential_kind: publish_gitlab.CredentialKind,
    checkout: Path | None = None,
) -> None:
    """Publish the same immutable bundle through both independent adapters."""
    failures: list[str] = []
    try:
        _github(
            repository=github_repository,
            tag=tag,
            commit_oid=commit_oid,
            assets=assets,
            workspace=workspace,
            checkout=checkout,
        )
    except publish_github.GitHubPublishError as error:
        failures.append(f"github: {error}")
    try:
        _gitlab(
            api_base=gitlab_api_base,
            project_id=gitlab_project_id,
            tag=tag,
            assets=assets,
            credential_kind=gitlab_credential_kind,
        )
    except publish_gitlab.GitLabPublishError as error:
        failures.append(f"gitlab: {error}")
    if failures:
        raise PublicationError("; ".join(failures))


def _prepare_checkout(*, tag: str, commit_oid: str, checkout: Path | None = None) -> None:
    """Prepare one exact annotated release checkout."""
    tag_oid, target = publish_github.prepare_checkout(checkout or Path.cwd(), tag, commit_oid)
    print(f"release checkout prepared: {tag_oid} -> {target}")


def _app() -> App:
    app = App(help=__doc__, result_action="return_value")
    app.command(_github, name="github")
    app.command(_gitlab, name="gitlab")
    app.command(_both, name="both")
    app.command(_prepare_checkout, name="prepare-checkout")
    return app


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run provider-neutral publication through the repository parser stack."""
    try:
        _app()(tuple(sys.argv[1:] if argv is None else argv))
    except (
        publish_github.GitHubPublishError,
        publish_gitlab.GitLabPublishError,
        PublicationError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
