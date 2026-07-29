#!/usr/bin/env python3
"""Audit the repository-owned Python quality scope and explicit contracts."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tokenize
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pyproject.toml"
_DEFINITION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class RepositoryInventory:
    """Index-owned quality paths plus fail-closed checkout gaps."""

    paths: tuple[Path, ...]
    gaps: tuple[str, ...]


def _in_scope(relative: str, configured_roots: Iterable[str]) -> bool:
    """Return whether a repository-relative path belongs to a configured root."""

    path = PurePosixPath(relative)
    for configured in configured_roots:
        configured_path = PurePosixPath(configured)
        if any(char in configured for char in "*?["):
            if len(path.parts) == len(configured_path.parts) and path.match(configured):
                return True
        elif path == configured_path or (
            configured_path.suffix != ".py" and configured_path in path.parents
        ):
            return True
    return False


def _physical_python_paths(root: Path, configured_roots: Iterable[str]) -> set[str]:
    """Resolve configured files and directories into one checkout inventory."""

    paths: set[str] = set()
    for configured in configured_roots:
        matches = (
            sorted(root.glob(configured))
            if any(char in configured for char in "*?[")
            else [root / configured]
        )
        for path in matches:
            if path.suffix == ".py" and (path.is_file() or path.is_symlink()):
                paths.add(path.relative_to(root).as_posix())
            elif path.is_dir():
                paths.update(
                    candidate.relative_to(root).as_posix()
                    for candidate in path.rglob("*.py")
                    if "__pycache__" not in candidate.parts
                    and (candidate.is_file() or candidate.is_symlink())
                )
    return paths


def _index_entries(root: Path) -> tuple[dict[str, str], list[str]]:
    """Read stage-zero index modes without treating the working tree as ownership truth."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--stage", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return {}, [f"quality_inventory_git_unavailable:{exc}"]
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip() or str(result.returncode)
        return {}, [f"quality_inventory_git_failed:{detail}"]

    entries: dict[str, str] = {}
    unmerged: set[str] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, encoded_path = raw.split(b"\t", 1)
            mode, _, stage = metadata.split()
        except ValueError:
            return {}, ["quality_inventory_git_output_malformed"]
        path = os.fsdecode(encoded_path)
        if stage != b"0":
            unmerged.add(path)
        else:
            entries[path] = os.fsdecode(mode)
    return entries, (
        [f"quality_inventory_unmerged:{','.join(sorted(unmerged))}"] if unmerged else []
    )


def _has_symlink(root: Path, relative: str) -> bool:
    """Reject a file reached through a symlink at any repository-relative component."""

    path = PurePosixPath(relative)
    return any((root.joinpath(*parent.parts)).is_symlink() for parent in (path, *path.parents[:-1]))


def _repository_inventory(
    root: Path, source_roots: Iterable[str], test_roots: Iterable[str]
) -> RepositoryInventory:
    """Return index-owned regular Python files and fail-closed checkout gaps."""

    source_roots = tuple(source_roots)
    test_roots = tuple(test_roots)
    configured_roots = (*source_roots, *test_roots)
    entries, gaps = _index_entries(root)
    scoped_entries = {
        path: mode
        for path, mode in entries.items()
        if path.endswith(".py")
        and "__pycache__" not in PurePosixPath(path).parts
        and _in_scope(path, configured_roots)
    }
    physical = _physical_python_paths(root, configured_roots)
    tracked = set(scoped_entries)
    untracked = sorted(physical - tracked)
    missing = sorted(path for path in tracked if not (root / path).exists())
    symlinks = sorted(path for path in tracked | physical if _has_symlink(root, path))
    non_regular = sorted(
        path
        for path, mode in scoped_entries.items()
        if path not in symlinks
        and (
            mode not in {"100644", "100755"} or path not in missing and not (root / path).is_file()
        )
    )
    test_entries = sorted(path for path in tracked if _in_scope(path, test_roots))
    configured_tests: list[str] = []
    misnamed: list[str] = []
    for path in test_entries:
        relative = PurePosixPath(path)
        if relative.name == "__init__.py" or relative.parts[:2] == ("tests", "support"):
            continue
        if relative.match("test_*.py"):
            configured_tests.append(path)
        else:
            misnamed.append(path)
    for label, paths in (
        ("untracked", untracked),
        ("missing", missing),
        ("symlink", symlinks),
        ("non_regular", non_regular),
        ("test_misnamed", misnamed),
    ):
        if paths:
            gaps.append(f"quality_inventory_{label}:{','.join(paths)}")
    if not configured_tests:
        gaps.append("quality_inventory_test_empty")
    invalid = {*missing, *symlinks, *non_regular}
    paths = tuple(root / path for path in sorted(tracked - invalid))
    return RepositoryInventory(paths, tuple(sorted(gaps)))


def _logical_statements(path: Path, tree: ast.Module) -> int:
    """Count non-docstring logical statements independently of formatter wrapping."""

    tokens = tokenize.tokenize(BytesIO(path.read_bytes()).readline)
    logical_statements = sum(token.type == tokenize.NEWLINE for token in tokens)
    docstrings = 0
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings += 1
    return logical_statements - docstrings


