"""Validate the repository Decision Record register and file grammar."""

from __future__ import annotations

import re
from pathlib import Path

_DECISION_RECORD = re.compile(
    r"dr-(?P<sequence>[0-9]{4})-(?P<description>[a-z0-9]+(?:-[a-z0-9]+)*)\.md"
)
_DECISION_STATUSES = frozenset({"accepted", "amended", "deprecated", "proposed", "superseded"})


def decision_record_gaps(root: Path) -> list[str]:
    """Validate the one Decision Record register and its semantic file grammar."""

    directory = root / "docs/decisions"
    register = directory / "README.md"
    if not directory.is_dir() or not register.is_file():
        return ["decision_record_register_missing"]
    gaps: list[str] = []
    records: list[tuple[int, Path]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == "README.md":
            continue
        match = _DECISION_RECORD.fullmatch(path.name)
        if match is None:
            gaps.append(f"decision_record_name_invalid:{path.relative_to(root).as_posix()}")
            continue
        records.append((int(match.group("sequence")), path))
    sequences = [sequence for sequence, _ in records]
    if len(sequences) != len(set(sequences)):
        gaps.append("decision_record_sequence_duplicate")
    if sequences:
        missing = sorted(set(range(1, max(sequences) + 1)) - set(sequences))
        gaps.extend(f"decision_record_sequence_gap:{sequence:04d}" for sequence in missing)
    register_text = register.read_text(encoding="utf-8")
    required_sections = ("## Context", "## Decision", "## Consequences", "## Revisit Trigger")
    for sequence, path in records:
        text = path.read_text(encoding="utf-8")
        expected_title = f"# DR-{sequence:04d}: "
        if not text.startswith(expected_title):
            gaps.append(f"decision_record_title_invalid:{path.relative_to(root).as_posix()}")
        status = re.search(r"^- Status: ([a-z]+)$", text, re.MULTILINE)
        if status is None or status.group(1) not in _DECISION_STATUSES:
            gaps.append(f"decision_record_status_invalid:{path.relative_to(root).as_posix()}")
        if re.search(r"^- Date: [0-9]{4}-[0-9]{2}-[0-9]{2}$", text, re.MULTILINE) is None:
            gaps.append(f"decision_record_date_invalid:{path.relative_to(root).as_posix()}")
        for section in required_sections:
            if section not in text:
                gaps.append(
                    f"decision_record_section_missing:{path.relative_to(root).as_posix()}:{section[3:]}"
                )
        registrations = register_text.count(f"({path.name})")
        if registrations == 0:
            gaps.append(f"decision_record_unregistered:{path.relative_to(root).as_posix()}")
        elif registrations > 1:
            gaps.append(
                f"decision_record_registration_duplicate:{path.relative_to(root).as_posix()}"
            )
    return sorted(gaps)
