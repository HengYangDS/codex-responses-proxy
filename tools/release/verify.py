#!/usr/bin/env python3
"""Emit secret-free evidence from live dual-Forge publication verification."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from tools.release.publication import verification as publication


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    """Explicit dual-Forge verification inputs."""

    tag: str
    gitlab_remote: str
    gitlab_api_base: str
    gitlab_repo: str
    github_remote: str
    github_repo: str
    gitlab_anchor: Path
    github_anchor: Path
    policy: Path


def verify(request: VerificationRequest) -> dict[str, object]:
    """Run live verification and copy only displayable evidence."""

    evidence = publication.verify(
        tag=request.tag,
        gitlab_remote=request.gitlab_remote,
        gitlab_api_base=request.gitlab_api_base,
        gitlab_repo=request.gitlab_repo,
        github_remote=request.github_remote,
        github_repo=request.github_repo,
        gitlab_anchor=request.gitlab_anchor,
        github_anchor=request.github_anchor,
        policy_path=request.policy,
    )
    return _plain(evidence)


def _plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _command(
    *,
    tag: str,
    gitlab_remote: str,
    gitlab_api_base: str,
    gitlab_repo: str,
    github_remote: str,
    github_repo: str,
    gitlab_anchor: Path,
    github_anchor: Path,
    policy: Path,
    as_json: Annotated[bool, Parameter(name="--json", negative=False)] = False,
) -> None:
    """Verify one published tag without mutating either Forge."""

    request = VerificationRequest(
        tag,
        gitlab_remote,
        gitlab_api_base,
        gitlab_repo,
        github_remote,
        github_repo,
        gitlab_anchor,
        github_anchor,
        policy,
    )
    try:
        result = verify(request)
    except publication.PublicationError as error:
        result = {
            "schema_version": 1,
            "tag": tag,
            "verified": False,
            "tree_equal": False,
            "reasons": [type(error).__name__],
            "forges": {},
        }
    if as_json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"publication proof: {'VERIFIED' if result['verified'] else 'UNVERIFIED'}")
    if not result["verified"]:
        raise SystemExit(1)


def main(argv: tuple[str, ...] | None = None) -> None:
    """Run publication verification through the repository's single parser stack."""

    try:
        App(
            default_command=_command,
            help=__doc__,
            print_error=False,
            exit_on_error=False,
            result_action="return_value",
        )(tuple(sys.argv[1:] if argv is None else argv))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
