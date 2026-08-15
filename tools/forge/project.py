"""Project accepted history into one forward-only Forge identity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from tools.forge import context, history, runner_admission


class ProjectionError(RuntimeError):
    """A provider projection cannot be constructed without weakening trust."""


class Projection:
    """One isolated provider history projection transaction."""

    def __init__(
        self,
        repository: Path,
        identity: context.PublicationContext,
        signing: context.SigningContext,
        anchor: Path,
    ) -> None:
        self.repository = repository
        self.identity = identity
        self.signing = signing
        self.anchor = anchor

    def existing_mapping(
        self,
        source_commits: list[str],
        remote_tip: str,
        *,
        continuity_base: str | None = None,
        projected_anchor: str | None = None,
        expected_remote_tip: str | None = None,
    ) -> tuple[str | None, list[tuple[str, str]], str | None]:
        """Validate and map an existing provider history."""

        if not remote_tip:
            if continuity_base or projected_anchor or expected_remote_tip:
                raise ProjectionError("continuity coordinates require an existing provider tip")
            return None, [], None
        if len(
            tuple(filter(None, (continuity_base, projected_anchor, expected_remote_tip)))
        ) not in {
            0,
            3,
        }:
            raise ProjectionError(
                "continuity base, projected anchor, and expected provider tip must be supplied together"
            )
        if expected_remote_tip and remote_tip != expected_remote_tip:
            raise ProjectionError("provider tip changed after continuity observation")
        if projected_anchor and not _is_ancestor(self.repository, projected_anchor, remote_tip):
            raise ProjectionError("projected anchor is not an ancestor of the provider tip")
        projected_commits = _run(self.repository, "rev-list", remote_tip).splitlines()
        trusted_commits = (
            _run(
                self.repository,
                "rev-list",
                "--ancestry-path",
                f"{projected_anchor}^..{remote_tip}",
            ).splitlines()
            if projected_anchor
            else projected_commits
        )
        if any(
            not _commit_valid(
                self.repository,
                commit,
                self.identity.email,
                self.anchor,
                self.signing.program,
            )
            for commit in trusted_commits
        ):
            raise ProjectionError("existing provider identity or signature is invalid")
        try:
            if continuity_base:
                observed_anchor, mapping = history.map_histories_from_base(
                    self.repository,
                    source_commits,
                    projected_commits,
                    continuity_base,
                )
                if observed_anchor != projected_anchor:
                    raise ProjectionError(
                        "provider history anchor differs from continuity observation"
                    )
                mapping = [pair for pair in mapping if pair[0] != continuity_base] + [
                    (continuity_base, remote_tip)
                ]
                return continuity_base, mapping, observed_anchor
            base, mapping = history.map_histories(
                self.repository, source_commits, projected_commits, remote_tip
            )
            return base, mapping, None
        except history.HistoryError as error:
            raise ProjectionError(str(error)) from error

    def create_commit(self, source_commit: str, parents: list[str]) -> str:
        """Create and verify one provider-identity commit."""

        message = _run(self.repository, "show", "-s", "--format=%B", source_commit) + "\n"
        environment = _environment()
        environment.update(
            {
                "GIT_AUTHOR_NAME": self.identity.name,
                "GIT_AUTHOR_EMAIL": self.identity.email,
                "GIT_AUTHOR_DATE": _run(
                    self.repository, "show", "-s", "--format=%aI", source_commit
                ),
                "GIT_COMMITTER_NAME": self.identity.name,
                "GIT_COMMITTER_EMAIL": self.identity.email,
                "GIT_COMMITTER_DATE": _run(
                    self.repository, "show", "-s", "--format=%cI", source_commit
                ),
            }
        )
        command = (
            "git",
            "-C",
            str(self.repository),
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={self.signing.program}",
            "-c",
            f"user.signingkey={self.signing.public_key}",
            "commit-tree",
            "-S",
            _run(self.repository, "show", "-s", "--format=%T", source_commit),
            *parents,
        )
        try:
            projected = subprocess.run(
                command,
                input=message,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise ProjectionError("signed provider commit creation failed") from error
        if not _commit_valid(
            self.repository,
            projected,
            self.identity.email,
            self.anchor,
            self.signing.program,
        ):
            raise ProjectionError("generated commit does not satisfy provider trust")
        return projected

    def append(
        self,
        source: str,
        source_commits: list[str],
        base_source: str | None,
        mapping: list[tuple[str, str]],
        remote_tip: str,
    ) -> tuple[str, list[tuple[str, str]]]:
        """Append only the source commits absent from provider history."""

        projected_by_source = dict(mapping)
        new_commits = (
            _run(
                self.repository,
                "rev-list",
                "--reverse",
                "--topo-order",
                f"{base_source}..{source}",
            ).splitlines()
            if base_source
            else source_commits
        )
        projected = remote_tip
        created: list[tuple[str, str]] = []
        for source_commit in new_commits:
            parents: list[str] = []
            for source_parent in _run(
                self.repository, "show", "-s", "--format=%P", source_commit
            ).split():
                projected_parent = projected_by_source.get(source_parent)
                if not projected_parent:
                    raise ProjectionError(
                        f"source parent has no provider projection: {source_parent}"
                    )
                parents.extend(("-p", projected_parent))
            projected = self.create_commit(source_commit, parents)
            projected_by_source[source_commit] = projected
            mapping.append((source_commit, projected))
            created.append((source_commit, projected))
        return projected, created


def _run(repository: Path, *args: str, environment: dict[str, str] | None = None) -> str:
    try:
        return subprocess.run(
            ("git", "-C", str(repository), *args),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else ""
        raise ProjectionError(detail or "Git projection operation failed") from error


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    """Return whether one commit is an ancestor without weakening Git errors."""

    result = subprocess.run(
        (
            "git",
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    if result.returncode in {0, 1}:
        return result.returncode == 0
    raise ProjectionError(result.stderr.strip() or "Git ancestry check failed")


def _environment() -> dict[str, str]:
    value = os.environ.copy()
    value.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return value


def _commit_valid(repository: Path, commit: str, email: str, anchor: Path, program: Path) -> bool:
    if _run(repository, "show", "-s", "--format=%ae", commit) != email:
        return False
    if _run(repository, "show", "-s", "--format=%ce", commit) != email:
        return False
    try:
        _run(
            repository,
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={program}",
            "-c",
            f"gpg.ssh.allowedSignersFile={anchor.resolve()}",
            "verify-commit",
            commit,
            environment=_environment(),
        )
        return True
    except ProjectionError:
        return False


def _write_mapping(
    path: Path,
    *,
    provider: str,
    source: str,
    projected: str,
    tree: str,
    base_source: str | None,
    base_projected: str | None,
    mapping: list[tuple[str, str]],
    created: list[tuple[str, str]],
    continuity_source_base: str | None,
    continuity_projected_anchor: str | None,
) -> None:
    payload = {
        "schema_version": 1,
        "provider": provider,
        "source_commit": source,
        "projected_commit": projected,
        "tree": tree,
        "base_source_commit": base_source,
        "base_projected_commit": base_projected,
        "mapping": [{"source": left, "projected": right} for left, right in mapping],
        "created": [{"source": left, "projected": right} for left, right in created],
        "continuity_mode": "explicit-base" if continuity_source_base else "automatic",
        "continuity_source_base": continuity_source_base,
        "continuity_projected_anchor": continuity_projected_anchor,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _prepare_projection(
    *,
    root: Path,
    repository: Path,
    remote: str,
    provider: str,
    publication_context: Path,
    anchor: Path,
    source: str,
    continuity_base: str | None,
    projected_anchor: str | None,
    expected_remote_tip: str | None,
    workspace: Path,
) -> tuple[Projection, str, list[str], str | None, list[tuple[str, str]], str | None]:
    """Prepare one isolated, exact-CAS projection transaction."""

    remote_url = _run(root, "config", "--local", "--get", f"remote.{remote}.url")
    subprocess.run(
        (
            "git",
            "clone",
            "--quiet",
            "--no-local",
            "--no-tags",
            f"file://{root}",
            str(repository),
        ),
        check=True,
        env=_environment(),
    )
    _run(repository, "remote", "remove", "origin")
    _run(repository, "remote", "add", "target", remote_url)
    identity = context.load(publication_context, provider)
    signing = context.select_signing_key(identity, workspace / "signing-key.pub")
    remote_tip = _run(repository, "ls-remote", "--heads", "target", "refs/heads/main")
    remote_tip = remote_tip.split(maxsplit=1)[0] if remote_tip else ""
    if remote_tip:
        _run(
            repository,
            "fetch",
            "--quiet",
            "--no-tags",
            "target",
            "refs/heads/main:refs/remotes/target/main",
            environment=_environment(),
        )
    transaction = Projection(repository, identity, signing, anchor)
    source_commits = _run(repository, "rev-list", "--reverse", "--topo-order", source).splitlines()
    resolved_base = (
        _run(repository, "rev-parse", "--verify", f"{continuity_base}^{{commit}}")
        if continuity_base
        else None
    )
    base_source, mapping, observed_anchor = transaction.existing_mapping(
        source_commits,
        remote_tip,
        continuity_base=resolved_base,
        projected_anchor=projected_anchor,
        expected_remote_tip=expected_remote_tip,
    )
    return transaction, remote_tip, source_commits, base_source, mapping, observed_anchor


def project(
    *,
    root: Path,
    provider: str,
    source_ref: str,
    remote: str,
    map_output: Path | None,
    publication_context: Path,
    anchor: Path,
    repository_coordinate: str,
    runner_tag: str | None,
    continuity_base: str | None,
    projected_anchor: str | None,
    expected_remote_tip: str | None,
) -> str:
    """Create and atomically publish one provider-specific history projection."""

    if provider not in {"gitlab", "github"}:
        raise ProjectionError("provider must be gitlab or github")
    if not anchor.is_file() or anchor.is_symlink():
        raise ProjectionError(f"{provider} commit trust anchor is unavailable")
    if _run(root, "status", "--porcelain"):
        raise ProjectionError("refusing Forge projection with a dirty checkout")
    source = _run(root, "rev-parse", "--verify", "--end-of-options", f"{source_ref}^{{commit}}")
    source_tree = _run(root, "rev-parse", f"{source}^{{tree}}")
    if provider == "gitlab":
        runner_admission._gitlab(repository_coordinate, runner_tag)
    else:
        runner_admission._github(repository_coordinate)

    with tempfile.TemporaryDirectory(
        prefix=f"codex-responses-proxy-{provider}-projection-"
    ) as name:
        workspace = Path(name)
        repository = workspace / "repository"
        if bool(continuity_base) != bool(projected_anchor):
            raise ProjectionError("continuity base and projected anchor must be supplied together")
        (
            transaction,
            remote_tip,
            source_commits,
            base_source,
            mapping,
            observed_projected_anchor,
        ) = _prepare_projection(
            root=root,
            repository=repository,
            remote=remote,
            provider=provider,
            publication_context=publication_context,
            anchor=anchor,
            source=source,
            continuity_base=continuity_base,
            projected_anchor=projected_anchor,
            expected_remote_tip=expected_remote_tip,
            workspace=workspace,
        )
        base_projected = remote_tip or None
        projected, created = transaction.append(
            source, source_commits, base_source, mapping, remote_tip
        )

        if not projected or _run(repository, "rev-parse", f"{projected}^{{tree}}") != source_tree:
            raise ProjectionError("projected branch tree differs from accepted source")
        _run(repository, "update-ref", "refs/heads/main", projected)
        _run(
            repository,
            "push",
            "--atomic",
            "target",
            "refs/heads/main:refs/heads/main",
            "refs/heads/main:refs/heads/dev",
            environment=_environment(),
        )
        if map_output:
            _write_mapping(
                map_output,
                provider=provider,
                source=source,
                projected=projected,
                tree=source_tree,
                base_source=base_source,
                base_projected=base_projected,
                mapping=mapping,
                created=created,
                continuity_source_base=base_source if continuity_base else None,
                continuity_projected_anchor=observed_projected_anchor,
            )
        return projected


def _command(
    *,
    provider: str,
    source_ref: str = "HEAD",
    remote: str | None = None,
    map_output: Path | None = None,
    root: Path | None = None,
    publication_context: Path,
    anchor: Path,
    repository: str,
    runner_tag: str | None = None,
    continuity_base: str | None = None,
    projected_anchor: str | None = None,
    expect_remote_tip: str | None = None,
    as_json: Annotated[bool, Parameter(name="--json", negative=False)] = False,
) -> None:
    """Project one accepted source independently to GitLab or GitHub."""

    selected_remote = remote or ("origin" if provider == "gitlab" else "github")
    try:
        projected = project(
            root=(root or Path.cwd()).resolve(),
            provider=provider,
            source_ref=source_ref,
            remote=selected_remote,
            map_output=map_output,
            publication_context=publication_context,
            anchor=anchor,
            repository_coordinate=repository,
            runner_tag=runner_tag,
            continuity_base=continuity_base,
            projected_anchor=projected_anchor,
            expected_remote_tip=expect_remote_tip,
        )
    except (
        ProjectionError,
        context.PublicationContextError,
        runner_admission.AdmissionError,
    ) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    result = {
        "provider": provider,
        "projected_commit": projected,
        "branches": ["main", "dev"],
    }
    print(
        json.dumps(result, sort_keys=True)
        if as_json
        else f"{provider} identity projection synchronized: {projected}"
    )


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run projection through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
