"""Physical package contracts for terminal semantic ownership."""

from __future__ import annotations

from pathlib import Path

from tools.quality.architecture import architecture_gaps

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "codex_responses_proxy"
TERMINAL = {"cli", "protocol", "providers", "relay", "runtime", "service", "lifecycle"}


class TerminalPackageContracts:
    def test_only_terminal_production_packages_remain(self) -> None:
        actual = {
            path.name
            for path in PACKAGE_ROOT.iterdir()
            if path.is_dir() and not path.name.startswith("__")
        }
        assert actual == TERMINAL

    def test_dependency_edges_follow_terminal_direction(self) -> None:
        assert architecture_gaps(ROOT) == []

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