def _public_docstring_gaps(root: Path, path: Path, tree: ast.Module) -> list[str]:
    """Report undocumented module-level public definitions."""

    gaps = []
    for node in tree.body:
        if not isinstance(node, _DEFINITION_TYPES):
            continue
        if node.name.startswith("_") or node.name == "main":
            continue
        if ast.get_docstring(node, clean=False) is None:
            gaps.append(
                "public_docstring_missing:"
                f"{path.relative_to(root).as_posix()}:{node.lineno}:{node.name}"
            )
    return gaps


def audit_paths(
    root: Path,
    paths: Iterable[Path],
    *,
    logic_limit: int,
    test_limit: int,
    ratchets: Mapping[str, int],
    module_public_definition_docstrings_required: bool = True,
) -> tuple[list[str], list[dict[str, object]]]:
    """Audit an explicit source inventory against hard limits and exact ratchets."""

    gaps: list[str] = []
    inventory: list[dict[str, object]] = []
    selected = sorted(set(paths))
    selected_relatives = {path.relative_to(root).as_posix() for path in selected}
    unknown_ratchets = sorted(set(ratchets) - selected_relatives)
    gaps.extend(f"unused_code_size_ratchet:{path}" for path in unknown_ratchets)
    for path in selected:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(root).as_posix()
        limit = test_limit if relative.startswith("tests/") else logic_limit
        logical = _logical_statements(path, tree)
        ratchet = ratchets.get(relative)
        inventory.append(
            {
                "path": relative,
                "logical_statements": logical,
                "hard_limit": limit,
                "ratchet": ratchet,
            }
        )
        if ratchet is not None:
            if ratchet <= limit:
                gaps.append(f"unnecessary_code_size_ratchet:{relative}:{ratchet}<={limit}")
            if logical > ratchet:
                gaps.append(f"code_size_ratchet_increased:{relative}:{logical}>{ratchet}")
        elif logical > limit:
            gaps.append(f"code_size_exceeded:{relative}:{logical}>{limit}")
        if module_public_definition_docstrings_required and not relative.startswith("tests/"):
            gaps.extend(_public_docstring_gaps(root, path, tree))
    return sorted(gaps), inventory


def _string_list(policy: Mapping[str, Any], key: str, errors: list[str]) -> list[str]:
    value = policy.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        errors.append(f"quality_policy_{key.replace('-', '_')}_must_be_nonempty_string_list")
        return []
    return value


def audit() -> dict[str, object]:
    """Return one deterministic quality report for CI and local verification."""

    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    tool = config.get("tool", {})
    metadata = tool.get("codex-dmx-proxy", {})
    policy = metadata.get("quality", {}) if isinstance(metadata, dict) else {}
    policy_errors: list[str] = []
    if metadata.get("requires-python") != ">=3.12":
        policy_errors.append("requires_python_must_be_3_12_without_upper_bound")
    if metadata.get("version-source") != "VERSION":
        policy_errors.append("version_source_must_remain_VERSION")
    if metadata.get("distribution") != "runtime-files" or "build-system" in config:
        policy_errors.append("distribution_must_remain_unbuilt_runtime_files")
    if not isinstance(policy, dict):
        policy_errors.append("quality_policy_must_be_a_table")
        policy = {}
    source_roots = _string_list(policy, "source-roots", policy_errors)
    test_roots = _string_list(policy, "test-roots", policy_errors)
    logic_limit = policy.get("logic-max-statements")
    test_limit = policy.get("test-max-statements")
    if not isinstance(logic_limit, int) or isinstance(logic_limit, bool) or logic_limit <= 0:
        policy_errors.append("logic_max_statements_must_be_positive_integer")
        logic_limit = 0
    if not isinstance(test_limit, int) or isinstance(test_limit, bool) or test_limit <= 0:
        policy_errors.append("test_max_statements_must_be_positive_integer")
        test_limit = 0
    raw_ratchets = policy.get("ratchet", {})
    if not isinstance(raw_ratchets, dict) or any(
        not isinstance(path, str)
        or not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit <= 0
        for path, limit in (raw_ratchets.items() if isinstance(raw_ratchets, dict) else ())
    ):
        policy_errors.append("quality_ratchets_must_map_paths_to_positive_integers")
        ratchets: dict[str, int] = {}
    else:
        ratchets = dict(raw_ratchets)
    repository_inventory = _repository_inventory(ROOT, source_roots, test_roots)
    gaps, inventory = audit_paths(
        ROOT,
        repository_inventory.paths,
        logic_limit=logic_limit,
        test_limit=test_limit,
        ratchets=ratchets,
        module_public_definition_docstrings_required=True,
    )
    configured_paths = {"source_roots": source_roots, "test_roots": test_roots}
    for key, values in configured_paths.items():
        for value in values:
            matches = ROOT.glob(value) if any(char in value for char in "*?[") else (ROOT / value,)
            if not any(path.exists() for path in matches):
                policy_errors.append(f"quality_policy_missing_path:{key}:{value}")
    all_gaps = sorted([*policy_errors, *repository_inventory.gaps, *gaps])
    return {
        "ok": not all_gaps,
        "gaps": all_gaps,
        "policy_errors": sorted(policy_errors),
        "files": inventory,
        "configured_paths": configured_paths,
    }


def main() -> None:
    """Print the quality report and fail when a repository contract is violated."""

    report = audit()
    print(json.dumps(report, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
