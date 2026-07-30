#!/usr/bin/env python3
"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import importlib.util
import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, script: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scripts/{script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _checker() -> ModuleType:
    return _load("codex_dmx_quality_checker", "check_quality.py")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result


@contextmanager
def _test_repository(
    files: tuple[str, ...], *, tracked: tuple[str, ...] | None = None
) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _git(root, "init", "-q")
        for relative in files:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n", encoding="utf-8")
        selected = files if tracked is None else tracked
        if selected:
            _git(root, "add", "--", *selected)
        yield root


def _quality_inventory(root: Path):
    return _checker()._repository_inventory(root, ("src",), ("tests",))


class QualityPolicyContracts(unittest.TestCase):
    """Keep quality scope and ratchets executable rather than documentary."""

    def audit_source(self, source_text: str, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_text(source_text, encoding="utf-8")
            options = {
                "logic_limit": 10,
                "test_limit": 10,
                "ratchets": {},
                "module_public_definition_docstrings_required": False,
                **overrides,
            }
            return _checker().audit_paths(root, [source], **options)

    def test_current_repository_policy_is_internally_consistent(self) -> None:
        report = _checker().audit()
        self.assertEqual(report["policy_errors"], [])
        inventory_gaps = [gap for gap in report["gaps"] if gap.startswith("quality_inventory_")]
        untracked = _git(
            ROOT,
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
            "codex_dmx_proxy",
            "watchdog",
            "scripts",
            "tests",
        ).stdout
        expected_untracked = sorted(path.decode() for path in untracked.split(b"\0") if path)
        if expected_untracked:
            self.assertEqual(
                inventory_gaps,
                [f"quality_inventory_untracked:{','.join(expected_untracked)}"],
            )
        else:
            self.assertEqual(inventory_gaps, [])
        self.assertGreater(len(report["files"]), 20)
        inventoried = {entry["path"] for entry in report["files"]}
        for path in (
            "control.py",
            "watchdog/watchdog.py",
            "scripts/check_release_metadata.py",
            "tests/test_repository_contracts.py",
        ):
            self.assertIn(path, inventoried)

    def test_unratcheted_file_exceeding_hard_limit_fails(self) -> None:
        gaps, inventory = self.audit_source(
            "\n".join(f"value_{index} = {index}" for index in range(4)), logic_limit=3
        )
        self.assertEqual(inventory[0]["logical_statements"], 4)
        self.assertIn("code_size_exceeded:source.py:4>3", gaps)

    def test_ratchet_is_an_exact_ceiling_not_a_free_allowance(self) -> None:
        gaps, _ = self.audit_source(
            "a = 1\nb = 2\nc = 3\n", logic_limit=1, ratchets={"source.py": 2}
        )
        self.assertIn("code_size_ratchet_increased:source.py:3>2", gaps)
        self.assertTrue(gaps)

    def test_logical_statement_metric_is_invariant_to_formatter_wrapping(self) -> None:
        for source in ("value = call(first, second)\n", "value = call(\n first,\n second,\n)\n"):
            with self.subTest(source=source):
                gaps, inventory = self.audit_source(source, logic_limit=1, test_limit=1)
                self.assertEqual(gaps, [])
                self.assertEqual(inventory[0]["logical_statements"], 1)

    def test_module_public_definition_docstring_switch_is_actually_enforced(self) -> None:
        gaps, _ = self.audit_source(
            "def public_api():\n    return 1\n",
            module_public_definition_docstrings_required=True,
        )
        self.assertIn("public_docstring_missing:source.py:1:public_api", gaps)

    def test_coverage_floor_is_branch_aware_and_at_least_ninety_five_percent(self) -> None:
        import tomllib

        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        coverage = metadata["tool"]["coverage"]
        self.assertIs(coverage["run"]["branch"], True)
        self.assertGreaterEqual(coverage["report"]["fail_under"], 95)
        self.assertEqual(coverage["run"]["omit"], ["*/__init__.py"])

    def test_quality_inventory_uses_index_ownership_with_staged_add_and_delete(self) -> None:
        with _test_repository(("src/current.py", "tests/test_current.py")) as root:
            added = root / "src" / "added.py"
            added.write_text("pass\n", encoding="utf-8")
            _git(root, "add", "--", "src/added.py")
            (root / "src/current.py").unlink()
            _git(root, "add", "--", "src/current.py")
            inventory = _quality_inventory(root)
        self.assertEqual(inventory.gaps, ())
        self.assertEqual(
            [path.relative_to(root).as_posix() for path in inventory.paths],
            ["src/added.py", "tests/test_current.py"],
        )

    def test_quality_inventory_rejects_untracked_missing_and_out_of_scope_is_ignored(self) -> None:
        files = ("src/tracked.py", "tests/test_current.py", "outside/foreign.py")
        with _test_repository(files, tracked=files[1:]) as root:
            (root / "tests/test_current.py").unlink()
            inventory = _quality_inventory(root)
        self.assertEqual(inventory.paths, ())
        self.assertEqual(
            inventory.gaps,
            (
                "quality_inventory_missing:tests/test_current.py",
                "quality_inventory_untracked:src/tracked.py",
            ),
        )

    def test_quality_inventory_glob_does_not_expand_beyond_its_configured_depth(self) -> None:
        checker = _checker()
        self.assertTrue(checker._in_scope("owner.py", ("*.py",)))
        self.assertFalse(checker._in_scope("nested/foreign.py", ("*.py",)))
        self.assertTrue(checker._in_scope("scripts/owner.py", ("scripts/*.py",)))
        self.assertFalse(checker._in_scope("scripts/nested/foreign.py", ("scripts/*.py",)))

    def test_quality_inventory_rejects_symlink_misnamed_test_and_empty_tests(self) -> None:
        with _test_repository(("src/current.py", "tests/helper.py")) as root:
            target = root / "target.py"
            target.write_text("pass\n", encoding="utf-8")
            link = root / "src" / "link.py"
            link.symlink_to(target)
            _git(root, "add", "--", "src/link.py")
            inventory = _quality_inventory(root)
        self.assertEqual(
            inventory.gaps,
            (
                "quality_inventory_symlink:src/link.py",
                "quality_inventory_test_empty",
                "quality_inventory_test_misnamed:tests/helper.py",
            ),
        )

    def test_quality_inventory_accepts_only_explicit_test_support_boundary(self) -> None:
        files = (
            "src/current.py",
            "tests/test_current.py",
            "tests/__init__.py",
            "tests/support/helper.py",
            "tests/nested/helper.py",
        )
        with _test_repository(files) as root:
            inventory = _quality_inventory(root)
        self.assertEqual(
            inventory.gaps, ("quality_inventory_test_misnamed:tests/nested/helper.py",)
        )

    def test_branch_coverage_floor_is_enforced_independently(self) -> None:
        checker = _load("codex_dmx_branch_coverage", "check_branch_coverage.py")
        cases = (
            ({"num_branches": 20, "covered_branches": 19}, 95, []),
            (
                {"num_branches": 21, "covered_branches": 20},
                96,
                ["branch_coverage_below_floor:95.24<96.00"],
            ),
            (
                {"num_branches": 0, "covered_branches": 0},
                95,
                ["branch_coverage_requires_measured_branches"],
            ),
        )
        for totals, floor, expected in cases:
            with self.subTest(totals=totals):
                self.assertEqual(checker.branch_gaps(totals, floor), expected)

    def test_statement_coverage_floor_is_enforced_independently(self) -> None:
        checker = _load("codex_dmx_branch_coverage", "check_branch_coverage.py")
        cases = (
            ({"num_statements": 20, "covered_lines": 19}, 95, []),
            (
                {"num_statements": 21, "covered_lines": 20},
                96,
                ["statement_coverage_below_floor:95.24<96.00"],
            ),
            (
                {"num_statements": 0, "covered_lines": 0},
                95,
                ["statement_coverage_requires_measured_statements"],
            ),
        )
        for totals, floor, expected in cases:
            with self.subTest(totals=totals):
                self.assertEqual(checker.statement_gaps(totals, floor), expected)


class TestRunnerContracts(unittest.TestCase):
    """Keep all behavior matrices and coverage on one ordered test inventory."""

    def test_runner_collects_all_failures_before_exiting(self) -> None:
        source = (ROOT / "scripts" / "run-python-tests.py").read_text(encoding="utf-8")
        self.assertIn("failures: list[tuple[str, str]]", source)
        self.assertIn("check=False", source)
        self.assertIn("canonical Python tests failed", source)

    def _runner(self) -> ModuleType:
        return _load("codex_dmx_test_runner_shared", "run-python-tests.py")

    def test_current_checkout_inventory_is_complete_or_reports_untracked_construction(self) -> None:
        runner = self._runner()
        try:
            configured = runner.configured_tests()
        except RuntimeError as exc:
            untracked = _git(
                ROOT, "ls-files", "-z", "--others", "--exclude-standard", "--", "tests"
            ).stdout
            paths = sorted(
                path.decode()
                for path in untracked.split(b"\0")
                if path.endswith(b".py") and b"__pycache__" not in path.split(b"/")
            )
            self.assertTrue(paths)
            self.assertEqual(str(exc), f"test_inventory_untracked:{','.join(paths)}")
        else:
            self.assertIn("tests/test_quality_contract.py", configured)

    def test_runner_reads_sorted_tests_from_the_git_index_at_any_depth(self) -> None:
        files = (
            "tests/test_top.py",
            "tests/nested/test_deep.py",
            "tests/support/helper.py",
            "tests/support/nested/helper.py",
            "tests/other/__init__.py",
        )
        with _test_repository(files) as root:
            self.assertEqual(
                self._runner().configured_tests(root),
                ["tests/nested/test_deep.py", "tests/test_top.py"],
            )

    def test_runner_rejects_untracked_or_missing_python_files(self) -> None:
        files = ("tests/test_tracked.py", "tests/test_untracked.py")
        with _test_repository(files, tracked=files[:1]) as root:
            with self.assertRaisesRegex(RuntimeError, "test_inventory_untracked"):
                self._runner().configured_tests(root)
        with _test_repository(files[:1]) as root:
            (root / files[0]).unlink()
            with self.assertRaisesRegex(RuntimeError, "test_inventory_missing"):
                self._runner().configured_tests(root)

    def test_runner_rejects_misnamed_helpers_and_empty_inventory(self) -> None:
        with _test_repository(("tests/test_valid.py", "tests/helper.py")) as root:
            with self.assertRaisesRegex(RuntimeError, "test_inventory_misnamed:tests/helper.py"):
                self._runner().configured_tests(root)
        with _test_repository(("tests/support/helper.py",)) as root:
            with self.assertRaisesRegex(RuntimeError, "test_inventory_empty"):
                self._runner().configured_tests(root)

    def test_runner_rejects_symlinks(self) -> None:
        with _test_repository(()) as root:
            target = root / "fixture.py"
            target.write_text("pass\n", encoding="utf-8")
            link = root / "tests/test_link.py"
            link.parent.mkdir()
            link.symlink_to(target)
            _git(root, "add", "--", "tests/test_link.py")
            with self.assertRaisesRegex(RuntimeError, "test_inventory_symlink"):
                self._runner().configured_tests(root)

    def test_coverage_mode_uses_the_current_interpreter_and_append(self) -> None:
        runner = self._runner()
        first = runner.command_for("tests/test_route_management.py", coverage=True, append=False)
        later = runner.command_for("tests/test_route_management.py", coverage=True, append=True)
        self.assertEqual(first[:5], [sys.executable, "-m", "coverage", "run", "--branch"])
        self.assertNotIn("--append", first)
        self.assertIn("--append", later)

    def test_behavior_mode_uses_the_current_interpreter_without_coverage(self) -> None:
        runner = self._runner()
        command = runner.command_for("tests/test_route_management.py", coverage=False, append=False)
        self.assertEqual(command, [sys.executable, "tests/test_route_management.py"])

    def test_runner_rejects_unhandled_tracebacks_and_python_warnings(self) -> None:
        runner = self._runner()
        self.assertFalse(runner.abnormal_output(b"390 tests passed\n", b""))
        for output in (
            b"Traceback (most recent call last):\n",
            b"Exception ignored in: <function Resource.__del__>\n",
            b"Exception occurred during processing of request\n",
            b"ResourceWarning: unclosed response\n",
            b"module.py:1: UserWarning: visible warning\n",
            b"Warning: visible base warning\n",
        ):
            with self.subTest(output=output):
                self.assertTrue(runner.abnormal_output(b"", output))

    def test_runner_compile_inventory_isolated_from_the_checkout(self) -> None:
        runner = self._runner()
        self.assertIn("tests", runner.COMPILE_TARGETS)
        self.assertIn("codex_dmx_proxy", runner.COMPILE_TARGETS)
        self.assertIn("sys.pycache_prefix", inspect.getsource(runner.compile_sources))

    def test_gitlab_quality_install_declares_the_container_root_policy(self) -> None:
        pipeline = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        self.assertIn("--root-user-action=ignore", pipeline)
        self.assertIn("DEBIAN_FRONTEND: noninteractive", pipeline)
        self.assertNotIn("apt-get install -y ", pipeline)

    def test_quality_runner_resolves_the_required_tool_beyond_a_foreign_venv(self) -> None:
        source = (ROOT / "scripts" / "run-python-quality.sh").read_text(encoding="utf-8")
        self.assertIn("resolve_versioned_tool", source)
        self.assertIn("for directory in $PATH", source)
        self.assertIn('ruff_path=$(resolve_versioned_tool "$ruff" "ruff 0.16.0"', source)
        self.assertIn('ty_path=$(resolve_versioned_tool "$ty" "ty 0.0.64"', source)

    @unittest.skipUnless(os.name == "posix", "models POSIX shell executable lookup")
    def test_quality_runner_skips_an_earlier_wrong_tool_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foreign, required = root / "foreign", root / "required"
            foreign.mkdir()
            required.mkdir()
            executables = {
                root
                / "python": "if [ \"$1 $2 $3\" = '-m coverage --version' ]; then echo 'Coverage.py, version 7.13.5 with C extension'; elif [ \"$#\" = 1 ] && [ \"$1\" = '-' ]; then printf 'codex_dmx_proxy\\ntests\\n'; fi",
                root / "ruff": "[ \"${1:-}\" = --version ] && echo 'ruff 0.16.0'; exit 0",
                foreign / "ty": "[ \"${1:-}\" = --version ] && echo 'ty 0.0.63'; exit 0",
                required / "ty": "[ \"${1:-}\" = --version ] && echo 'ty 0.0.64'; exit 0",
            }
            for path, body in executables.items():
                path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
                path.chmod(0o755)
            completed = subprocess.run(
                ["sh", str(ROOT / "scripts/run-python-quality.sh")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env=os.environ
                | {
                    "PATH": f"{foreign}:{required}:{os.environ['PATH']}",
                    "PYTHON": str(root / "python"),
                    "RUFF": str(root / "ruff"),
                    "TY": "ty",
                },
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
