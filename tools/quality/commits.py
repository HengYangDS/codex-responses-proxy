"""Validate commit subjects against the repository-owned grammar."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path

from codex_responses_proxy.product_identity import environment_name

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".ethos/workspace.toml"


def commit_subject_pattern(policy: Mapping[str, object]) -> re.Pattern[str]:
    """Read the same subject expression consumed by native ETHOS hooks."""
    value = policy.get("subject_pattern")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("commit_policy_subject_pattern_invalid")
    return re.compile(value)


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


def _event_revisions(root: Path) -> tuple[str, ...] | None:
    """Validate explicit event objects independently of movable branch refs."""
    base = os.environ.get(environment_name("COMMIT_BASE"))
    head = os.environ.get(environment_name("COMMIT_HEAD"))
    if base is None and head is None:
        return None
    if (
        not base
        or not head
        or any(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None for value in (base, head))
    ):
        raise ValueError("commit_event_objects_invalid")
    actual = _git(root, "rev-parse", "HEAD")
    if actual.returncode or actual.stdout.strip() != head:
        raise ValueError("commit_event_head_mismatch")
    if set(base) == {"0"}:
        return (head,)
    if _git(root, "cat-file", "-e", f"{base}^{{commit}}").returncode:
        raise ValueError("commit_event_base_unavailable")
    if _git(root, "merge-base", "--is-ancestor", base, head).returncode:
        raise ValueError("commit_event_base_not_ancestor")
    return ("-1", head) if base == head else (f"{base}..{head}",)


def _subjects(root: Path) -> tuple[tuple[str, ...], str | None]:
    try:
        event = _event_revisions(root)
    except ValueError as error:
        return (), str(error)
    base = None if event is not None else _base_ref(root)
    args = ["log", "--format=%s"]
    if event is not None:
        args.extend(event)
    elif base is not None:
        tip = _git(root, "rev-parse", "HEAD").stdout.strip()
        base_tip = _git(root, "rev-parse", base).stdout.strip()
        args.extend(("-1", "HEAD") if tip == base_tip else (f"{base}..HEAD",))
    else:
        args.append("HEAD")
    result = _git(root, *args)
    if result.returncode:
        detail = result.stderr.strip() or str(result.returncode)
        return (), f"commit_history_unavailable:{detail}"
    return tuple(subject for subject in result.stdout.splitlines() if subject), None


def commit_subject_gaps(root: Path = ROOT) -> list[str]:
    """Report lane-local subjects not admitted by one positive grammar."""
    policy = tomllib.loads(POLICY.read_text(encoding="utf-8"))["commit_policy"]
    pattern = commit_subject_pattern(policy)
    subjects, error = _subjects(root)
    if error is not None:
        return [error]
    return [
        f"commit_subject_invalid:{subject}"
        for subject in subjects
        if not pattern.fullmatch(subject)
    ]
