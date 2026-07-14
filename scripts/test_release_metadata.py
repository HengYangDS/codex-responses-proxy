#!/usr/bin/env python3
"""Regression tests for release-history provenance enforcement."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_release_metadata.py"


def expect_rejection(text: str, description: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
        handle.write(text)
    try:
        completed = subprocess.run(
            [sys.executable, str(CHECKER), "--changelog", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            raise SystemExit(f"release metadata checker accepted {description}")
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    source = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    current_heading = f"## [{version}] - 2026-07-14"
    subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, check=True)
    expect_rejection(source.replace(current_heading, f"## [{version}] - 2000-01-01", 1), "the current tag/date mismatch")
    expect_rejection(source.replace(current_heading + "\n", "", 1), "the current reachable tag missing from the Changelog")
    expect_rejection(source.replace("## [1.0.4] - 2026-07-14", "## [1.0.4] - 2000-01-01", 1), "a tag/date mismatch")
    expect_rejection(source.replace("## [1.0.4] - 2026-07-14\n", "", 1), "a missing reachable tag")
    print("release metadata chronology contract: OK")


if __name__ == "__main__":
    main()
