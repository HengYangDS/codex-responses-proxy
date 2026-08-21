"""Validate product package ownership and dependency direction."""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".config/checks/architecture/policy.toml"

_POLICY_FIELDS = frozenset(
    {
        "owner",
        "risk_model",
        "measurement",
        "false_positive_cost",
        "remediation",
        "review_condition",
        "source_roots",
        "test_roots",
        "package_root",
        "root_configuration_modules",
        "package_initializers",
        "allowed_package_edges",
    }
)


def _package_edges(package: Path, package_name: str) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    for path in sorted(package.rglob("*.py")) if package.is_dir() else ():
        relative = path.relative_to(package)
        if len(relative.parts) < 2:
            continue
        owner = relative.parts[0]
        edges.setdefault(owner, set())
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            elif isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            for module in modules:
                prefix = f"{package_name}."
                if module.startswith(prefix):
                    target = module.removeprefix(prefix).split(".", 1)[0]
                    if target != owner:
                        edges[owner].add(target)
    return edges


def _dependency_cycles(edges: Mapping[str, set[str]]) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    cycles: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in sorted(edges.get(node, ())):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in active:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            target = stack.pop()
            active.remove(target)
            component.append(target)
            if target == node:
                break
        if len(component) > 1:
            cycles.append(tuple(sorted(component)))

    for node in sorted(set(edges) | {target for targets in edges.values() for target in targets}):
        if node not in indices:
            visit(node)
    return sorted(cycles)


def _package_declaration_gaps(root: Path, package: Path) -> list[str]:
    gaps: list[str] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if path.name == "__init__.py" and ast.get_docstring(tree, clean=False) is None:
            gaps.append(f"architecture_package_declaration_missing:{relative}")
    return gaps


def _policy_gaps(policy: Mapping[str, Any]) -> list[str]:
    gaps = [f"architecture_policy_schema:{field}" for field in sorted(set(policy) ^ _POLICY_FIELDS)]
    for field in (
        "owner",
        "risk_model",
        "measurement",
        "false_positive_cost",
        "remediation",
        "review_condition",
        "package_root",
        "package_initializers",
    ):
        value = policy.get(field)
        if not isinstance(value, str) or not value.strip():
            gaps.append(f"architecture_policy_value:{field}")
    if policy.get("package_initializers") not in {
        "declarations-only",
        "ordinary-modules",
    }:
        gaps.append("architecture_policy_value:package_initializers")
    return gaps


def architecture_gaps(root: Path = ROOT, policy: Mapping[str, Any] | None = None) -> list[str]:
    """Enforce the declared semantic package topology."""

    policy = tomllib.loads(POLICY.read_text(encoding="utf-8")) if policy is None else policy
    policy_gaps = _policy_gaps(policy)
    if policy_gaps:
        return sorted(policy_gaps)
    package_root = str(policy["package_root"])
    package = root / package_root
    package_name = package.name
    package_initializers = str(policy["package_initializers"])
    root_modules = frozenset(policy.get("root_configuration_modules", ()))
    allowed_edges = {
        owner: frozenset(targets)
        for owner, targets in policy.get("allowed_package_edges", {}).items()
    }
    gaps = [
        f"architecture_root_implementation:{path.name}"
        for path in sorted(root.glob("*.py"))
        if path.name not in root_modules and (path.is_file() or path.is_symlink())
    ]
    if not package.is_dir():
        return sorted([*gaps, f"architecture_package_missing:{package_root}"])
    actual = {
        child.name
        for child in package.iterdir()
        if child.is_dir() and not child.name.startswith("__")
    }
    gaps.extend(
        f"architecture_undeclared_package:{name}" for name in sorted(actual - allowed_edges.keys())
    )
    gaps.extend(
        f"architecture_package_missing:{name}" for name in sorted(allowed_edges.keys() - actual)
    )
    if package_initializers == "declarations-only":
        for path in sorted(package.rglob("__init__.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            body = list(tree.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    body.pop(0)
            if body:
                gaps.append(f"architecture_init_behavior:{path.relative_to(root).as_posix()}")
    edges = _package_edges(package, package_name)
    for owner, targets in sorted(edges.items()):
        gaps.extend(
            f"architecture_disallowed_edge:{owner}->{target}"
            for target in sorted(targets - allowed_edges.get(owner, frozenset()))
        )
    gaps.extend(f"architecture_cycle:{','.join(cycle)}" for cycle in _dependency_cycles(edges))
    gaps.extend(_package_declaration_gaps(root, package))
    return sorted(gaps)
