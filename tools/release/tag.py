"""Create one immutable provider-native release tag."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cyclopts import App

from tools.forge import context, tag_signature
from tools.release.publication.git import _TAG


class TagError(RuntimeError):
    """A provider-native tag cannot be created safely."""


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
        raise TagError(detail or "Git release tag operation failed") from error


def _environment() -> dict[str, str]:
    value = os.environ.copy()
    value.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return value


def _metadata(repository: Path, provider: str, *args: str) -> None:
    """Run metadata validation from the exact provider checkout."""

    try:
        subprocess.run(
            (
                sys.executable,
                str(repository / "tools/release/metadata.py"),
                "--provider",
                provider,
                *args,
            ),
            cwd=repository,
            check=True,
            capture_output=True,
            env=_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise TagError(f"{provider} release metadata validation failed") from error


def create(
    *,
    root: Path,
    provider: str,
    tag: str,
    remote: str,
    publication_context: Path,
    anchor: Path,
) -> str:
    """Create, verify, and publish one exact provider-native tag."""

    if provider not in {"gitlab", "github"} or _TAG.fullmatch(tag) is None:
        raise TagError("provider and tag must identify gitlab|github and vMAJOR.MINOR.PATCH")
    if _run(root, "status", "--porcelain"):
        raise TagError(f"refusing {provider} tag with a dirty checkout")
    identity = context.load(publication_context, provider)
    remote_url = _run(root, "config", "--local", "--get", f"remote.{remote}.url")
    with tempfile.TemporaryDirectory(prefix=f"codex-responses-proxy-{provider}-tag-") as name:
        workspace = Path(name)
        repository = workspace / "repository"
        subprocess.run(
            ("git", "clone", "--quiet", "--no-tags", remote_url, str(repository)),
            check=True,
            env=_environment(),
        )
        _run(repository, "fetch", "--quiet", "--force", "--prune", "--prune-tags", "origin")
        _run(
            repository,
            "fetch",
            "--quiet",
            "--force",
            "--prune",
            "--prune-tags",
            "origin",
            "+refs/tags/*:refs/tags/*",
        )
        if _run(repository, "tag", "--list", tag):
            raise TagError(f"{provider} tag already exists: {tag}")
        target = _run(repository, "rev-parse", "refs/remotes/origin/main^{commit}")
        _run(repository, "checkout", "--quiet", "--detach", target)
        _metadata(repository, provider, "--prepare-release")
        signing = context.select_signing_key(identity, workspace / "signing-key.pub")
        _run(
            repository,
            "-c",
            f"user.name={identity.name}",
            "-c",
            f"user.email={identity.email}",
            "-c",
            "user.useConfigOnly=true",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.program={signing.program}",
            "-c",
            f"user.signingkey={signing.public_key}",
            "tag",
            "-s",
            "-a",
            tag,
            target,
            "-m",
            f"Codex Responses Proxy {tag}",
        )
        _metadata(repository, provider, "--tag", tag)
        tag_signature.verify(repository, tag, provider, anchor)
        _run(repository, "push", "--quiet", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
        return _run(repository, "rev-parse", f"refs/tags/{tag}")


def _command(
    *,
    provider: str,
    tag: str,
    publication_context: Path,
    anchor: Path,
    root: Path = Path.cwd(),
    remote: str | None = None,
) -> None:
    """Create one signed tag on exactly one selected Forge."""

    selected_remote = remote or ("origin" if provider == "gitlab" else "github")
    try:
        tag_oid = create(
            root=root.resolve(),
            provider=provider,
            tag=tag,
            remote=selected_remote,
            publication_context=publication_context,
            anchor=anchor,
        )
    except (TagError, context.PublicationContextError, tag_signature.TagSignatureError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(f"{provider} provider-native release tag created: {tag} ({tag_oid})")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run tag creation through the repository parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
