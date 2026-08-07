"""Physical package contracts for terminal semantic ownership."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "codex_responses_proxy"
TERMINAL = {"cli", "protocol", "providers", "relay", "runtime", "service", "lifecycle"}
ALLOWED = {
    "cli": {"lifecycle", "service"},
    "lifecycle": {"service", "relay", "runtime", "protocol", "providers"},
    "service": {"relay", "runtime", "protocol", "providers"},
    "relay": {"runtime", "protocol", "providers"},
    "runtime": set(),
    "protocol": set(),
    "providers": set(),
}


def internal_edges() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0]
        if source.endswith(".py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            for module in modules:
                if module.startswith("codex_responses_proxy."):
                    target = module.split(".", 2)[1]
                    if target != source:
                        edges.add((source, target))
    return edges


class TerminalPackageContracts:
    def test_only_terminal_production_packages_remain(self) -> None:
        actual = {
            path.name
            for path in PACKAGE_ROOT.iterdir()
            if path.is_dir() and not path.name.startswith("__")
        }
        assert actual == TERMINAL

    def test_dependency_edges_follow_terminal_direction(self) -> None:
        forbidden = sorted(
            edge
            for edge in internal_edges()
            if edge[0] in TERMINAL and edge[1] not in ALLOWED[edge[0]]
        )
        assert forbidden == []

    def test_verified_native_artifact_has_one_semantic_owner(self) -> None:
        """The runtime transaction consumes an admitted artifact, never source checkout state."""

        lifecycle = PACKAGE_ROOT / "lifecycle"
        assert (lifecycle / "artifact.py").is_file()
        assert not (lifecycle / "source.py").exists()
        artifact = (lifecycle / "artifact.py").read_text(encoding="utf-8")
        installer = (lifecycle / "install.py").read_text(encoding="utf-8")
        assert "def admit(" in artifact
        for implementation_detail in ("tarfile", "ssh-keygen", "_verify_signature"):
            assert implementation_detail not in installer
