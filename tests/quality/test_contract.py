"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import tomllib
import tokenize
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

import pytest
from pytest_mock import MockerFixture

ROOT = Path(__file__).resolve().parents[2]


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


def _audit_source(source_text: str, **overrides: Any):
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


class TestQualityPolicyContracts:
    """Keep quality scope and ratchets executable rather than documentary."""

    def test_current_repository_policy_is_internally_consistent(self) -> None:
        report = _checker().audit()
        assert report["policy_errors"] == []
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
        assert inventory_gaps == expected_gaps
        assert len(report["files"]) > 20
        inventoried = {entry["path"] for entry in report["files"]}
        for path in (
            "src/codex_responses_proxy/lifecycle/control.py",
            "src/codex_responses_proxy/lifecycle/supervision/watchdog.py",
            "tools/release/metadata.py",
            "tests/governance/test_repository.py",
        ):
            assert path in inventoried

    def test_repository_cli_is_quiet_on_success_and_diagnostic_on_failure(
        self, mocker: MockerFixture
    ) -> None:
        checker = _checker()
        mocker.patch.object(checker, "audit", return_value={"ok": True, "gaps": []})
        output = mocker.patch("builtins.print")
        checker.main()
        output.assert_not_called()

        mocker.patch.object(
            checker, "audit", return_value={"ok": False, "gaps": ["invalid_contract"]}
        )
        output.reset_mock()
        with pytest.raises(SystemExit):
            checker.main()
        output.assert_called_once()

    def test_worktree_fingerprint_is_stable_and_content_sensitive(self) -> None:
        checker = _checker()
        with _test_repository(("tracked.txt",)) as root:
            untracked = root / "untracked.txt"
            untracked.write_text("first\n", encoding="utf-8")

            initial = checker.worktree_fingerprint(root)
            assert checker.worktree_fingerprint(root) == initial

            (root / "tracked.txt").write_text("changed\n", encoding="utf-8")
            tracked_changed = checker.worktree_fingerprint(root)
            assert tracked_changed != initial

            untracked.write_text("second\n", encoding="utf-8")
            untracked_changed = checker.worktree_fingerprint(root)
            assert untracked_changed != tracked_changed

            if os.name != "nt":
                (root / "tracked.txt").chmod(0o755)
                assert checker.worktree_fingerprint(root) != untracked_changed

    def test_worktree_fingerprint_is_path_sensitive_and_ignores_git_internals(self) -> None:
        checker = _checker()
        with _test_repository(("first.txt",)) as root:
            before = checker.worktree_fingerprint(root)
            (root / "first.txt").rename(root / "second.txt")
            renamed = checker.worktree_fingerprint(root)
            assert renamed != before

            (root / ".git" / "irrelevant").write_text("internal\n", encoding="utf-8")
            assert checker.worktree_fingerprint(root) == renamed

    def test_current_product_architecture_is_acyclic_and_directional(self) -> None:
        assert _checker().architecture_gaps(ROOT) == []

    def test_cli_is_the_only_production_command_composition_root(self) -> None:
        package = ROOT / "src/codex_responses_proxy"
        argparse_owners = []
        module_entrypoints = []
        shebangs = []
        for path in sorted(package.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
            if source.startswith("#!"):
                shebangs.append(relative)
            if any(
                (
                    isinstance(node, ast.Import)
                    and any(alias.name == "argparse" for alias in node.names)
                )
                or (isinstance(node, ast.ImportFrom) and node.module == "argparse")
                for node in tree.body
            ):
                argparse_owners.append(relative)
            if any(
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and ast.unparse(node.test) == "__name__ == '__main__'"
                for node in tree.body
            ):
                module_entrypoints.append(relative)

        assert argparse_owners == ["src/codex_responses_proxy/cli/application.py"]
        assert module_entrypoints == []
        assert shebangs == []
        assert (
            (package / "cli/__main__.py")
            .read_text(encoding="utf-8")
            .endswith("raise SystemExit(main())\n")
        )

    def test_lifecycle_tests_follow_lifecycle_ownership(self) -> None:
        tests = ROOT / "tests"
        assert [
            name for name in ("deployment", "payload", "supervision") if (tests / name).exists()
        ] == []
        assert (tests / "lifecycle/fixtures.py").is_file()
        assert (tests / "lifecycle/supervision/test_process.py").is_file()
        assert (tests / "service/test_identity.py").is_file()

    def test_service_tests_follow_runtime_and_deployment_ownership(self) -> None:
        tests = ROOT / "tests"
        assert [name for name in ("listener", "runtime") if (tests / name).exists()] == []
        assert (tests / "relay/proxy_fixture.py").is_file()
        assert (tests / "service/test_entrypoint.py").is_file()
        assert (tests / "service/handoff/test_runtime.py").is_file()
        assert (tests / "lifecycle/deployment/test_handoff.py").is_file()

    def test_protocol_and_relay_tests_follow_terminal_ownership(self) -> None:
        tests = ROOT / "tests"
        assert [
            name for name in ("compatibility", "transport", "recovery") if (tests / name).exists()
        ] == []
        assert (tests / "protocol/test_request.py").is_file()
        assert (tests / "protocol/test_response.py").is_file()
        assert (tests / "protocol/test_input_variant.py").is_file()
        assert (tests / "relay/test_empty_response.py").is_file()
        assert (tests / "relay/test_routes.py").is_file()
        for retired in tests.joinpath("providers").glob("test_portable_*.py"):
            raise AssertionError(f"protocol test remains under providers: {retired.name}")

    def test_product_and_tests_never_mutate_import_resolution_or_suppress_analysis(self) -> None:
        offenders = []
        for root in (ROOT / "tests",):
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                if any(
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "sys"
                    and node.attr == "path"
                    for node in ast.walk(tree)
                ):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:sys.path")
                comments = (
                    token.string
                    for token in tokenize.generate_tokens(io.StringIO(source).readline)
                    if token.type == tokenize.COMMENT
                )
                if any("noqa" in comment or "type: ignore" in comment for comment in comments):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:suppression")
        assert offenders == []

    def test_architecture_gate_rejects_root_implementation_init_behavior_and_cycles(self) -> None:
        checker = _checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "control.py": "def main():\n    return 0\n",
                "src/codex_responses_proxy/__init__.py": "from .runtime import state\n",
                "src/codex_responses_proxy/common/value.py": "VALUE = 1\n",
                "src/codex_responses_proxy/service/__init__.py": "",
                "src/codex_responses_proxy/service/private.py": "_VALUE = 1\n",
                "src/codex_responses_proxy/service/forward.py": (
                    "from codex_responses_proxy.service import private\nPUBLIC = private._VALUE\n"
                ),
                "src/codex_responses_proxy/service/direct.py": (
                    "from codex_responses_proxy.service.private import _VALUE\nPUBLIC = _VALUE\n"
                ),
                "src/codex_responses_proxy/runtime/state.py": (
                    "from codex_responses_proxy.relay import relay\n"
                ),
                "src/codex_responses_proxy/relay/relay.py": (
                    "from codex_responses_proxy.runtime import state\n"
                ),
                "src/codex_responses_proxy/lifecycle/install.py": (
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

        assert "architecture_root_implementation:control.py" in gaps
        assert "architecture_init_behavior:src/codex_responses_proxy/__init__.py" in gaps
        assert "architecture_forbidden_package:common" in gaps
        assert (
            "architecture_package_declaration_missing:src/codex_responses_proxy/service/__init__.py"
            in gaps
        )
        assert (
            "architecture_private_cross_module:"
            "src/codex_responses_proxy/service/forward.py:2:private._VALUE" in gaps
        )
        assert (
            "architecture_forwarding_alias:"
            "src/codex_responses_proxy/service/forward.py:2:private._VALUE" in gaps
        )
        assert (
            "architecture_private_cross_module:src/codex_responses_proxy/service/direct.py:1:_VALUE"
            in gaps
        )
        assert (
            "architecture_forwarding_alias:src/codex_responses_proxy/service/direct.py:2:_VALUE"
            in gaps
        )
        assert "architecture_retired_module:src/codex_responses_proxy/runtime/state.py" in gaps
        assert "architecture_disallowed_edge:relay->runtime" in gaps
        assert "architecture_disallowed_edge:runtime->relay" in gaps
        assert "architecture_cycle:relay,runtime" in gaps
        assert "architecture_retired_source_root:codex_dmx_proxy" in gaps
        assert "architecture_retired_source_root:watchdog" in gaps
        assert (
            "architecture_foreign_product_dependency:"
            "src/codex_responses_proxy/lifecycle/install.py:1:aigw_cli" in gaps
        )
        assert (
            "architecture_foreign_product_literal:src/codex_responses_proxy/lifecycle/install.py:2:aigw"
            in gaps
        )

    def test_unratcheted_file_exceeding_hard_limit_fails(self) -> None:
        gaps, inventory = _audit_source(
            "\n".join(f"value_{index} = {index}" for index in range(4)), logic_limit=3
        )
        assert inventory[0]["logical_statements"] == 4
        assert "code_size_exceeded:source.py:4>3" in gaps

    def test_ratchet_is_an_exact_ceiling_not_a_free_allowance(self) -> None:
        gaps, _ = _audit_source("a = 1\nb = 2\nc = 3\n", logic_limit=1, ratchets={"source.py": 2})
        assert "code_size_ratchet_increased:source.py:3>2" in gaps
        assert gaps

    @pytest.mark.parametrize(
        "source",
        ("value = call(first, second)\n", "value = call(\n first,\n second,\n)\n"),
    )
    def test_logical_statement_metric_is_invariant_to_formatter_wrapping(self, source: str) -> None:
        gaps, inventory = _audit_source(source, logic_limit=1, test_limit=1)
        assert gaps == []
        assert inventory[0]["logical_statements"] == 1

    def test_module_public_definition_docstring_switch_is_actually_enforced(self) -> None:
        gaps, _ = _audit_source(
            "def public_api():\n    return 1\n",
            module_public_definition_docstrings_required=True,
        )
        assert "public_docstring_missing:source.py:1:public_api" in gaps

    @pytest.mark.parametrize(
        ("source", "options", "expected"),
        (
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
        ),
    )
    def test_structural_limits_reject_large_or_deep_production_owners(
        self, source: str, options: dict[str, int], expected: str
    ) -> None:
        gaps, _ = _audit_source(source, **options)
        assert expected in gaps

    def test_structural_inventory_exposes_eloc_function_size_and_nesting(self) -> None:
        gaps, inventory = _audit_source(
            "def owner(value):\n    if value:\n        return value\n    return None\n",
            module_eloc_limit=10,
            function_eloc_limit=10,
            nesting_depth_limit=2,
        )
        assert gaps == []
        assert inventory[0]["effective_lines"] == 4
        assert inventory[0]["max_function_lines"] == 4
        assert inventory[0]["max_nesting_depth"] == 1

    def test_coverage_floor_is_branch_aware_and_at_least_ninety_five_percent(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        coverage = metadata["tool"]["coverage"]
        assert coverage["run"]["branch"] is True
        assert coverage["run"]["source_pkgs"] == ["codex_responses_proxy"]
        assert "disable_warnings" not in coverage["run"]
        assert coverage["report"]["fail_under"] >= 95
        assert coverage["run"]["omit"] == ["*/__init__.py"]

    def test_repository_has_standard_package_metadata_and_one_version_owner(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]
        assert project["name"] == "codex-responses-proxy"
        assert project["requires-python"] == ">=3.12"
        assert project["dynamic"] == ["version"]
        assert project["scripts"] == {
            "codex-responses-proxy": "codex_responses_proxy.cli.application:main"
        }
        assert metadata["build-system"]["build-backend"] == "hatchling.build"
        assert metadata["tool"]["hatch"]["version"]["path"] == "VERSION"
        assert "setuptools" not in metadata["tool"]
        assert "requires-python" not in metadata["tool"]["codex-responses-proxy"]
        assert "version-source" not in metadata["tool"]["codex-responses-proxy"]

    def test_quality_inventory_uses_index_ownership_with_staged_add_and_delete(self) -> None:
        with _test_repository(("src/current.py", "tests/test_current.py")) as root:
            added = root / "src" / "added.py"
            added.write_text("pass\n", encoding="utf-8")
            _git(root, "add", "--", "src/added.py")
            (root / "src/current.py").unlink()
            _git(root, "add", "--", "src/current.py")
            inventory = _quality_inventory(root)
        assert inventory.gaps == ()
        assert [path.relative_to(root).as_posix() for path in inventory.paths] == [
            "src/added.py",
            "tests/test_current.py",
        ]

    def test_quality_inventory_rejects_untracked_missing_and_out_of_scope_is_ignored(self) -> None:
        files = ("src/tracked.py", "tests/test_current.py", "outside/foreign.py")
        with _test_repository(files, tracked=files[1:]) as root:
            (root / "tests/test_current.py").unlink()
            inventory = _quality_inventory(root)
        assert inventory.paths == ()
        assert inventory.gaps == (
            "quality_inventory_missing:tests/test_current.py",
            "quality_inventory_untracked:src/tracked.py",
        )

    def test_quality_inventory_glob_does_not_expand_beyond_its_configured_depth(self) -> None:
        checker = _checker()
        assert checker._in_scope("owner.py", ("*.py",))
        assert not checker._in_scope("nested/foreign.py", ("*.py",))
        assert checker._in_scope("tools/owner.py", ("tools/*.py",))
        assert not checker._in_scope("tools/nested/foreign.py", ("tools/*.py",))

    def test_quality_inventory_rejects_symlink_misnamed_test_and_empty_tests(self) -> None:
        with _test_repository(("src/current.py", "tests/helper.py")) as root:
            target = root / "target.py"
            target.write_text("pass\n", encoding="utf-8")
            link = root / "src" / "link.py"
            link.symlink_to(target)
            _git(root, "add", "--", "src/link.py")
            inventory = _quality_inventory(root)
        assert inventory.gaps == (
            "quality_inventory_symlink:src/link.py",
            "quality_inventory_test_empty",
            "quality_inventory_test_misnamed:tests/helper.py",
        )

    def test_quality_inventory_accepts_semantic_fixture_carriers_only(self) -> None:
        files = (
            "src/current.py",
            "tests/test_current.py",
            "tests/__init__.py",
            "tests/service/fixtures.py",
            "tests/protocol/replay_fixture.py",
            "tests/nested/helper.py",
        )
        with _test_repository(files) as root:
            inventory = _quality_inventory(root)
        assert inventory.gaps == ("quality_inventory_test_misnamed:tests/nested/helper.py",)

    @pytest.mark.parametrize(
        ("totals", "floor", "expected"),
        (
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
        ),
    )
    def test_branch_coverage_floor_is_enforced_independently(
        self, totals: dict[str, int], floor: int, expected: list[str]
    ) -> None:
        checker = _load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        assert checker.branch_gaps(totals, floor) == expected

    @pytest.mark.parametrize(
        ("totals", "floor", "expected"),
        (
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
        ),
    )
    def test_statement_coverage_floor_is_enforced_independently(
        self, totals: dict[str, int], floor: int, expected: list[str]
    ) -> None:
        checker = _load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        assert checker.statement_gaps(totals, floor) == expected


class TestVerificationContracts:
    """Keep verification on mature tools and the released product artifact."""

    def test_pytest_is_the_only_behavior_test_runner(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert "pytest==9.1.1" in metadata["dependency-groups"]["quality"]
        assert "pytest-mock==3.15.1" in metadata["dependency-groups"]["quality"]
        assert metadata["tool"]["pytest"]["ini_options"] == {
            "addopts": ["--import-mode=importlib", "--strict-config", "--strict-markers"],
            "filterwarnings": ["error"],
            "markers": ["native_distribution: requires the self-contained released executable"],
            "python_classes": ["Test*", "*Tests", "*Contracts"],
            "testpaths": ["tests"],
        }
        assert not (ROOT / "tools" / "quality" / "tests.py").exists()
        direct_test_commands = []
        for relative in (
            ".gitlab-ci.yml",
            ".github/workflows/verify.yml",
            "noxfile.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for lineno, line in enumerate(source.splitlines(), 1):
                if "python tests/" in line or '"-m", "tests.' in line:
                    direct_test_commands.append(f"{relative}:{lineno}:{line.strip()}")
        assert direct_test_commands == []
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        metadata_job = gitlab.split("verify-release-metadata:", 1)[1].split(
            "verify-release-tag:", 1
        )[0]
        assert "uv==0.12.1" in metadata_job
        assert "uv sync --locked --only-group quality" in metadata_job
        assert "uv run --locked --no-sync pytest -q tests/release/test_metadata.py" in metadata_job

    def test_test_suite_has_no_unittest_compatibility_surface(self) -> None:
        offenders = []
        for path in sorted((ROOT / "tests").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name == "unittest" or alias.name.startswith("unittest.")
                    for alias in node.names
                ):
                    offenders.append(f"{relative}:{node.lineno}:unittest_import")
                elif isinstance(node, ast.ImportFrom) and (
                    node.module == "unittest"
                    or (node.module is not None and node.module.startswith("unittest."))
                ):
                    offenders.append(f"{relative}:{node.lineno}:unittest_import")
                elif isinstance(node, ast.ClassDef) and any(
                    (isinstance(base, ast.Name) and base.id == "TestCase")
                    or (
                        isinstance(base, ast.Attribute)
                        and isinstance(base.value, ast.Name)
                        and base.value.id == "unittest"
                        and base.attr == "TestCase"
                    )
                    for base in node.bases
                ):
                    offenders.append(f"{relative}:{node.lineno}:testcase_inheritance")
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "unittest"
                    and node.func.attr == "main"
                ):
                    offenders.append(f"{relative}:{node.lineno}:unittest_main")
                elif (
                    isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                ):
                    offenders.append(f"{relative}:{node.lineno}:direct_test_entrypoint")
        assert offenders == []

    def test_nox_tests_build_and_install_the_wheel_before_running_pytest(self) -> None:
        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert set(functions) >= {"_build_wheel", "_install_wheel", "_assert_installed_product"}
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        commands = [
            tuple(
                argument.value
                for argument in call.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            )
            for call in calls
            if isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "session"
            and call.func.attr in {"run", "run_install"}
        ]
        assert any(command[:3] == ("uv", "build", "--wheel") for command in commands)
        assert any(command[:3] == ("uv", "pip", "install") for command in commands)
        tests_calls = {
            node.func.id
            for node in ast.walk(functions["tests"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert tests_calls >= {"_build_wheel", "_install_wheel", "_assert_installed_product"}
        assert "_build_executable" not in tests_calls
        tests_source = ast.get_source_segment(source, functions["tests"]) or ""
        quality_source = ast.get_source_segment(source, functions["quality"]) or ""
        assert '"compileall",' in tests_source
        assert '"pytest", "-m", "not native_distribution"' in tests_source
        assert '"pytest",\n        "-m",\n        "not native_distribution"' in quality_source
        assert (
            '"CODEX_RESPONSES_PROXY_EXECUTABLE": str(_installed_executable(session))'
            in tests_source
        )
        assert (
            '"CODEX_RESPONSES_PROXY_EXECUTABLE": str(_installed_executable(session))'
            in quality_source
        )
        assert "PYTHONPATH=src" not in source

    def test_nox_release_exports_one_manifest_bound_native_asset_set(self) -> None:
        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        release_source = ast.get_source_segment(source, functions["release"]) or ""
        assert '"tests/cli/test_interface.py"' in release_source
        assert '"tests/service/handoff/test_subprocess.py"' in release_source
        assert '"CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE": str(executable)' in release_source
        assert '"-m", "tests.' not in release_source
        release_calls = {
            node.func.id
            for node in ast.walk(functions["release"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_package_release_asset" in release_calls
        package_source = ast.get_source_segment(source, functions["_package_release_asset"]) or ""
        assert "tools.release.assets" in package_source
        assert "--executable" in package_source
        assert "--platform" in package_source
        assert "session.posargs" in package_source

        native_build_owners = {
            name
            for name, function in functions.items()
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_build_executable"
                for node in ast.walk(function)
            )
        }
        assert native_build_owners == {"release"}

    def test_native_distribution_tests_are_explicit_and_release_owned(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert metadata["tool"]["pytest"]["ini_options"]["markers"] == [
            "native_distribution: requires the self-contained released executable"
        ]
        source = (ROOT / "tests/service/handoff/test_subprocess.py").read_text(encoding="utf-8")
        assert "pytestmark = pytest.mark.native_distribution" in source

    def test_quality_environment_is_repository_owned_and_locked(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert metadata["dependency-groups"]["quality"] == [
            "coverage==7.15.2",
            "hatchling==1.31.0",
            "nox==2026.7.11",
            "pyinstaller==6.21.0",
            "pytest==9.1.1",
            "pytest-mock==3.15.1",
            "pytest-subtests==0.15.0",
            "ruff==0.16.1",
            "ty==0.0.65",
        ]
        assert metadata["tool"]["uv"]["required-version"] == "==0.12.1"
        assert (ROOT / "uv.lock").is_file()
        assert not (ROOT / "tools" / "quality" / "requirements.lock").exists()
        assert not (ROOT / "tools" / "quality" / "requirements.txt").exists()
        assert "requirements.lock" not in (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_repository_declares_the_supported_python_matrix_once(self) -> None:
        assert (ROOT / ".python-versions").read_text(encoding="utf-8") == "3.12\n3.13\n3.14\n"
        assert not (ROOT / ".python-version").exists()
        noxfile = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        assert 'PYTHONS = ("3.12", "3.13", "3.14")' in noxfile
        for session in ("quick", "full", "release"):
            assert f"def {session}(session: nox.Session)" in noxfile

        tree = ast.parse(noxfile)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        full_source = ast.get_source_segment(noxfile, functions["full"]) or ""
        assert 'session.notify(f"tests-{python}")' in full_source
        assert 'session.notify("tests",' not in full_source

    def test_release_black_box_path_is_repeatable(self) -> None:
        """Release verification must tolerate repeated commands in one Nox session."""

        tree = ast.parse((ROOT / "noxfile.py").read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_without_python"
        )
        mkdir = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "mkdir"
        )
        keywords = {keyword.arg: keyword.value for keyword in mkdir.keywords}
        exist_ok = keywords.get("exist_ok")
        assert isinstance(exist_ok, ast.Constant)
        assert exist_ok.value is True

    def test_nox_is_the_only_quality_composition_owner(self) -> None:
        assert not (ROOT / "tools" / "quality" / "run.sh").exists()

    def test_forge_quality_jobs_use_the_locked_runner(self) -> None:
        github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        for source in (github, gitlab):
            assert "uv sync --locked --only-group quality" in source
            assert "uv run --locked --no-sync nox -s quality" in source
            assert "tools/quality/run.sh" not in source
            assert "tools/quality/tests.py" not in source
            assert "tools/quality/requirements.txt" not in source
