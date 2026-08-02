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

ROOT = Path(__file__).resolve().parents[2]


def _quality_versions() -> dict[str, str]:
    """Read exact quality tool versions from their single repository owner."""
    return dict(
        line.split("==", maxsplit=1)
        for line in (ROOT / "tools" / "quality" / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )


def _load(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _checker() -> ModuleType:
    return _load("codex_responses_proxy_quality_checker", "tools/quality/repository.py")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    result = subprocess.run(
        ["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
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
            "codex_responses_proxy",
            "watchdog",
            "tools",
            "tests",
        ).stdout
        expected_untracked = sorted(
            path.decode() for path in untracked.split(b"\0") if path.endswith(b".py")
        )
        expected_gaps = []
        missing = sorted(
            path.decode()
            for path in _git(
                ROOT,
                "ls-files",
                "-z",
                "--deleted",
                "--",
                "*.py",
                "codex_responses_proxy",
                "watchdog",
                "tools",
                "tests",
            ).stdout.split(b"\0")
            if path.endswith(b".py")
        )
        if missing:
            expected_gaps.append(f"quality_inventory_missing:{','.join(missing)}")
        if expected_untracked:
            expected_gaps.append(f"quality_inventory_untracked:{','.join(expected_untracked)}")
        self.assertEqual(inventory_gaps, expected_gaps)
        self.assertGreater(len(report["files"]), 20)
        inventoried = {entry["path"] for entry in report["files"]}
        for path in (
            "codex_responses_proxy/commands/control.py",
            "codex_responses_proxy/supervision/watchdog.py",
            "tools/release/metadata.py",
            "tests/governance/test_repository.py",
        ):
            self.assertIn(path, inventoried)

    def test_current_product_architecture_is_acyclic_and_directional(self) -> None:
        self.assertEqual(_checker().architecture_gaps(ROOT), [])

    def test_architecture_gate_rejects_root_implementation_init_behavior_and_cycles(self) -> None:
        checker = _checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "control.py": "def main():\n    return 0\n",
                "codex_responses_proxy/__init__.py": "from .runtime import state\n",
                "codex_responses_proxy/common/value.py": "VALUE = 1\n",
                "codex_responses_proxy/listener/__init__.py": "",
                "codex_responses_proxy/listener/private.py": "_VALUE = 1\n",
                "codex_responses_proxy/listener/forward.py": (
                    "from codex_responses_proxy.listener import private\nPUBLIC = private._VALUE\n"
                ),
                "codex_responses_proxy/listener/direct.py": (
                    "from codex_responses_proxy.listener.private import _VALUE\nPUBLIC = _VALUE\n"
                ),
                "codex_responses_proxy/runtime/state.py": (
                    "from codex_responses_proxy.transport import relay\n"
                ),
                "codex_responses_proxy/transport/relay.py": (
                    "from codex_responses_proxy.runtime import state\n"
                ),
                "codex_responses_proxy/commands/install.py": (
                    "import aigw_cli\nCOMMAND = 'aigw sync'\n"
                ),
                "codex_dmx_proxy/legacy.py": "VALUE = 1\n",
                "watchdog/watchdog.py": "VALUE = 1\n",
            }
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

            gaps = checker.architecture_gaps(root)

        self.assertIn("architecture_root_implementation:control.py", gaps)
        self.assertIn("architecture_init_behavior:codex_responses_proxy/__init__.py", gaps)
        self.assertIn("architecture_forbidden_package:common", gaps)
        self.assertIn(
            "architecture_package_declaration_missing:codex_responses_proxy/listener/__init__.py",
            gaps,
        )
        self.assertIn(
            "architecture_private_cross_module:"
            "codex_responses_proxy/listener/forward.py:2:private._VALUE",
            gaps,
        )
        self.assertIn(
            "architecture_forwarding_alias:"
            "codex_responses_proxy/listener/forward.py:2:private._VALUE",
            gaps,
        )
        self.assertIn(
            "architecture_private_cross_module:codex_responses_proxy/listener/direct.py:1:_VALUE",
            gaps,
        )
        self.assertIn(
            "architecture_forwarding_alias:codex_responses_proxy/listener/direct.py:2:_VALUE",
            gaps,
        )
        self.assertIn("architecture_retired_module:codex_responses_proxy/runtime/state.py", gaps)
        self.assertIn("architecture_disallowed_edge:runtime->transport", gaps)
        self.assertIn("architecture_cycle:runtime,transport", gaps)
        self.assertIn("architecture_retired_source_root:codex_dmx_proxy", gaps)
        self.assertIn("architecture_retired_source_root:watchdog", gaps)
        self.assertIn(
            "architecture_foreign_product_dependency:"
            "codex_responses_proxy/commands/install.py:1:aigw_cli",
            gaps,
        )
        self.assertIn(
            "architecture_foreign_product_literal:codex_responses_proxy/commands/install.py:2:aigw",
            gaps,
        )

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

    def test_structural_limits_reject_large_or_deep_production_owners(self) -> None:
        cases = (
            (
                '"""Docs do not buy structural headroom."""\ndef compact():\n    return (\n        1\n        + 2\n        + 3\n    )\n',
                {"module_eloc_limit": 4},
                "module_eloc_exceeded:source.py:6>4",
            ),
            (
                "def long_owner():\n    value = 1\n    value += 1\n    return value\n",
                {"function_eloc_limit": 3},
                "function_eloc_exceeded:source.py:4>3",
            ),
            (
                "def nested(value):\n    if value:\n        for item in value:\n            if item:\n                return item\n",
                {"nesting_depth_limit": 2},
                "nesting_depth_exceeded:source.py:3>2",
            ),
        )
        for source, options, expected in cases:
            with self.subTest(expected=expected):
                gaps, _ = self.audit_source(source, **options)
                self.assertIn(expected, gaps)

    def test_structural_inventory_exposes_eloc_function_size_and_nesting(self) -> None:
        gaps, inventory = self.audit_source(
            "def owner(value):\n    if value:\n        return value\n    return None\n",
            module_eloc_limit=10,
            function_eloc_limit=10,
            nesting_depth_limit=2,
        )
        self.assertEqual(gaps, [])
        self.assertEqual(inventory[0]["effective_lines"], 4)
        self.assertEqual(inventory[0]["max_function_lines"], 4)
        self.assertEqual(inventory[0]["max_nesting_depth"], 1)

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
        self.assertTrue(checker._in_scope("tools/owner.py", ("tools/*.py",)))
        self.assertFalse(checker._in_scope("tools/nested/foreign.py", ("tools/*.py",)))

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

    def test_quality_inventory_accepts_semantic_fixture_carriers_only(self) -> None:
        files = (
            "src/current.py",
            "tests/test_current.py",
            "tests/__init__.py",
            "tests/runtime/fixtures.py",
            "tests/compatibility/replay_fixture.py",
            "tests/nested/helper.py",
        )
        with _test_repository(files) as root:
            inventory = _quality_inventory(root)
        self.assertEqual(
            inventory.gaps, ("quality_inventory_test_misnamed:tests/nested/helper.py",)
        )

    def test_branch_coverage_floor_is_enforced_independently(self) -> None:
        checker = _load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        cases = (
            (
                {"num_branches": 20, "covered_branches": 19},
                95,
                ["branch_coverage_not_strictly_above_floor:95.00<=95.00"],
            ),
            ({"num_branches": 200, "covered_branches": 191}, 95, []),
            (
                {"num_branches": 21, "covered_branches": 20},
                96,
                ["branch_coverage_not_strictly_above_floor:95.24<=96.00"],
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
        checker = _load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        cases = (
            (
                {"num_statements": 20, "covered_lines": 19},
                95,
                ["statement_coverage_not_strictly_above_floor:95.00<=95.00"],
            ),
            ({"num_statements": 200, "covered_lines": 191}, 95, []),
            (
                {"num_statements": 21, "covered_lines": 20},
                96,
                ["statement_coverage_not_strictly_above_floor:95.24<=96.00"],
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
        source = (ROOT / "tools" / "quality" / "tests.py").read_text(encoding="utf-8")
        self.assertIn("failures: list[tuple[str, str]]", source)
        self.assertIn("check=False", source)
        self.assertIn("canonical Python tests failed", source)

    def _runner(self) -> ModuleType:
        return _load("codex_responses_proxy_test_runner", "tools/quality/tests.py")

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
            self.assertIn("tests/quality/test_contract.py", configured)

    def test_runner_reads_sorted_tests_from_the_git_index_at_any_depth(self) -> None:
        files = (
            "tests/test_top.py",
            "tests/nested/test_deep.py",
            "tests/runtime/fixtures.py",
            "tests/compatibility/replay_fixture.py",
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
        with _test_repository(("tests/runtime/fixtures.py",)) as root:
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

    def test_runner_rejects_unhandled_tracebacks_warnings_and_error_banners(self) -> None:
        runner = self._runner()
        self.assertFalse(runner.abnormal_output(b"390 tests passed\n", b""))
        for output in (
            b"Traceback (most recent call last):\n",
            b"Exception ignored in: <function Resource.__del__>\n",
            b"Exception occurred during processing of request\n",
            b"ResourceWarning: unclosed response\n",
            b"module.py:1: UserWarning: visible warning\n",
            b"Warning: visible base warning\n",
            b"ERROR: visible error banner\n",
        ):
            with self.subTest(output=output):
                self.assertTrue(runner.abnormal_output(b"", output))

    def test_git_fixtures_do_not_inherit_host_hooks(self) -> None:
        with _test_repository(("src/current.py",)) as root:
            hooks = root / ".git" / "hooks"
            self.assertFalse((hooks / "pre-commit").exists())

    def test_runner_compile_inventory_isolated_from_the_checkout(self) -> None:
        runner = self._runner()
        self.assertIn("tests", runner.COMPILE_TARGETS)
        self.assertIn("codex_responses_proxy", runner.COMPILE_TARGETS)
        self.assertIn("sys.pycache_prefix", inspect.getsource(runner.compile_sources))

    def test_gitlab_quality_install_declares_the_container_root_policy(self) -> None:
        pipeline = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        self.assertIn("--root-user-action=ignore", pipeline)
        self.assertIn("DEBIAN_FRONTEND: noninteractive", pipeline)
        self.assertNotIn("apt-get install -y ", pipeline)

    def test_quality_runner_resolves_the_required_tool_beyond_a_foreign_venv(self) -> None:
        source = (ROOT / "tools" / "quality" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("resolve_versioned_tool", source)
        self.assertIn("for directory in $PATH", source)
        self.assertIn("quality_requirements=tools/quality/requirements.txt", source)
        self.assertIn("required_version()", source)
        self.assertIn('ruff_path=$(resolve_versioned_tool "$ruff" "ruff $ruff_version"', source)
        self.assertIn('ty_path=$(resolve_versioned_tool "$ty" "ty $ty_version"', source)
        self.assertIn("Coverage.py, version $coverage_required with C extension", source)

    @unittest.skipUnless(os.name == "posix", "models POSIX shell executable lookup")
    def test_quality_runner_skips_an_earlier_wrong_tool_version(self) -> None:
        versions = _quality_versions()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foreign, required = root / "foreign", root / "required"
            foreign.mkdir()
            required.mkdir()
            executables = {
                root
                / "python": f"if [ \"$1 $2 $3\" = '-m coverage --version' ]; then echo 'Coverage.py, version {versions['coverage']} with C extension'; elif [ \"$#\" = 1 ] && [ \"$1\" = '-' ]; then printf 'codex_responses_proxy\\ntests\\n'; fi",
                root
                / "ruff": f"[ \"${{1:-}}\" = --version ] && echo 'ruff {versions['ruff']}'; exit 0",
                foreign / "ty": "[ \"${1:-}\" = --version ] && echo 'ty 0.0.63'; exit 0",
                required
                / "ty": f"[ \"${{1:-}}\" = --version ] && echo 'ty {versions['ty']}'; exit 0",
            }
            for path, body in executables.items():
                path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
                path.chmod(0o755)
            completed = subprocess.run(
                ["sh", str(ROOT / "tools/quality/run.sh")],
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

    @unittest.skipUnless(os.name == "posix", "models POSIX shell executable lookup")
    def test_quality_runner_accepts_metadata_but_rejects_version_prefixes(self) -> None:
        versions = _quality_versions()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            misleading, required = root / "misleading", root / "required"
            misleading.mkdir()
            required.mkdir()
            executables = {
                root
                / "python": f"if [ \"$1 $2 $3\" = '-m coverage --version' ]; then echo 'Coverage.py, version {versions['coverage']} with C extension'; elif [ \"$#\" = 1 ] && [ \"$1\" = '-' ]; then printf 'codex_responses_proxy\\ntests\\n'; fi",
                root
                / "ruff": f"[ \"${{1:-}}\" = --version ] && echo 'ruff {versions['ruff']}'; exit 0",
                misleading
                / "ty": f"[ \"${{1:-}}\" = --version ] && echo 'ty {versions['ty']}0'; exit 0",
                required
                / "ty": f"[ \"${{1:-}}\" = --version ] && echo 'ty {versions['ty']} (stable build)'; exit 0",
            }
            for path, body in executables.items():
                path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
                path.chmod(0o755)
            completed = subprocess.run(
                ["sh", str(ROOT / "tools/quality/run.sh")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env=os.environ
                | {
                    "PATH": f"{misleading}:{required}:{os.environ['PATH']}",
                    "PYTHON": str(root / "python"),
                    "RUFF": str(root / "ruff"),
                    "TY": "ty",
                },
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
