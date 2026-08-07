"""Validate semantic file-name grammars for repository-owned carriers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

_NATIVE_NAMES = frozenset({"AGENTS.md", "CHANGELOG.md", "CONTRIBUTING.md", "README.md"})
_OPEN_SPEC_CARRIERS = frozenset({"design.md", "proposal.md", "spec.md", "tasks.md"})
_HISTORICAL_ROOTS = (
    PurePosixPath("evidence/claims"),
    PurePosixPath("evidence/chronicle"),
    PurePosixPath("openspec/changes/archive"),
)
_GRAMMARS = {
    ".md": ("markdown", re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.md")),
    ".py": ("python", re.compile(r"(?:__[a-z0-9_]+__|[a-z][a-z0-9_]*)\.py")),
    ".sh": ("shell", re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.sh")),
}


def semantic_name_gaps(root: Path) -> list[str]:
    """Return tracked project files that violate their carrier's native grammar."""

    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    gaps: list[str] = []
    for encoded in output.split(b"\0"):
        if not encoded:
            continue
        relative = encoded.decode()
        path = PurePosixPath(relative)
        if any(root == path or root in path.parents for root in _HISTORICAL_ROOTS):
            continue
        name = path.name
        grammar = _GRAMMARS.get(PurePosixPath(name).suffix)
        if (
            grammar is None
            or name in _NATIVE_NAMES
            or name in _OPEN_SPEC_CARRIERS
            and PurePosixPath(relative).parts[0] == "openspec"
        ):
            continue
        label, pattern = grammar
        if pattern.fullmatch(name) is None:
            gaps.append(f"semantic_name_invalid:{label}:{relative}")
    return sorted(gaps)
