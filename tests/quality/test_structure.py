"""Structural and coverage contracts for repository quality."""

from __future__ import annotations

import ast
import io
import tempfile
import tokenize
import tomllib
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
    def test_product_and_tests_never_mutate_import_resolution_or_suppress_analysis(
        self,
    ) -> None:
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

    def test_architecture_gate_enforces_positive_topology_and_package_contracts(
        self,
    ) -> None:
        quality_checker = checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "control.py": "def main():\n    return 0\n",
                "src/codex_responses_proxy/__init__.py": "from .runtime import state\n",
                "src/codex_responses_proxy/common/value.py": "VALUE = 1\n",
                "src/codex_responses_proxy/service/__init__.py": "",
                "src/codex_responses_proxy/extra/state.py": (
                    "from codex_responses_proxy.relay import relay\n"
                ),
                "src/codex_responses_proxy/relay/relay.py": (
                    "from codex_responses_proxy.runtime import state\n"
                ),
            }
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

            gaps = quality_checker.architecture_gaps(root)

        assert "architecture_root_implementation:control.py" in gaps
        assert "architecture_init_behavior:src/codex_responses_proxy/__init__.py" in gaps
        assert "architecture_undeclared_package:common" in gaps
        assert (
            "architecture_package_declaration_missing:src/codex_responses_proxy/service/__init__.py"
            in gaps
        )
        assert "architecture_undeclared_package:extra" in gaps
        assert "architecture_disallowed_edge:relay->runtime" not in gaps
        assert "architecture_disallowed_edge:extra->relay" in gaps

    @pytest.mark.parametrize(
        "source",
        ["value = call(first, second)\n", "value = call(\n first,\n second,\n)\n"],
    )
    def test_logical_statement_metric_is_invariant_to_formatter_wrapping(self, source: str) -> None:
        gaps, inventory = audit_source(source)
        assert gaps == []
        assert inventory[0]["logical_statements"] == 1

    def test_structural_inventory_exposes_eloc_function_size_and_nesting(self) -> None:
        gaps, inventory = audit_source(
            "def owner(value):\n    if value:\n        return value\n    return None\n"
        )
        assert gaps == []
        assert inventory[0]["effective_lines"] == 4
        assert inventory[0]["max_function_lines"] == 4
        assert inventory[0]["max_nesting_depth"] == 1

    def test_structural_metrics_are_observations_not_merge_thresholds(self) -> None:
        source = "\n".join(
            [
                "def owner(value):",
                *[f"    value += {index}" for index in range(120)],
                "    return value",
            ]
        )
        gaps, inventory = audit_source(source)
        assert gaps == []
        assert inventory[0]["logical_statements"] == 122
        assert inventory[0]["effective_lines"] == 122

    def test_coverage_floor_has_one_owner_and_semantic_risk_scopes(self) -> None:
        coverage = (ROOT / ".config/checks/coverage/coverage.ini").read_text(encoding="utf-8")
        policy = tomllib.loads(
            (ROOT / ".config/checks/coverage/policy.toml").read_text(encoding="utf-8")
        )
        assert "branch = True" in coverage
        assert "source_pkgs = codex_responses_proxy" in coverage
        assert "omit" not in coverage
        assert set(policy) == {
            "minimum_percent",
            "comparison",
            "threshold_scopes",
            "package_observation",
            "metrics",
            "owner",
            "source",
            "risk_model",
            "measurement",
            "false_positive_cost",
            "remediation",
            "review_condition",
        }
        assert policy["minimum_percent"] == 95.0
        assert policy["comparison"] == "at-least"
        assert policy["threshold_scopes"] == ["aggregate"]
        assert policy["package_observation"] == "required"

    def test_repository_policy_declares_positive_owners_without_numeric_vetoes(
        self,
    ) -> None:
        policy = tomllib.loads(
            (ROOT / ".config/checks/architecture/policy.toml").read_text(encoding="utf-8")
        )
        assert policy["source_roots"] == ["src/codex_responses_proxy", "tools"]
        assert policy["test_roots"] == ["tests"]
        assert policy["package_root"] == "src/codex_responses_proxy"
        assert set(policy["allowed_package_edges"]) == {
            "cli",
            "lifecycle",
            "protocol",
            "providers",
            "relay",
            "runtime",
            "service",
        }
        assert set(policy) == {
            "owner",
            "risk_model",
            "measurement",
            "false_positive_cost",
            "remediation",
            "review_condition",
            "source_roots",
            "test_roots",
            "package_root",
            "root_configuration_modules",
            "package_initializers",
            "allowed_package_edges",
        }
        assert all(
            isinstance(policy[field], str) and policy[field].strip()
            for field in (
                "owner",
                "risk_model",
                "measurement",
                "false_positive_cost",
                "remediation",
                "review_condition",
            )
        )

    def test_package_initializer_contract_is_explicit_and_configurable(self) -> None:
        quality_checker = checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "src" / "codex_responses_proxy"
            (package / "service").mkdir(parents=True)
            (package / "service" / "__init__.py").write_text(
                '"""Service package."""\nVALUE = 1\n', encoding="utf-8"
            )
            policy = {
                "owner": "quality",
                "risk_model": "package initializers can hide runtime coupling",
                "measurement": "parse declared package initializers",
                "false_positive_cost": "a deliberate initializer requires policy review",
                "remediation": "move runtime behavior to a semantic module",
                "review_condition": "reassess when initializer behavior is required",
                "source_roots": ["src/codex_responses_proxy"],
                "test_roots": ["tests"],
                "package_root": "src/codex_responses_proxy",
                "root_configuration_modules": [],
                "package_initializers": "declarations-only",
                "allowed_package_edges": {"service": []},
            }
            gaps = quality_checker.architecture_gaps(root, policy)
            policy["package_initializers"] = "ordinary-modules"
            relaxed = quality_checker.architecture_gaps(root, policy)
        expected = "architecture_init_behavior:src/codex_responses_proxy/service/__init__.py"
        assert expected in gaps
        assert expected not in relaxed

    def test_repository_has_standard_package_metadata_and_one_version_owner(
        self,
    ) -> None:
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

    def test_quality_inventory_uses_index_ownership_with_staged_add_and_delete(
        self,
    ) -> None:
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

    def test_quality_inventory_rejects_untracked_missing_and_out_of_scope_is_ignored(
        self,
    ) -> None:
        files = ("src/tracked.py", "tests/test_current.py", "outside/foreign.py")
        with repository(files, tracked=files[1:]) as root:
            (root / "tests/test_current.py").unlink()
            inventory = quality_inventory(root)
        assert inventory.paths == ()
        assert inventory.gaps == (
            "quality_inventory_missing:tests/test_current.py",
            "quality_inventory_untracked:src/tracked.py",
        )

    def test_quality_inventory_glob_does_not_expand_beyond_its_configured_depth(
        self,
    ) -> None:
        quality_checker = checker()
        assert quality_checker._in_scope("owner.py", ("*.py",))
        assert not quality_checker._in_scope("nested/foreign.py", ("*.py",))
        assert quality_checker._in_scope("tools/owner.py", ("tools/*.py",))
        assert not quality_checker._in_scope("tools/nested/foreign.py", ("tools/*.py",))

    def test_quality_inventory_rejects_symlink_misnamed_test_and_empty_tests(
        self,
    ) -> None:
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
        [
            (
                {"num_branches": 20, "covered_branches": 19},
                95,
                [],
            ),
            ({"num_branches": 200, "covered_branches": 191}, 95, []),
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
        ],
    )
    def test_branch_coverage_floor_is_enforced_independently(
        self, totals: dict[str, int], floor: int, expected: list[str]
    ) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        assert checker.branch_gaps(totals, floor) == expected

    @pytest.mark.parametrize(
        ("totals", "floor", "expected"),
        [
            (
                {"num_statements": 20, "covered_lines": 19},
                95,
                [],
            ),
            ({"num_statements": 200, "covered_lines": 191}, 95, []),
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
        ],
    )
    def test_statement_coverage_floor_is_enforced_independently(
        self, totals: dict[str, int], floor: int, expected: list[str]
    ) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        assert checker.statement_gaps(totals, floor) == expected

    def test_each_semantic_package_must_have_execution_evidence(self) -> None:
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
        assert checker.package_gaps(checker.package_totals(files, "codex_responses_proxy")) == []

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
        assert checker.package_gaps(checker.package_totals(files, "codex_responses_proxy")) == []

    def test_files_combine_into_their_semantic_package_before_admission(self) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        files = {
            "/site-packages/codex_responses_proxy/relay/first.py": {
                "summary": {
                    "num_statements": 1,
                    "covered_lines": 0,
                    "num_branches": 0,
                    "covered_branches": 0,
                }
            },
            "/site-packages/codex_responses_proxy/relay/second.py": {
                "summary": {
                    "num_statements": 99,
                    "covered_lines": 96,
                    "num_branches": 20,
                    "covered_branches": 20,
                }
            },
        }
        assert checker.package_gaps(checker.package_totals(files, "codex_responses_proxy")) == []

    def test_semantic_package_observation_rejects_wholly_unexecuted_owner(self) -> None:
        checker = load("codex_responses_proxy_branch_coverage", "tools/quality/branch_coverage.py")
        files = {
            "/site-packages/codex_responses_proxy/relay/exchange.py": {
                "summary": {
                    "num_statements": 4,
                    "covered_lines": 0,
                    "num_branches": 2,
                    "covered_branches": 0,
                }
            }
        }
        totals = checker.package_totals(files, "codex_responses_proxy")
        assert checker.package_gaps(totals) == [
            "package_statement_coverage_unobserved:relay",
            "package_branch_coverage_unobserved:relay",
        ]
