#!/usr/bin/env python3
"""Emit secret-free evidence from live dual-Forge publication verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.release import publication  # noqa: E402


def parser() -> argparse.ArgumentParser:
    """Build the evidence-only publication verifier command line."""

    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--tag", required=True)
    command.add_argument("--gitlab-remote", required=True)
    command.add_argument("--gitlab-api-base", required=True)
    command.add_argument("--gitlab-repo", required=True)
    command.add_argument("--github-remote", required=True)
    command.add_argument("--github-repo", required=True)
    command.add_argument("--gitlab-anchor", type=Path, required=True)
    command.add_argument("--github-anchor", type=Path, required=True)
    command.add_argument(
        "--policy", type=Path, default=ROOT / "packaging/release/publication-policy.toml"
    )
    command.add_argument("--json", action="store_true", dest="as_json")
    return command


def verify(args: argparse.Namespace) -> dict[str, object]:
    """Run live verification and copy only displayable evidence."""

    authority = publication.verify(
        tag=args.tag,
        gitlab_remote=args.gitlab_remote,
        gitlab_api_base=args.gitlab_api_base,
        gitlab_repo=args.gitlab_repo,
        github_remote=args.github_remote,
        github_repo=args.github_repo,
        gitlab_anchor=args.gitlab_anchor,
        github_anchor=args.github_anchor,
        policy_path=args.policy,
    )
    return _plain(authority.evidence())


def _plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def main() -> None:
    args = parser().parse_args()
    try:
        result = verify(args)
    except publication.PublicationError as error:
        result = {
            "schema_version": 1,
            "tag": args.tag,
            "verified": False,
            "tree_equal": False,
            "reasons": [type(error).__name__],
            "forges": {},
        }
    if args.as_json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"publication proof: {'VERIFIED' if result['verified'] else 'UNVERIFIED'}")
    if not result["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
