#!/usr/bin/env python3
"""Contracts for repository-owned portability and ownership classification."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
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


class PortabilityContracts(unittest.TestCase):
    """Reject values decided by the wrong durable repository owner."""

    def test_scanner_classifies_personal_host_and_forge_bindings(self) -> None:
        scanner = _scanner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "product.py").write_text(
                'home = "/Users/alice/project"\n'
                'python = "/opt/homebrew/bin/python3.14"\n'
                'forge = "http://192.168.50.12/team/repository"\n'
                'actor = "alice@corp.invalid"\n',
                encoding="utf-8",
            )

            findings = scanner.audit(root, paths=("product.py",))

        self.assertEqual(
            {finding.rule for finding in findings},
            {"absolute-home", "package-manager-prefix", "private-network", "personal-identity"},
        )

    def test_scanner_keeps_only_immutable_records_out_of_product_scope(self) -> None:
        scanner = _scanner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "evidence/chronicle/receipt.md",
                "openspec/changes/archive/retired.md",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'fixture = "/Users/example/test"\nactor = "fixture@example.test"\n',
                    encoding="utf-8",
                )

            findings = scanner.audit(
                root,
                paths=(
                    "evidence/chronicle/receipt.md",
                    "openspec/changes/archive/retired.md",
                ),
            )

        self.assertEqual(findings, ())

    def test_scanner_keeps_bounded_data_heavy_fixtures_out_of_product_scope(self) -> None:
        scanner = _scanner()
        self.assertTrue(scanner._FIXTURE_FILES)
        self.assertTrue(all(path.startswith("tests/") for path in scanner._FIXTURE_FILES))

    def test_current_product_surfaces_have_no_wrong_owner_bindings(self) -> None:
        self.assertEqual(_scanner().audit(ROOT), ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
