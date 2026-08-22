"""Create one local release tag and publish its exact object to one Forge peer."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from cyclopts import App

from codex_responses_proxy import product_identity
from tools.forge import context
from tools.forge import tag_signature
from tools.git_environment import isolated_config_environment
from tools.release import identity


class TagError(RuntimeError):
    """A local product tag cannot be created or published safely."""


def _run(repository: Path, *args: str, environment: dict[str, str] | None = None) -> str:
    try:
        return subprocess.run(
            ("git", "-C", str(repository), *args),
            check=True,
            capture_output=True,
            text=True,
            env=environment or isolated_config_environment(),
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else ""
        raise TagError(detail or "Git release tag operation failed") from error


def _metadata(repository: Path, *args: str) -> None:
    """Run provider-neutral product metadata validation."""
    try:
        subprocess.run(
            (
                sys.executable,
                "-m",
                "tools.release.metadata",
                *args,
            ),
            cwd=repository,
            check=True,
            capture_output=True,
            env=isolated_config_environment({"PYTHONDONTWRITEBYTECODE": "1"}),
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise TagError("product release metadata validation failed") from error


def create(
    *,
    root: Path,
    provider: str,
    tag: str,
    remote: str,
    publication_context: Path,
    anchor: Path,
) -> str:
    """Create the local tag once, then publish that exact object to one peer."""
    if provider not in {"gitlab", "github"} or not identity.is_tag(tag):
        raise TagError("provider and tag must identify gitlab|github and vMAJOR.MINOR.PATCH")
    if _run(root, "status", "--porcelain"):
        raise TagError(f"refusing {provider} tag with a dirty checkout")
    publication_identity = context.load(publication_context)
    reference = f"refs/tags/{tag}"
    if not _run(root, "tag", "--list", tag):
        target = _run(root, "rev-parse", "refs/heads/main^{commit}")
        _metadata(root, "--prepare-release")
        with tempfile.TemporaryDirectory(prefix=f"{product_identity.PRODUCT_SLUG}-tag-") as name:
            signing = context.select_signing_key(
                publication_identity, Path(name) / "signing-key.pub"
            )
            _run(
                root,
                "-c",
                f"user.name={publication_identity.name}",
                "-c",
                f"user.email={publication_identity.email}",
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
                product_identity.release_title(tag),
            )
    _metadata(root, "--tag", tag)
    tag_signature.verify(root, tag, anchor)
    tag_oid = _run(root, "rev-parse", reference)
    observed = _run(root, "ls-remote", "--tags", remote, reference).split()
    if observed:
        if len(observed) != 2 or observed[1] != reference:
            raise TagError(f"{provider} release tag observation is malformed: {tag}")
        if observed[0] != tag_oid:
            raise TagError(f"{provider} release tag differs from local: {tag}")
        return tag_oid
    _run(root, "push", "--quiet", remote, f"{reference}:{reference}")
    published = _run(root, "ls-remote", "--tags", remote, reference).split()
    if published != [tag_oid, reference]:
        raise TagError(f"{provider} release tag does not equal local after publication: {tag}")
    return tag_oid


def _command(
    *,
    provider: str,
    tag: str,
    publication_context: Path,
    anchor: Path,
    root: Path | None = None,
    remote: str | None = None,
) -> None:
    """Create one signed tag on exactly one selected Forge."""
    root = (root or Path.cwd()).resolve()
    selected_remote = remote or ("origin" if provider == "gitlab" else "github")
    try:
        tag_oid = create(
            root=root,
            provider=provider,
            tag=tag,
            remote=selected_remote,
            publication_context=publication_context,
            anchor=anchor,
        )
    except (
        TagError,
        context.PublicationContextError,
        tag_signature.TagSignatureError,
    ) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(f"{provider} release tag synchronized: {tag} ({tag_oid})")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run tag creation through the repository parser stack."""
    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
