#!/usr/bin/env python3
"""Select ordinary or pending release metadata validation for trusted CI refs."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from check_release_metadata import (
    changelog_releases,
    known_release_versions,
    read_version,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_release_metadata.py"


def checker_arguments(
    version: str,
    released_versions: set[str],
    tagged_versions: set[str],
) -> list[str]:
    if version in released_versions and version not in tagged_versions:
        return ["--prepare-release"]
    return []


def main() -> None:
    version = read_version()
    released = {item for item, _date in changelog_releases()}
    tagged = set(known_release_versions())
    subprocess.run(
        [sys.executable, str(CHECKER), *checker_arguments(version, released, tagged)],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()