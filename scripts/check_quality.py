#!/usr/bin/env python3
"""Audit the repository-owned Python quality scope and explicit contracts."""

from __future__ import annotations

import ast
import json
import tokenize
import tomllib
from collections.abc import Iterable, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pyproject.toml"
_DEFINITION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _paths_from_roots(root: Path, configured_roots: Iterable[str]) -> list[Path]:
    """Resolve configured files and directories into one deterministic Python inventory."""

    paths: set[Path] = set()
    for configured in configured_roots:
        path = root / configured
        if path.is_file() and path.suffix == ".py":
            paths.add(path)
        elif path.is_dir():
            paths.update(
                candidate
                for candidate in path.rglob("*.py")
                if "__pycache__" not in candidate.parts
            )
    return sorted(paths)


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
                f"public_docstring_missing:{path.relative_to(root)}:{node.lineno}:{node.name}"
            )
    return gaps


def audit_paths(
    root: Path,
    paths: Iterable[Path],
    *,
    logic_limit: int,
    test_limit: int,
    ratchets: Mapping[str, int],
    module_public_definition_docstrings_required: bool,
    docstring_paths: set[Path] | None = None,
) -> tuple[list[str], list[dict[str, object]]]:
    """Audit an explicit source inventory against hard limits and exact ratchets."""

    gaps: list[str] = []
    inventory: list[dict[str, object]] = []
    selected = sorted(set(paths))
    selected_relatives = {str(path.relative_to(root)) for path in selected}
    unknown_ratchets = sorted(set(ratchets) - selected_relatives)
    gaps.extend(f"unused_code_size_ratchet:{path}" for path in unknown_ratchets)
    for path in selected:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = str(path.relative_to(root))
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
        if module_public_definition_docstrings_required and (
            docstring_paths is None or path in docstring_paths
        ):
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
    if "project" in config or "build-system" in config:
        policy_errors.append("repository_must_not_pretend_to_be_a_python_distribution")
    if metadata.get("supported-python") != ">=3.12":
        policy_errors.append("supported_python_must_be_3_12_without_upper_bound")
    if "python-requires" in metadata:
        policy_errors.append("python_requires_is_distribution_metadata_not_a_tool_contract")
    if metadata.get("version-source") != "VERSION" or "version" in metadata:
        policy_errors.append("version_owner_must_remain_VERSION")
    if metadata.get("distribution-mode") != "runtime-file-payload":
        policy_errors.append("distribution_mode_must_be_runtime_file_payload")
    if metadata.get("build-system-allowed") is not False:
        policy_errors.append("build_system_must_remain_disallowed")
    if not isinstance(policy, dict):
        policy_errors.append("quality_policy_must_be_a_table")
        policy = {}
    logic_roots = _string_list(policy, "logic-roots", policy_errors)
    test_roots = _string_list(policy, "test-roots", policy_errors)
    docstring_roots = _string_list(
        policy, "module-public-definition-docstring-roots", policy_errors
    )
    type_roots = _string_list(policy, "type-roots", policy_errors)
    coverage_tests = _string_list(policy, "coverage-tests", policy_errors)
    logic_limit = policy.get("logic-max-statements")
    test_limit = policy.get("test-max-statements")
    if not isinstance(logic_limit, int) or isinstance(logic_limit, bool) or logic_limit <= 0:
        policy_errors.append("logic_max_statements_must_be_positive_integer")
        logic_limit = 0
    if not isinstance(test_limit, int) or isinstance(test_limit, bool) or test_limit <= 0:
        policy_errors.append("test_max_statements_must_be_positive_integer")
        test_limit = 0
    public_required = policy.get("module-public-definition-docstrings-required")
    if not isinstance(public_required, bool):
        policy_errors.append("module_public_definition_docstrings_required_must_be_boolean")
        public_required = False
    raw_ratchets = policy.get("ratchet", {})
    if not isinstance(raw_ratchets, dict) or any(
        not isinstance(path, str)
        or not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit <= 0
        for path, limit in getattr(raw_ratchets, "items", lambda: ())()
    ):
        policy_errors.append("quality_ratchets_must_map_paths_to_positive_integers")
        ratchets: dict[str, int] = {}
    else:
        ratchets = dict(raw_ratchets)
    source_paths = _paths_from_roots(ROOT, [*logic_roots, *test_roots])
    docstring_paths = set(_paths_from_roots(ROOT, docstring_roots))
    gaps, inventory = audit_paths(
        ROOT,
        source_paths,
        logic_limit=logic_limit,
        test_limit=test_limit,
        ratchets=ratchets,
        module_public_definition_docstrings_required=public_required,
        docstring_paths=docstring_paths,
    )
    configured_paths = {
        "logic_roots": logic_roots,
        "test_roots": test_roots,
        "module_public_definition_docstring_roots": docstring_roots,
        "type_roots": type_roots,
        "coverage_tests": coverage_tests,
    }
    for key, values in configured_paths.items():
        for value in values:
            if not (ROOT / value).exists():
                policy_errors.append(f"quality_policy_missing_path:{key}:{value}")
    actual_tests = sorted(
        str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py")
    )
    if coverage_tests != sorted(set(coverage_tests)):
        policy_errors.append("coverage_tests_must_be_unique_and_sorted")
    if coverage_tests != actual_tests:
        policy_errors.append("coverage_tests_must_match_tests_inventory_exactly")
    all_gaps = sorted([*policy_errors, *gaps])
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
