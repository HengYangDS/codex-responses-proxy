"""Structural and coverage contracts for repository quality."""

from __future__ import annotations

import ast
import io
import tempfile
import tomllib
import tokenize
from pathlib import Path

import pytest

from tests.quality.fixtures import (
    ROOT,
    audit_source,
    checker,
    git,
    load,
    quality_inventory,
    repository,
)


class TestStructuralQualityContracts:
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
        quality_checker = checker()
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
                "src/codex_responses_proxy/extra/state.py": (
                    "from codex_responses_proxy.relay import relay\n"
                ),
                "src/codex_responses_proxy/relay/relay.py": (
                    "from codex_responses_proxy.runtime import state\n"
                ),
                "src/codex_responses_proxy/lifecycle/install.py": (
                    "import client_control_plane\nCOMMAND = 'client-control-plane sync'\n"
                ),
            }
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

            gaps = quality_checker.architecture_gaps(root)

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
        assert "architecture_undeclared_package:extra" in gaps
        assert "architecture_disallowed_edge:relay->runtime" not in gaps
        assert "architecture_disallowed_edge:extra->relay" in gaps
        assert (
            "architecture_foreign_product_dependency:"
            "src/codex_responses_proxy/lifecycle/install.py:1:client_control_plane" in gaps
        )
        assert (
            "architecture_foreign_product_literal:"
            "src/codex_responses_proxy/lifecycle/install.py:2:client-control-plane" in gaps
        )

    def test_unratcheted_file_exceeding_hard_limit_fails(self) -> None:
        gaps, inventory = audit_source(
            "\n".join(f"value_{index} = {index}" for index in range(4)), logic_limit=3
        )
        assert inventory[0]["logical_statements"] == 4
        assert "code_size_exceeded:source.py:4>3" in gaps

    def test_ratchet_is_an_exact_ceiling_not_a_free_allowance(self) -> None:
        gaps, _ = audit_source("a = 1\nb = 2\nc = 3\n", logic_limit=1, ratchets={"source.py": 2})
        assert "code_size_ratchet_increased:source.py:3>2" in gaps
        assert gaps

    @pytest.mark.parametrize(
        "source",
        ("value = call(first, second)\n", "value = call(\n first,\n second,\n)\n"),
    )
    def test_logical_statement_metric_is_invariant_to_formatter_wrapping(self, source: str) -> None:
        gaps, inventory = audit_source(source, logic_limit=1, test_limit=1)
        assert gaps == []
        assert inventory[0]["logical_statements"] == 1

    def test_module_public_definition_docstring_switch_is_actually_enforced(self) -> None:
        gaps, _ = audit_source(
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
        gaps, _ = audit_source(source, **options)
        assert expected in gaps

    def test_structural_inventory_exposes_eloc_function_size_and_nesting(self) -> None:
        gaps, inventory = audit_source(
            "def owner(value):\n    if value:\n        return value\n    return None\n",
            module_eloc_limit=10,
            function_eloc_limit=10,
            nesting_depth_limit=2,
        )
        assert gaps == []
        assert inventory[0]["effective_lines"] == 4
        assert inventory[0]["max_function_lines"] == 4
        assert inventory[0]["max_nesting_depth"] == 1

    def test_structural_limits_apply_to_tests_without_a_parallel_exception(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "tests" / "test_large.py"
        source.parent.mkdir()
        source.write_text(
            "def test_large():\n"
            "    if True:\n"
            "        if True:\n"
            "            return 1\n"
            "    return 0\n",
            encoding="utf-8",
        )
        gaps, _ = checker().audit_paths(
            tmp_path,
            [source],
            logic_limit=100,
            test_limit=100,
            ratchets={},
            module_eloc_limit=3,
            function_eloc_limit=3,
            nesting_depth_limit=1,
        )
        assert "module_eloc_exceeded:tests/test_large.py:5>3" in gaps
        assert "function_eloc_exceeded:tests/test_large.py:5>3" in gaps
        assert "nesting_depth_exceeded:tests/test_large.py:2>1" in gaps

    def test_coverage_floor_is_branch_aware_and_at_least_ninety_five_percent(self) -> None:
        coverage = (ROOT / ".config/checks/coverage/coverage.ini").read_text(encoding="utf-8")
        policy = tomllib.loads(
            (ROOT / ".config/checks/coverage/policy.toml").read_text(encoding="utf-8")
        )
        assert "branch = True" in coverage
        assert "source_pkgs = codex_responses_proxy" in coverage
        assert "omit" not in coverage
        assert policy["minimum_percent"] > 95
        assert policy["comparison"] == "strictly-greater-than"
        assert policy["scopes"] == ["aggregate", "package", "module"]

    def repository_owned_structural_limits_are_ratified(self) -> None:
        policy = tomllib.loads(
            (ROOT / ".config/checks/architecture/policy.toml").read_text(encoding="utf-8")
        )
        assert policy["logic_max_statements"] == 600
        assert policy["module_max_eloc"] == 600
        assert policy["function_max_eloc"] == 120
        assert policy["max_nesting_depth"] == 8
        assert "ratchet" not in policy

    def repository_has_standard_package_metadata_and_one_version_owner(self) -> None:
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
        with repository(("src/current.py", "tests/test_current.py")) as root:
            added = root / "src" / "added.py"
            added.write_text("pass\n", encoding="utf-8")
            git(root, "add", "--", "src/added.py")
            (root / "src/current.py").unlink()
            git(root, "add", "--", "src/current.py")
            inventory = quality_inventory(root)
        assert inventory.gaps == ()
        assert [path.relative_to(root).as_posix() for path in inventory.paths] == [
            "src/added.py",
            "tests/test_current.py",
        ]

    def test_quality_inventory_rejects_untracked_missing_and_out_of_scope_is_ignored(self) -> None:
        files = ("src/tracked.py", "tests/test_current.py", "outside/foreign.py")
        with repository(files, tracked=files[1:]) as root:
            (root / "tests/test_current.py").unlink()
            inventory = quality_inventory(root)
        assert inventory.paths == ()
        assert inventory.gaps == (
            "quality_inventory_missing:tests/test_current.py",
            "quality_inventory_untracked:src/tracked.py",
        )

    def test_quality_inventory_glob_does_not_expand_beyond_its_configured_depth(self) -> None:
        quality_checker = checker()
        assert quality_checker._in_scope("owner.py", ("*.py",))
        assert not quality_checker._in_scope("nested/foreign.py", ("*.py",))
        assert quality_checker._in_scope("tools/owner.py", ("tools/*.py",))
        assert not quality_checker._in_scope("tools/nested/foreign.py", ("tools/*.py",))

    def test_quality_inventory_rejects_symlink_misnamed_test_and_empty_tests(self) -> None:
        with repository(("src/current.py", "tests/helper.py")) as root:
            target = root / "target.py"
            target.write_text("pass\n", encoding="utf-8")
            link = root / "src" / "link.py"
            link.symlink_to(target)
            git(root, "add", "--", "src/link.py")
            inventory = quality_inventory(root)
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
        with repository(files) as root:
            inventory = quality_inventory(root)
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
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
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
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        assert checker.statement_gaps(totals, floor) == expected

    def test_each_semantic_package_must_clear_both_coverage_floors(self) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        files = {
            "/site-packages/codex_responses_proxy/cli/application.py": {
                "summary": {
                    "num_statements": 60,
                    "covered_lines": 58,
                    "num_branches": 20,
                    "covered_branches": 19,
                }
            },
            "/site-packages/codex_responses_proxy/relay/exchange.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 99,
                    "num_branches": 100,
                    "covered_branches": 96,
                }
            },
        }
        assert checker.package_gaps(files, 95) == [
            "package_branch_coverage_not_strictly_above_floor:cli:95.00<=95.00"
        ]

    def test_branchless_root_package_is_governed_by_statement_coverage(self) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        files = {
            "/site-packages/codex_responses_proxy/cli/__main__.py": {
                "summary": {
                    "num_statements": 3,
                    "covered_lines": 3,
                    "num_branches": 0,
                    "covered_branches": 0,
                }
            }
        }
        assert checker.package_gaps(files, 95) == []

    def test_each_product_module_must_clear_both_coverage_floors(self) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        files = {
            "/site-packages/codex_responses_proxy/relay/exchange.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 99,
                    "num_branches": 20,
                    "covered_branches": 19,
                }
            },
            "/site-packages/codex_responses_proxy/relay/__init__.py": {
                "summary": {
                    "num_statements": 0,
                    "covered_lines": 0,
                    "num_branches": 0,
                    "covered_branches": 0,
                }
            },
        }
        assert checker.module_gaps(files, 95) == [
            "module_branch_coverage_not_strictly_above_floor:relay/exchange.py:95.00<=95.00"
        ]
