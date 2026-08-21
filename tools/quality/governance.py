"""Run the repository's provider-neutral governance checks once."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from cyclopts import App

ROOT = Path(__file__).resolve().parents[2]
LINK_POLICY = ".config/checks/links/lychee.toml"
MARKDOWN_INPUTS = ("./*.md", "./**/*.md")


class GovernanceError(RuntimeError):
    """A repository governance concern failed."""


def _commands(*, online_links: bool) -> tuple[tuple[str, ...], ...]:
    """Return the single ordered governance graph for this repository."""

    link_mode = () if online_links else ("--offline",)
    return (
        ("cue", "vet", ".config/ci/pipeline.cue"),
        (sys.executable, "-m", "tools.ci.project"),
        ("openspec", "validate", "--all", "--strict", "--no-interactive"),
        ("actionlint", ".github/workflows/verify.yml"),
        (
            "deptry",
            "src/codex_responses_proxy",
            "--config",
            "pyproject.toml",
            "--no-ansi",
        ),
        (
            "vulture",
            "src/codex_responses_proxy",
            "--config",
            ".config/checks/dead-code/vulture.toml",
        ),
        ("gitleaks", "git", "--platform", "gitlab", "--redact", "--no-banner", "."),
        ("lychee", "--config", LINK_POLICY, *link_mode, *MARKDOWN_INPUTS),
        (sys.executable, "tools/release/metadata.py"),
        (sys.executable, "-m", "tools.quality.repository"),
    )


def audit(*, online_links: bool = False) -> None:
    """Execute every governance concern from one composition root."""

    for command in _commands(online_links=online_links):
        try:
            completed = subprocess.run(command, cwd=ROOT, check=False)
        except OSError as error:
            raise GovernanceError(f"governance tool unavailable: {command[0]}") from error
        if completed.returncode:
            raise GovernanceError(f"governance check failed: {command[0]}")


def _command(*, online_links: bool = False) -> None:
    """Run deterministic checks, optionally including external links."""

    audit(online_links=online_links)


def main(argv: Iterable[str] = ()) -> None:
    """Run repository governance through the shared parser stack."""

    try:
        App(default_command=_command, help=__doc__, result_action="return_value")(tuple(argv))
    except GovernanceError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])
