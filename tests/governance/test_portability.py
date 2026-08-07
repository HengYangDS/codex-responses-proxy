"""Contracts for repository-owned portability and ownership classification."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "codex_responses_proxy_portability", ROOT / "tools" / "quality" / "portability.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load tools/quality/portability.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PortabilityContracts:
    """Reject values decided by the wrong durable repository owner."""

    def test_scanner_classifies_personal_host_and_forge_bindings(self) -> None:
        scanner = _scanner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slash = "/"
            (root / "product.py").write_text(
                f'home = "{slash}Users{slash}alice{slash}project"\n'
                f'python = "{slash}opt{slash}homebrew{slash}bin{slash}python3.14"\n'
                f'forge = "http:{slash}{slash}{".".join(("192", "168", "50", "12"))}'
                f'{slash}team{slash}repository"\n'
                f'actor = "alice{"@"}corp.invalid"\n',
                encoding="utf-8",
            )

            findings = scanner.audit(root, paths=("product.py",))

        assert {finding.rule for finding in findings} == {
            "absolute-home",
            "package-manager-prefix",
            "private-network",
            "personal-identity",
        }

    def test_scanner_has_no_mutable_surface_allowlist(self) -> None:
        scanner = _scanner()
        assert not hasattr(scanner, "_FIXTURE_FILES")

    def test_scanner_classifies_current_product_not_historical_records(self) -> None:
        scanner = _scanner()
        current = "docs/operator-guide.md"
        historical = (
            "evidence/claims/release.toml",
            "evidence/chronicle/release/observation.md",
            "openspec/changes/archive/2026-08-07-release/specs/product/spec.md",
        )

        assert scanner._in_scope(current)
        assert all(not scanner._in_scope(path) for path in historical)

    def test_current_product_surfaces_have_no_wrong_owner_bindings(self) -> None:
        assert _scanner().audit(ROOT) == ()
