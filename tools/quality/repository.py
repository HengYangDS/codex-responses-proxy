"""Audit the repository-owned Python quality scope and explicit contracts."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tokenize
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from cyclopts import App
from tools.quality.architecture import architecture_gaps
from tools.quality.commits import commit_subject_gaps
from tools.quality.decision_records import decision_record_gaps
from tools.quality.repository_state import worktree_fingerprint
from tools.quality.semantic_names import semantic_name_gaps

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".config/checks/architecture/policy.toml"
PROJECT = ROOT / "pyproject.toml"
_DEFINITION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_EVIDENCE_SPEC = Path("openspec/specs/evidence-layout/spec.md")
_EVIDENCE_TAXONOMY = re.compile(r"```toml evidence-taxonomy\n(?P<body>.*?)\n```", re.DOTALL)


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
        if relative.name == "__init__.py":
            continue
        if relative.match("test_*.py"):
            configured_tests.append(path)
        elif relative.name == "fixtures.py" or relative.name.endswith("_fixture.py"):
            continue
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


def _docstring_expressions(tree: ast.Module) -> Iterable[ast.Expr]:
    """Yield syntax nodes that carry module, class, or function docstrings."""

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, *_DEFINITION_TYPES))
            and ast.get_docstring(node, clean=False) is not None
        ):
            yield node.body[0]


def _effective_lines(path: Path, tree: ast.Module) -> int:
    """Count code lines while excluding comments, blanks, and docstring carriers."""

    lines = path.read_text(encoding="utf-8").splitlines()
    excluded: set[int] = set()
    for token in tokenize.tokenize(BytesIO(path.read_bytes()).readline):
        if token.type == tokenize.COMMENT:
            excluded.update(range(token.start[0], token.end[0] + 1))
    for expression in _docstring_expressions(tree):
        if expression.end_lineno is not None:
            excluded.update(range(expression.lineno, expression.end_lineno + 1))
    return sum(
        bool(line.strip()) and lineno not in excluded for lineno, line in enumerate(lines, 1)
    )


def _nesting_depth(node: ast.AST) -> int:
    """Return the deepest control-flow nesting below one syntax node."""

    control = (
        ast.AsyncFor,
        ast.AsyncWith,
        ast.For,
        ast.If,
        ast.Match,
        ast.Try,
        ast.TryStar,
        ast.While,
        ast.With,
    )

    def visit(current: ast.AST, depth: int) -> int:
        if current is not node and isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            return depth
        next_depth = depth + isinstance(current, control)
        return max(
            (visit(child, next_depth) for child in ast.iter_child_nodes(current)),
            default=next_depth,
        )

    return visit(node, 0)


def _function_structure(tree: ast.Module) -> tuple[int, int]:
    """Return the largest function ELOC and control-flow nesting depth."""

    metrics = [
        (node.end_lineno - node.lineno + 1, _nesting_depth(node))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno is not None
    ]
    return (
        max((lines for lines, _ in metrics), default=0),
        max((depth for _, depth in metrics), default=0),
    )


def _logical_statements(path: Path, tree: ast.Module) -> int:
    """Count non-docstring logical statements independently of formatter wrapping."""

    tokens = tokenize.tokenize(BytesIO(path.read_bytes()).readline)
    return sum(token.type == tokenize.NEWLINE for token in tokens) - sum(
        1 for _ in _docstring_expressions(tree)
    )


def _public_docstring_gaps(root: Path, path: Path, tree: ast.Module) -> list[str]:
    """Report undocumented module-level public definitions."""

    gaps = []
    for node in tree.body:
        if (
            not isinstance(node, _DEFINITION_TYPES)
            or node.name.startswith("_")
            or node.name == "main"
        ):
            continue
        if ast.get_docstring(node, clean=False) is None:
            gaps.append(
                "public_docstring_missing:"
                f"{path.relative_to(root).as_posix()}:{node.lineno}:{node.name}"
            )
    return gaps


def evidence_layout_gaps(root: Path = ROOT) -> list[str]:
    """Validate physical evidence roots against the canonical positive taxonomy."""

    evidence = root / "evidence"
    if not evidence.is_dir():
        return []
    specification = root / _EVIDENCE_SPEC
    try:
        text = specification.read_text(encoding="utf-8")
        match = _EVIDENCE_TAXONOMY.search(text)
        taxonomy = tomllib.loads(match.group("body")) if match else {}
        owned_roots = {
            Path(entry["root"]).name
            for entry in taxonomy.values()
            if isinstance(entry, dict)
            and isinstance(entry.get("root"), str)
            and isinstance(entry.get("meaning"), str)
            and Path(entry["root"]).parent == Path("evidence")
        }
    except (OSError, tomllib.TOMLDecodeError, TypeError):
        owned_roots = set()
    if not owned_roots:
        return ["evidence_taxonomy_unavailable:openspec/specs/evidence-layout/spec.md"]
    return [
        f"evidence_root_unowned:evidence/{path.name}"
        for path in sorted(evidence.iterdir())
        if path.is_dir() and not path.name.startswith(".") and path.name not in owned_roots
    ]


def audit_paths(
    root: Path,
    paths: Iterable[Path],
    *,
    module_public_definition_docstrings_required: bool = True,
) -> tuple[list[str], list[dict[str, object]]]:
    """Audit semantic contracts and report descriptive source metrics."""

    gaps: list[str] = []
    inventory: list[dict[str, object]] = []
    selected = sorted(set(paths))
    for path in selected:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(root).as_posix()
        logical = _logical_statements(path, tree)
        effective_lines = _effective_lines(path, tree)
        function_eloc, nesting_depth = _function_structure(tree)
        inventory.append(
            {
                "path": relative,
                "logical_statements": logical,
                "effective_lines": effective_lines,
                "max_function_lines": function_eloc,
                "max_nesting_depth": nesting_depth,
            }
        )
        if module_public_definition_docstrings_required and not relative.startswith("tests/"):
            gaps.extend(_public_docstring_gaps(root, path, tree))
    return sorted(gaps), inventory


def _string_list(policy: Mapping[str, Any], key: str, errors: list[str]) -> list[str]:
    value = policy.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        errors.append(f"quality_policy_{key}_must_be_nonempty_string_list")
        return []
    return value


def audit() -> dict[str, object]:
    """Return one deterministic quality report for CI and local verification."""

    policy = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    config = tomllib.loads(PROJECT.read_text(encoding="utf-8"))
    tool = config.get("tool", {})
    repository = tool.get("codex-responses-proxy", {})
    project = config.get("project", {})
    policy_errors: list[str] = []
    if not isinstance(project, dict) or project.get("requires-python") != ">=3.12":
        policy_errors.append("requires_python_must_be_3_12_without_upper_bound")
    hatch_version = tool.get("hatch", {}).get("version", {})
    if project.get("dynamic") != ["version"] or hatch_version.get("path") != "VERSION":
        policy_errors.append("version_source_must_remain_VERSION")
    if repository.get("distribution") != "native-executable" or "build-system" not in config:
        policy_errors.append("distribution_must_be_native_executable")
    if not isinstance(policy, dict):
        policy_errors.append("quality_policy_must_be_a_table")
        policy = {}
    source_roots = _string_list(policy, "source_roots", policy_errors)
    test_roots = _string_list(policy, "test_roots", policy_errors)
    repository_inventory = _repository_inventory(ROOT, source_roots, test_roots)
    gaps, inventory = audit_paths(
        ROOT,
        repository_inventory.paths,
        module_public_definition_docstrings_required=True,
    )
    configured_paths = {"source_roots": source_roots, "test_roots": test_roots}
    for key, values in configured_paths.items():
        for value in values:
            matches = ROOT.glob(value) if any(char in value for char in "*?[") else (ROOT / value,)
            if not any(path.exists() for path in matches):
                policy_errors.append(f"quality_policy_missing_path:{key}:{value}")
    all_gaps = sorted(
        [
            *policy_errors,
            *repository_inventory.gaps,
            *gaps,
            *architecture_gaps(ROOT, policy),
            *commit_subject_gaps(ROOT),
            *evidence_layout_gaps(ROOT),
            *decision_record_gaps(ROOT),
            *semantic_name_gaps(ROOT),
        ]
    )
    return {
        "ok": not all_gaps,
        "gaps": all_gaps,
        "policy_errors": sorted(policy_errors),
        "files": inventory,
        "configured_paths": configured_paths,
    }


def _command(*, fingerprint: bool = False) -> None:
    """Print an explicit fingerprint or audit the repository quietly."""

    if fingerprint:
        print(worktree_fingerprint(ROOT))
        return

    report = audit()
    if not report["ok"]:
        print(json.dumps(report, sort_keys=True))
        raise SystemExit(1)


def main(argv: Iterable[str] = ()) -> None:
    """Run the repository audit through the repository's single parser stack."""

    App(default_command=_command, help=__doc__, result_action="return_value")(tuple(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
