"""Shared fixtures for repository quality contracts."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, relative: str) -> ModuleType:
    """Load a repository module without changing import search paths."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checker() -> ModuleType:
    """Load the repository quality checker with its package owners."""
    load("tools", "tools/__init__.py")
    load("tools.quality", "tools/quality/__init__.py")
    return load("codex_responses_proxy_quality_checker", "tools/quality/repository.py")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run isolated fixture Git and fail with its diagnostic."""
    environment = os.environ | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    result = subprocess.run(
        ["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result


@contextmanager
def repository(files: tuple[str, ...], *, tracked: tuple[str, ...] | None = None) -> Iterator[Path]:
    """Yield one isolated Git fixture with explicit tracked ownership."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        git(root, "init", "-q", "--initial-branch=fixture-root")
        for relative in files:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n", encoding="utf-8")
        selected = files if tracked is None else tracked
        if selected:
            git(root, "add", "--", *selected)
        yield root


def quality_inventory(root: Path):
    """Compile the fixture's configured Python inventory."""
    return checker()._repository_inventory(root, ("src",), ("tests",))


def audit_source(source_text: str):
    """Audit one isolated Python owner and return its observed structure."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.py"
        source.write_text(source_text, encoding="utf-8")
        return checker().audit_paths(root, [source])
