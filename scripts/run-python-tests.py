#!/usr/bin/env python3
"""Run the canonical stdlib test inventory from ``pyproject.toml``."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pyproject.toml"


def configured_tests() -> list[str]:
    """Return the ordered canonical behavior-test inventory."""

    metadata = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    tests = metadata["tool"]["codex-dmx-proxy"]["quality"]["coverage-tests"]
    if not isinstance(tests, list) or not tests or not all(isinstance(path, str) for path in tests):
        raise ValueError("quality.coverage-tests must be a nonempty string list")
    if tests != sorted(set(tests)):
        raise ValueError("quality.coverage-tests must be unique and sorted")
    actual = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py"))
    if tests != actual:
        raise ValueError("quality.coverage-tests must match tests/test_*.py exactly")
    missing = [path for path in tests if not (ROOT / path).is_file()]
    if missing:
        raise ValueError("configured tests do not exist: " + ", ".join(missing))
    return tests


def command_for(test: str, *, coverage: bool, append: bool) -> list[str]:
    """Build one interpreter-bound test command."""

    if not coverage:
        return [sys.executable, test]
    command = [sys.executable, "-m", "coverage", "run", "--branch"]
    if append:
        command.append("--append")
    command.append(test)
    return command


def main() -> None:
    """Run every configured test and report all interpreter-bound failures."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", action="store_true", help="collect branch coverage")
    args = parser.parse_args()
    failures: list[tuple[str, int]] = []
    for index, test in enumerate(configured_tests()):
        print(f"==> {test}", flush=True)
        result = subprocess.run(
            command_for(test, coverage=args.coverage, append=args.coverage and index > 0),
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            failures.append((test, result.returncode))
    if failures:
        detail = ", ".join(f"{test}={code}" for test, code in failures)
        raise SystemExit(f"canonical Python tests failed: {detail}")


if __name__ == "__main__":
    main()
