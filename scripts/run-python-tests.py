#!/usr/bin/env python3
"""Run the complete canonical stdlib behavior-test inventory."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def configured_tests(root: Path = ROOT) -> list[str]:
    """Return the index-owned test inventory after validating its checkout."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--", "tests"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"test_inventory_git_unavailable:{exc}") from exc
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip() or str(result.returncode)
        raise RuntimeError(f"test_inventory_git_failed:{detail}")

    tracked = {
        os.fsdecode(raw)
        for raw in result.stdout.split(b"\0")
        if raw and raw.endswith(b".py") and b"__pycache__" not in raw.split(b"/")
    }
    tests_root = root / "tests"
    physical_paths = tuple(tests_root.rglob("*.py"))
    physical = {
        path.relative_to(root).as_posix()
        for path in physical_paths
        if "__pycache__" not in path.parts and (path.is_file() or path.is_symlink())
    }
    symlinks = sorted(
        path.relative_to(root).as_posix()
        for path in tests_root.rglob("*")
        if "__pycache__" not in path.parts and path.is_symlink()
    )
    gaps = []
    for label, paths in (
        ("untracked", sorted(physical - tracked)),
        ("missing", sorted(tracked - physical)),
        ("symlink", symlinks),
    ):
        if paths:
            gaps.append(f"test_inventory_{label}:{','.join(paths)}")
    if gaps:
        raise RuntimeError(";".join(gaps))

    configured: list[str] = []
    misnamed: list[str] = []
    for path in sorted(tracked):
        relative = PurePosixPath(path)
        if relative.name == "__init__.py" or relative.parts[:2] == ("tests", "support"):
            continue
        if relative.match("test_*.py"):
            configured.append(path)
        else:
            misnamed.append(path)
    if misnamed:
        raise RuntimeError(f"test_inventory_misnamed:{','.join(misnamed)}")
    if not configured:
        raise RuntimeError("test_inventory_empty")
    return configured


def command_for(test: str, *, coverage: bool, append: bool) -> list[str]:
    """Build one interpreter-bound test command."""

    if not coverage:
        return [sys.executable, test]
    command = [sys.executable, "-m", "coverage", "run", "--branch"]
    if append:
        command.append("--append")
    return [*command, test]


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
