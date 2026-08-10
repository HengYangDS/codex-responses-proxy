"""Validate product package ownership and dependency direction."""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".config/checks/architecture/policy.toml"
_CONTROL_PLANE_IMPORTS = frozenset({"client_control_plane"})
_CONTROL_PLANE_LITERAL = re.compile(r"(?<![A-Za-z0-9])client-control-plane(?![A-Za-z0-9])")


def _package_edges(package: Path) -> dict[str, set[str]]:
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
                prefix = "codex_responses_proxy."
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


def _foreign_product_gaps(root: Path, package: Path) -> list[str]:
    gaps: list[str] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            elif isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            for module in modules:
                owner = module.split(".", 1)[0]
                if owner in _CONTROL_PLANE_IMPORTS:
                    gaps.append(
                        f"architecture_foreign_product_dependency:{relative}:"
                        f"{getattr(node, 'lineno', 0)}:{owner}"
                    )
        gaps.extend(
            f"architecture_foreign_product_literal:{relative}:{number}:client-control-plane"
            for number, line in enumerate(source.splitlines(), 1)
            if _CONTROL_PLANE_LITERAL.search(line)
        )
    return gaps


def _semantic_owner_gaps(root: Path, package: Path) -> list[str]:
    gaps: list[str] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if path.name == "__init__.py" and ast.get_docstring(tree, clean=False) is None:
            gaps.append(f"architecture_package_declaration_missing:{relative}")
        peer_modules: set[str] = set()
        peer_symbols: set[str] = set()
        current_package = path.parent.relative_to(package.parent).as_posix().replace("/", ".")
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == current_package:
                    peer_modules.update(alias.asname or alias.name for alias in node.names)
                elif node.module.startswith(f"{current_package}."):
                    for alias in node.names:
                        peer_symbols.add(alias.asname or alias.name)
                        if alias.name.startswith("_"):
                            gaps.append(
                                f"architecture_private_cross_module:{relative}:"
                                f"{node.lineno}:{alias.name}"
                            )
            elif isinstance(node, ast.Import):
                peer_modules.update(
                    alias.asname or alias.name.rsplit(".", 1)[-1]
                    for alias in node.names
                    if alias.name.startswith(f"{current_package}.")
                )
        gaps.extend(
            f"architecture_private_cross_module:{relative}:"
            f"{node.lineno}:{node.value.id}.{node.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in peer_modules
            and node.attr.startswith("_")
        )
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                if value.value.id in peer_modules:
                    gaps.append(
                        f"architecture_forwarding_alias:{relative}:"
                        f"{node.lineno}:{value.value.id}.{value.attr}"
                    )
            elif isinstance(value, ast.Name) and value.id in peer_symbols:
                gaps.append(f"architecture_forwarding_alias:{relative}:{node.lineno}:{value.id}")
    return gaps


def architecture_gaps(root: Path = ROOT, policy: Mapping[str, Any] | None = None) -> list[str]:
    """Enforce the declared semantic package topology."""

    policy = tomllib.loads(POLICY.read_text(encoding="utf-8")) if policy is None else policy
    package = root / "src" / "codex_responses_proxy"
    forbidden = frozenset(policy.get("forbidden_packages", ()))
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
        return sorted([*gaps, "architecture_package_missing:codex_responses_proxy"])
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
    gaps.extend(
        f"architecture_forbidden_package:{child.name}"
        for child in sorted(package.iterdir())
        if child.is_dir() and child.name in forbidden
    )
    for path in sorted(package.rglob("__init__.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        body = list(tree.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                body.pop(0)
        if body:
            gaps.append(f"architecture_init_behavior:{path.relative_to(root).as_posix()}")
    edges = _package_edges(package)
    for owner, targets in sorted(edges.items()):
        gaps.extend(
            f"architecture_disallowed_edge:{owner}->{target}"
            for target in sorted(targets - allowed_edges.get(owner, frozenset()))
        )
    gaps.extend(f"architecture_cycle:{','.join(cycle)}" for cycle in _dependency_cycles(edges))
    gaps.extend(_foreign_product_gaps(root, package))
    gaps.extend(_semantic_owner_gaps(root, package))
    return sorted(gaps)
