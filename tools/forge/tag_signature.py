"""Verify one provider-native annotated release tag."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cyclopts import App

from tools.release.publication.git import _TAG


class TagSignatureError(RuntimeError):
    """A release tag or its trust input is invalid."""


def verify(repository: Path, tag: str, provider: str, anchor: Path) -> None:
    """Verify one exact provider tag with one explicit external anchor."""

    if provider not in {"gitlab", "github"}:
        raise TagSignatureError("release provider must be gitlab or github")
    if _TAG.fullmatch(tag.removeprefix("github/")) is None:
        raise TagSignatureError(f"release tag must be v<semver>: {tag}")
    if not anchor.is_file() or anchor.is_symlink():
        raise TagSignatureError(f"{provider} release trust anchor is unavailable")
    try:
        subprocess.run(
            ("git", "-C", str(repository), "rev-parse", "--verify", f"refs/tags/{tag}"),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "-c",
                "gpg.format=ssh",
                "-c",
                "gpg.ssh.program=ssh-keygen",
                "-c",
                f"gpg.ssh.allowedSignersFile={anchor.resolve()}",
                "verify-tag",
                tag,
            ),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise TagSignatureError(f"{provider} release tag signature is invalid") from error


def _command(repository: Path, tag: str, provider: str, anchor: Path) -> None:
    """Verify one provider-native tag without implicit trust sources."""

    try:
        verify(repository.resolve(), tag, provider, anchor)
    except TagSignatureError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(f"{provider} release tag signature: OK ({tag})")


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run tag verification through the repository parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(
        tuple(sys.argv[1:] if argv is None else argv)
    )


if __name__ == "__main__":
    main()
