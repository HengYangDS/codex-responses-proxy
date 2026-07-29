#!/usr/bin/env python3
"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "codex_dmx_quality_checker", ROOT / "scripts" / "check_quality.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/check_quality.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityPolicyContracts(unittest.TestCase):
    """Keep quality scope and ratchets executable rather than documentary."""

    def test_current_repository_policy_is_internally_consistent(self) -> None:
        report = _load_checker().audit()
        self.assertEqual(report["policy_errors"], [])
        self.assertGreater(len(report["files"]), 20)
        inventoried = {entry["path"] for entry in report["files"]}
        for path in (
            "control.py",
            "proxy/dmx_responses_proxy.py",
            "platform_adapters/common.py",
            "watchdog/watchdog.py",
            "scripts/check_release_metadata.py",
            "tests/test_repository_contracts.py",
        ):
            self.assertIn(path, inventoried)

    def test_tool_metadata_rejects_distribution_build_surfaces(self) -> None:
        import tomllib

        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        repository = metadata["tool"]["codex-dmx-proxy"]
        self.assertNotIn("project", metadata)
        self.assertNotIn("build-system", metadata)
        self.assertEqual(repository["supported-python"], ">=3.12")
        self.assertNotIn("python-requires", repository)
        self.assertEqual(repository["version-source"], "VERSION")
        self.assertEqual(repository["distribution-mode"], "runtime-file-payload")
        self.assertIs(repository["build-system-allowed"], False)
        self.assertNotIn("version", repository)

    def test_unratcheted_file_exceeding_hard_limit_fails(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proxy").mkdir()
            source = root / "proxy" / "too_large.py"
            source.write_text("\n".join(f"value_{index} = {index}" for index in range(4)))
            gaps, inventory = checker.audit_paths(
                root,
                [source],
                logic_limit=3,
                test_limit=5,
                ratchets={},
                module_public_definition_docstrings_required=False,
            )
        self.assertEqual(inventory[0]["logical_statements"], 4)
        self.assertIn("code_size_exceeded:proxy/too_large.py:4>3", gaps)

    def test_ratchet_is_an_exact_ceiling_not_a_free_allowance(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proxy").mkdir()
            source = root / "proxy" / "legacy.py"
            source.write_text("a = 1\nb = 2\nc = 3\n")
            gaps, _ = checker.audit_paths(
                root,
                [source],
                logic_limit=2,
                test_limit=5,
                ratchets={"proxy/legacy.py": 2},
                module_public_definition_docstrings_required=False,
            )
        expected = "code_size_ratchet_increased:proxy/legacy.py:3>2"
        self.assertIn(expected, gaps)
        report = {"ok": not gaps, "gaps": gaps}
        self.assertFalse(report["ok"])

    def test_quality_report_is_red_when_a_configured_ratchet_is_exceeded(self) -> None:
        checker = _load_checker()
        report = checker.audit()
        increases = [
            gap for gap in report["gaps"] if gap.startswith("code_size_ratchet_increased:")
        ]
        if increases:
            self.assertFalse(report["ok"])

    def test_logical_statement_metric_is_invariant_to_formatter_wrapping(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compact = root / "compact.py"
            wrapped = root / "wrapped.py"
            compact.write_text("value = call(first, second)\n", encoding="utf-8")
            wrapped.write_text("value = call(\n    first,\n    second,\n)\n", encoding="utf-8")
            compact_gaps, compact_inventory = checker.audit_paths(
                root,
                [compact],
                logic_limit=1,
                test_limit=1,
                ratchets={},
                module_public_definition_docstrings_required=False,
            )
            wrapped_gaps, wrapped_inventory = checker.audit_paths(
                root,
                [wrapped],
                logic_limit=1,
                test_limit=1,
                ratchets={},
                module_public_definition_docstrings_required=False,
            )
        self.assertEqual(compact_gaps, [])
        self.assertEqual(wrapped_gaps, [])
        self.assertEqual(compact_inventory[0]["logical_statements"], 1)
        self.assertEqual(wrapped_inventory[0]["logical_statements"], 1)

    def test_module_public_definition_docstring_switch_is_actually_enforced(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "runtime.py"
            source.write_text("def public_api():\n    return 1\n")
            gaps, _ = checker.audit_paths(
                root,
                [source],
                logic_limit=10,
                test_limit=10,
                ratchets={},
                module_public_definition_docstrings_required=True,
            )
        self.assertIn("public_docstring_missing:runtime.py:1:public_api", gaps)

    def test_coverage_inventory_is_unique_sorted_and_exact(self) -> None:
        report = _load_checker().audit()
        configured = report["configured_paths"]["coverage_tests"]
        actual = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py"))
        self.assertEqual(configured, sorted(set(configured)))
        self.assertEqual(configured, actual)


class TestRunnerContracts(unittest.TestCase):
    """Keep all behavior matrices and coverage on one ordered test inventory."""

    def test_runner_collects_all_failures_before_exiting(self) -> None:
        source = (ROOT / "scripts" / "run-python-tests.py").read_text(encoding="utf-8")
        self.assertIn("failures: list[tuple[str, int]]", source)
        self.assertIn("check=False", source)
        self.assertIn("canonical Python tests failed", source)

    def test_runner_inventory_tracks_every_test_file_exactly(self) -> None:
        configured = self._runner().configured_tests()
        actual = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py"))
        self.assertEqual(configured, actual)

    def _runner(self):
        spec = importlib.util.spec_from_file_location(
            "codex_dmx_test_runner_shared", ROOT / "scripts" / "run-python-tests.py"
        )
        if spec is None or spec.loader is None:
            self.fail("cannot load scripts/run-python-tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        return runner

    def test_runner_reads_the_canonical_inventory(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "codex_dmx_test_runner", ROOT / "scripts" / "run-python-tests.py"
        )
        if spec is None or spec.loader is None:
            self.fail("cannot load scripts/run-python-tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        configured = runner.configured_tests()
        policy = _load_checker().audit()["configured_paths"]["coverage_tests"]
        self.assertEqual(configured, policy)
        self.assertIn("tests/test_quality_contract.py", configured)

    def test_coverage_mode_uses_the_current_interpreter_and_append(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "codex_dmx_test_runner_commands", ROOT / "scripts" / "run-python-tests.py"
        )
        if spec is None or spec.loader is None:
            self.fail("cannot load scripts/run-python-tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        first = runner.command_for("tests/test_route_management.py", coverage=True, append=False)
        later = runner.command_for("tests/test_route_management.py", coverage=True, append=True)
        self.assertEqual(first[:5], [sys.executable, "-m", "coverage", "run", "--branch"])
        self.assertNotIn("--append", first)
        self.assertIn("--append", later)

    def test_behavior_mode_uses_the_current_interpreter_without_coverage(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "codex_dmx_plain_test_runner", ROOT / "scripts" / "run-python-tests.py"
        )
        if spec is None or spec.loader is None:
            self.fail("cannot load scripts/run-python-tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        command = runner.command_for("tests/test_route_management.py", coverage=False, append=False)
        self.assertEqual(command, [sys.executable, "tests/test_route_management.py"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
