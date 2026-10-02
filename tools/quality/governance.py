"""Run the repository's provider-neutral governance checks once."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

from cyclopts import App

ROOT = Path(__file__).resolve().parents[2]
LINK_POLICY = ".config/quality/native/lychee.toml"
_REPOSITORY_ROOT_PARSER = r"""
import { json } from "node:stream/consumers";

try {
  const roots = (await json(process.stdin)).map((value) => {
    if (!/^https?:\/\//iu.test(value) || /[\s?#]/u.test(value) ||
        /^https?:\/\/[/\\]*[^/\\]*@/iu.test(value)) {
      throw new Error("Invalid repository root");
    }
    const url = new URL(value);
    if (!url.hostname || url.username || url.password || url.port === "0" ||
        !url.pathname.replace(/\/+$/u, "")) {
      throw new Error("Invalid repository root");
    }
    return url.href.replace(/\/+$/u, "");
  });
  process.stdout.write(JSON.stringify(roots));
} catch {
  process.stderr.write("Invalid publication repository root\n");
  process.exitCode = 1;
}
"""


def _tracked_current(suffixes: tuple[str, ...]) -> tuple[str, ...]:
    """Return tracked current authorities for one native formatter."""
    completed = subprocess.run(
        ("git", "--git-dir=.git", "--work-tree=.", "ls-files", "-z"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return tuple(
        path
        for path in completed.stdout.decode().split("\0")
        if path and path.endswith(suffixes) and not path.startswith("openspec/changes/archive/")
    )


class GovernanceError(RuntimeError):
    """A repository governance concern failed."""


def _canonical_repository_roots(repositories: dict[str, str]) -> dict[str, str]:
    """Use the locked native WHATWG parser without exposing input in command arguments."""
    try:
        completed = subprocess.run(
            ("node", "--input-type=module", "--eval", _REPOSITORY_ROOT_PARSER),
            cwd=ROOT,
            input=json.dumps(tuple(repositories.values())),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        )
        roots = json.loads(completed.stdout)
        if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
            raise ValueError("native repository root observation is invalid")
        return dict(zip(repositories, roots, strict=True))
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
        raise GovernanceError("publication peer identity is invalid") from error


def _peer_link_exclusions(peer: str) -> tuple[str, ...]:
    """Limit network exclusions to exact unselected declared repository roots."""
    try:
        metadata = tomllib.loads((ROOT / ".ethos/release.toml").read_text(encoding="utf-8"))
        peers = metadata["publication"]["peers"]
        if not isinstance(peers, list) or not peers:
            raise ValueError("publication peers are unavailable")
        repositories: dict[str, str] = {}
        for record in peers:
            name, repository = record["id"], record["forge_repository"]
            if (
                not isinstance(name, str)
                or not name
                or any(char.isspace() for char in name)
                or name in repositories
            ):
                raise ValueError("publication peer identity is ambiguous")
            if not isinstance(repository, str) or any(char.isspace() for char in repository):
                raise ValueError("publication peer identity is malformed")
            repositories[name] = repository
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise GovernanceError("publication peer identity is invalid") from error
    if peer not in repositories:
        raise GovernanceError("online link checks require a declared publication peer")
    repositories = _canonical_repository_roots(repositories)
    if any(
        left_name != right_name and (left == right or left.startswith(right + "/"))
        for left_name, left in repositories.items()
        for right_name, right in repositories.items()
    ):
        raise GovernanceError("publication peer identity contains overlapping repositories")
    return tuple(
        f"--exclude=^{re.escape(repository)}(?:[/?#]|$)"
        for name, repository in repositories.items()
        if name != peer
    )


def _commands(*, online_links: bool, peer: str | None = None) -> tuple[tuple[str, ...], ...]:
    """Return the single ordered governance graph for this repository."""
    if peer is not None and not online_links:
        raise GovernanceError("peer selection requires --online-links")
    peer_scope = () if peer is None else _peer_link_exclusions(peer)
    link_mode = () if online_links else ("--offline",)
    structured_text = _tracked_current((".md", ".mjs", ".yaml", ".yml", ".json", ".jsonc"))
    markdown = tuple(path for path in structured_text if path.endswith(".md"))
    toml = _tracked_current((".toml",))
    return (
        (
            "npm",
            "exec",
            "--offline",
            "--",
            "prettier",
            "--check",
            "--config",
            ".config/quality/native/prettier.json",
            "--ignore-path",
            ".config/quality/native/prettier.ignore",
            *structured_text,
        ),
        (
            "taplo",
            "format",
            "--check",
            "--config",
            ".config/quality/native/taplo.toml",
            *toml,
        ),
        (
            "npm",
            "exec",
            "--offline",
            "--",
            "markdownlint-cli2",
            "--config",
            ".config/quality/native/markdownlint-cli2.mjs",
            "--no-globs",
            *markdown,
        ),
        (
            "vale",
            "--config=.config/quality/native/vale.ini",
            "--no-global",
            "--no-color",
            *markdown,
        ),
        ("cue", "fmt", "--check", "--files", ".config/ci/pipeline.cue"),
        ("cue", "vet", ".config/ci/pipeline.cue"),
        (sys.executable, "-m", "tools.ci.project"),
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "repository_toolchain",
            "tests/quality/test_verification.py",
            "tests/quality/test_contract.py",
        ),
        ("node", "--test", "tests/quality/markdown-policy.test.mjs"),
        (
            "npm",
            "exec",
            "--offline",
            "--",
            "openspec",
            "validate",
            "--all",
            "--strict",
            "--no-interactive",
        ),
        ("actionlint",),
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
            "tools",
            "--config",
            ".config/quality/native/vulture.toml",
        ),
        ("gitleaks", "git", "--platform", "gitlab", "--redact", "--no-banner", "."),
        ("lychee", "--config", LINK_POLICY, *link_mode, *peer_scope, *markdown),
        (sys.executable, "-m", "tools.release.metadata"),
        (sys.executable, "-m", "tools.quality.hard_coding"),
        (sys.executable, "-m", "tools.quality.repository"),
    )


def audit(*, online_links: bool = False, peer: str | None = None) -> None:
    """Execute every governance concern from one composition root."""
    commands = _commands(online_links=online_links, peer=peer)
    if peer is not None:
        print(
            f"Online links: selected peer {peer}; other declared repositories are network-unqualified."
        )
    for command in commands:
        try:
            completed = subprocess.run(command, cwd=ROOT, check=False)
        except OSError as error:
            raise GovernanceError(f"governance tool unavailable: {command[0]}") from error
        if completed.returncode:
            raise GovernanceError(f"governance check failed: {command[0]}")


def _command(*, online_links: bool = False, peer: str | None = None) -> None:
    """Run deterministic checks, optionally including external links."""
    audit(online_links=online_links, peer=peer)


def main(argv: Iterable[str] = ()) -> None:
    """Run repository governance through the shared parser stack."""
    try:
        App(default_command=_command, help=__doc__, result_action="return_value")(tuple(argv))
    except GovernanceError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])
