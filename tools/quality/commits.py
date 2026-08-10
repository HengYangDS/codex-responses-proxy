"""Validate commit subjects against the repository-owned grammar."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".config/checks/commits/policy.toml"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _base_ref(root: Path) -> str | None:
    """Select the first available integration base for this checkout."""

    for ref in ("candidate/dev", "origin/dev", "origin/main", "dev", "main"):
        result = _git(root, "merge-base", "--is-ancestor", ref, "HEAD")
        if result.returncode == 0:
            return ref
    return None


def _subjects(root: Path) -> tuple[tuple[str, ...], str | None]:
    base = _base_ref(root)
    args = ["log", "--format=%s"]
    if base is not None:
        args.append(f"{base}..HEAD")
    else:
        args.append("HEAD")
    result = _git(root, *args)
    if result.returncode:
        detail = result.stderr.strip() or str(result.returncode)
        return (), f"commit_history_unavailable:{detail}"
    return tuple(subject for subject in result.stdout.splitlines() if subject), None


def commit_subject_gaps(root: Path = ROOT) -> list[str]:
    """Report lane-local subjects not admitted by one positive grammar."""

    policy = tomllib.loads(POLICY.read_text(encoding="utf-8"))
    patterns = tuple(
        re.compile(pattern) for pattern in (policy["human_pattern"], *policy["generated_patterns"])
    )
    subjects, error = _subjects(root)
    if error is not None:
        return [error]
    return [
        f"commit_subject_invalid:{subject}"
        for subject in subjects
        if not any(pattern.fullmatch(subject) for pattern in patterns)
    ]
