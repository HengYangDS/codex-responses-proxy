"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import tomllib
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
    _load("tools", "tools/__init__.py")
    _load("tools.quality", "tools/quality/__init__.py")
    return _load("codex_responses_proxy_quality_checker", "tools/quality/repository.py")


def _commit_checker() -> ModuleType:
    _load("tools", "tools/__init__.py")
    _load("tools.quality", "tools/quality/__init__.py")
    return _load("codex_responses_proxy_commit_checker", "tools/quality/commits.py")


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
        _git(root, "init", "-q", "--initial-branch=fixture-root")
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
            "module_public_definition_docstrings_required": False,
            **overrides,
        }
        return _checker().audit_paths(root, [source], **options)


class TestQualityPolicyContracts:
    """Keep the repository quality scope executable rather than documentary."""

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

    def test_publication_topology_has_only_declared_independent_peers(self) -> None:
        publication = tomllib.loads((ROOT / ".ethos/release.toml").read_text(encoding="utf-8"))[
            "publication"
        ]

        assert set(publication) == {
            "local_verification_command",
            "local_installation_command",
            "peers",
        }
        assert publication["peers"] == [
            {
                "id": "gitlab",
                "provider": "gitlab",
                "role": "organization_collaboration",
                "git_remote": "origin",
                "capabilities": ["repository", "ci_cd", "publication"],
                "ci_surface": ".gitlab-ci.yml",
            },
            {
                "id": "github",
                "provider": "github",
                "role": "public_distribution",
                "git_remote": "github",
                "capabilities": ["repository", "ci_cd", "publication"],
                "ci_surface": ".github/workflows/verify.yml",
            },
        ]

    def test_branch_roles_delegate_local_release_transition_to_ethos(self) -> None:
        policy = tomllib.loads((ROOT / ".ethos/workspace.toml").read_text(encoding="utf-8"))[
            "branch_roles"
        ]

        assert {key: policy[key] for key in policy if key != "transitions"} == {
            "release_branch": "main",
            "accepted_branch": "dev",
            "candidate_branch": "candidate/dev",
            "work_branch_prefix": "work/",
            "proposal_branch_prefix": "proposal/",
        }
        assert policy["transitions"] == [
            {
                "id": "accepted-to-release",
                "source_role": "accepted_root",
                "target_role": "release_root",
                "capability": "repository.release",
                "required_gates": [],
                "required_evidence": ["proof:execution"],
                "coupled_with": "",
            }
        ]

    def test_quality_policy_has_one_explicit_owner_per_concern(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        tool = pyproject.get("tool", {})

        for path in (
            ".config/checks/ruff/ruff.toml",
            ".config/checks/ty/ty.toml",
            ".config/checks/coverage/coverage.ini",
            ".config/checks/coverage/policy.toml",
            ".config/checks/architecture/policy.toml",
            ".config/checks/commits/policy.toml",
            ".config/checks/text-layout/policy.toml",
            ".editorconfig",
        ):
            assert (ROOT / path).is_file(), path

        for duplicate in ("ruff", "ty", "coverage"):
            assert duplicate not in tool
        assert set(tool["pytest"]) == {
            "addopts",
            "cache_dir",
            "filterwarnings",
            "markers",
            "testpaths",
            "python_classes",
        }
        repository = tool.get("codex-responses-proxy", {})
        assert "quality" not in repository

        rationale = {
            "risk_model",
            "measurement",
            "false_positive_cost",
            "remediation",
            "review_condition",
        }
        for relative in (
            ".config/checks/architecture/policy.toml",
            ".config/checks/commits/policy.toml",
            ".config/checks/coverage/policy.toml",
            ".config/checks/text-layout/policy.toml",
        ):
            policy = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))
            assert all(
                isinstance(policy.get(field), str) and policy[field].strip() for field in rationale
            ), relative

    def test_editor_defaults_and_text_layout_policy_are_aligned(self) -> None:
        editor = (ROOT / ".editorconfig").read_text(encoding="utf-8")
        policy = tomllib.loads(
            (ROOT / ".config/checks/text-layout/policy.toml").read_text(encoding="utf-8")
        )

        assert "charset = utf-8" in editor
        assert "end_of_line = lf" in editor
        assert "insert_final_newline = true" in editor
        assert "trim_trailing_whitespace = true" in editor
        assert policy["encoding"] == "utf-8"
        assert policy["line_ending"] == "lf"
        assert policy["insert_final_newline"] is True
        assert policy["trim_trailing_whitespace"] is True

    def test_commit_subjects_consume_the_tracked_positive_grammar(self) -> None:
        checker = _checker()
        assert checker.commit_subject_gaps(ROOT) == []

        policy = tomllib.loads(
            (ROOT / ".config/checks/commits/policy.toml").read_text(encoding="utf-8")
        )
        (subject,) = _commit_checker().commit_subject_patterns(policy)

        assert subject.fullmatch("refactor(quality): centralize repository policy owners")
        assert subject.fullmatch("fix(install): restore exact payload on rollback")
        assert subject.fullmatch("fix(supervision): classify zombie tombstones")
        assert not subject.fullmatch("refactor: centralize repository policy owners")
        assert not subject.fullmatch("fix(arbitrary): restore exact payload on rollback")
        assert not subject.fullmatch("materialize quality-policy-ssot carrier")

    def test_commit_subject_grammar_allows_internal_semver_periods(self) -> None:
        policy = tomllib.loads(
            (ROOT / ".config/checks/commits/policy.toml").read_text(encoding="utf-8")
        )
        (subject,) = _commit_checker().commit_subject_patterns(policy)

        assert subject.fullmatch("chore(release): prepare v2.0.22")
        assert not subject.fullmatch("chore(release): prepare v2.0.22.")

    def test_commit_subjects_use_remote_main_when_candidate_is_local_only(self) -> None:
        checker = _checker()
        with _test_repository(("tracked.txt",)) as root:
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "test(quality): establish hosted baseline",
            )
            base = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            _git(root, "update-ref", "refs/remotes/origin/main", base)
            (root / "tracked.txt").write_text("changed\n", encoding="utf-8")
            _git(root, "add", "tracked.txt")
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "invalid hosted subject",
            )

            assert checker.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid hosted subject"
            ]

    def test_commit_subjects_validate_head_without_an_integration_ref(self) -> None:
        checker = _checker()
        with _test_repository(("tracked.txt",)) as root:
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "invalid root subject",
            )
            branch = _git(root, "branch", "--show-current").stdout.strip().decode()
            _git(root, "switch", "--detach", "-q")
            _git(root, "branch", "-D", branch)

            assert checker.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid root subject"
            ]

    def test_commit_subjects_skip_an_integration_ref_ahead_of_head(self) -> None:
        checker = _checker()
        with _test_repository(("tracked.txt",)) as root:
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "invalid root subject",
            )
            head = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
            _git(root, "add", "tracked.txt")
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "test(quality): candidate ahead of checkout",
            )
            candidate = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            _git(root, "update-ref", "refs/heads/candidate/dev", candidate)
            _git(root, "reset", "--hard", "-q", head)

            assert checker.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid root subject"
            ]

    def test_readme_install_path_matches_product_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        assert "$CODEX_RESPONSES_PROXY_RELEASE_ASSET" not in readme
        assert "$CODEX_RESPONSES_PROXY_RELEASE_TRUST_ANCHOR" not in readme
        assert "codex-responses-proxy-<version>-macos-arm64.tar.gz" in readme
        assert re.search(r"codex-responses-proxy-\d+\.\d+\.\d+-", readme) is None
        assert "Replace `<version>` with the release version you downloaded." in readme
        assert "codex-responses-proxy-macos-arm64.manifest.json" in readme
        assert "SHA256SUMS.sig" in readme
        assert "SSH" in readme
        assert "`allowed_signers` file" in readme
        assert "--port 8801" in readme
        assert "CODEX_RESPONSES_PROXY_PROXY_PORT" not in readme

    def test_python_command_surfaces_use_one_modern_parser(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = pyproject["project"]["dependencies"]
        assert {requirement.partition("==")[0] for requirement in dependencies} == {
            "certifi",
            "cyclopts",
            "platformdirs",
            "psutil",
            "rich",
        }
        assert all(requirement.partition("==")[1:] != ("", "") for requirement in dependencies)
        offenders = []
        for root in (ROOT / "src", ROOT / "tools"):
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                if "import argparse" in source or "from argparse" in source:
                    offenders.append(path.relative_to(ROOT).as_posix())
        assert offenders == []

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

    def test_decision_records_have_one_register_and_semantic_names(self) -> None:
        assert _checker().decision_record_gaps(ROOT) == []

    def test_decision_record_gate_rejects_numeric_and_unregistered_names(self) -> None:
        checker = _checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decisions = root / "docs/decisions"
            decisions.mkdir(parents=True)
            (decisions / "decision-register.md").write_text(
                "# Decision Records\n", encoding="utf-8"
            )
            (decisions / "0001-vague.md").write_text("# ADR-0001: Vague\n", encoding="utf-8")
            valid = decisions / "dr-0002-release-trust.md"
            valid.write_text(
                "# DR-0002: Release Trust\n\n"
                "- Status: accepted\n"
                "- Date: 2026-08-07\n\n"
                "## Context\n\nContext.\n\n"
                "## Decision\n\nDecision.\n\n"
                "## Consequences\n\nConsequences.\n\n"
                "## Revisit Trigger\n\nTrigger.\n",
                encoding="utf-8",
            )

            gaps = checker.decision_record_gaps(root)

        assert "decision_record_name_invalid:docs/decisions/0001-vague.md" in gaps
        assert "decision_record_unregistered:docs/decisions/dr-0002-release-trust.md" in gaps

    def test_decision_record_gate_requires_unique_registration_without_history_ratchets(
        self,
    ) -> None:
        checker = _checker()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decisions = root / "docs/decisions"
            decisions.mkdir(parents=True)
            first = decisions / "dr-0001-boundary.md"
            third = decisions / "dr-0003-release.md"
            body = (
                "- Status: accepted\n"
                "- Date: 2026-08-07\n\n"
                "## Context\n\nContext.\n\n"
                "## Decision\n\nDecision.\n\n"
                "## Consequences\n\nConsequences.\n\n"
                "## Revisit Trigger\n\nTrigger.\n"
            )
            first.write_text("# DR-0001: Boundary\n\n" + body, encoding="utf-8")
            third.write_text("# DR-0003: Release\n\n" + body, encoding="utf-8")
            (decisions / "decision-register.md").write_text(
                "# Decision Records\n\n"
                "[DR-0001](dr-0001-boundary.md)\n"
                "[duplicate](dr-0001-boundary.md)\n"
                "[DR-0003](dr-0003-release.md)\n",
                encoding="utf-8",
            )

            gaps = checker.decision_record_gaps(root)

        assert "decision_record_sequence_gap:0002" not in gaps
        assert "decision_record_registration_duplicate:docs/decisions/dr-0001-boundary.md" in gaps

    def test_tracked_project_files_follow_semantic_type_grammars(self) -> None:
        assert _checker().semantic_name_gaps(ROOT) == []

    def test_semantic_name_gate_rejects_numeric_and_cross_language_grammar(self) -> None:
        checker = _checker()
        with _test_repository(
            (
                "src/valid_name.py",
                "src/invalid-name.py",
                "scripts/release/check_release.sh",
                "docs/2026-plan.md",
            )
        ) as root:
            gaps = checker.semantic_name_gaps(root)

        assert "semantic_name_invalid:python:src/invalid-name.py" in gaps
        assert "semantic_name_invalid:shell:scripts/release/check_release.sh" in gaps
        assert "semantic_name_invalid:markdown:docs/2026-plan.md" in gaps

    def test_semantic_name_gate_exempts_only_openspec_history(self) -> None:
        checker = _checker()
        with _test_repository(
            (
                "docs/2026-plan.md",
                "openspec/changes/archive/2026-08-07-release/specs/product/spec.md",
            )
        ) as root:
            gaps = checker.semantic_name_gaps(root)

        assert gaps == ["semantic_name_invalid:markdown:docs/2026-plan.md"]

    def test_semantic_name_gate_accepts_official_pyinstaller_hook_modules(self) -> None:
        checker = _checker()
        with _test_repository(("tools/release/hooks/hook-ctypes.py",)) as root:
            gaps = checker.semantic_name_gaps(root)

        assert gaps == []

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

        assert argparse_owners == []
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
        assert (tests / "service/handoff/test_state_machine.py").is_file()
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
        assert not tuple(tests.joinpath("providers").glob("test_portable_*.py"))
