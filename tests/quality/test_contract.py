"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import os
import re
import tempfile
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
from pytest_mock import MockerFixture

from tests.quality.fixtures import ROOT
from tests.quality.fixtures import checker as _checker
from tests.quality.fixtures import git as _git
from tests.quality.fixtures import load as _load
from tests.quality.fixtures import repository as _test_repository


def _commit_checker() -> ModuleType:
    _load("tools", "tools/__init__.py")
    _load("tools.quality", "tools/quality/__init__.py")
    return _load("codex_responses_proxy_commit_checker", "tools/quality/commits.py")


def _governance_checker() -> ModuleType:
    _load("tools", "tools/__init__.py")
    _load("tools.quality", "tools/quality/__init__.py")
    return _load("codex_responses_proxy_governance_checker", "tools/quality/governance.py")


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
            "pytest.ini",
            ".config/checks/ty/ty.toml",
            ".config/checks/coverage/coverage.ini",
            ".config/checks/coverage/policy.toml",
            ".config/checks/architecture/policy.toml",
            ".config/checks/commits/policy.toml",
            ".config/checks/text-layout/policy.toml",
            ".config/checks/links/lychee.toml",
            ".editorconfig",
        ):
            assert (ROOT / path).is_file(), path

        for duplicate in ("ruff", "pytest", "ty", "coverage"):
            assert duplicate not in tool
        repository = tool.get("codex-responses-proxy", {})
        assert "quality" not in repository

        governance = (ROOT / "docs/governance/release-and-change-policy.md").read_text(
            encoding="utf-8"
        )
        assert "`pytest.ini` therefore owns test discovery and warning policy" in governance
        assert "`.config/checks/<concern>/` owns quality policy" not in governance

        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert ".pytest_cache/" in ignored

        ruff = tomllib.loads((ROOT / ".config/checks/ruff/ruff.toml").read_text(encoding="utf-8"))
        assert ruff["lint"]["select"] == [
            "E4",
            "E7",
            "E9",
            "F",
            "I",
            "N",
            "ARG",
            "A",
            "ASYNC",
            "DTZ",
            "D100",
            "D105",
            "D107",
            "D400",
            "D401",
            "D404",
            "D415",
            "EXE",
            "FA",
            "FLY",
            "G",
            "ICN",
            "LOG",
            "PGH",
            "PLC0414",
            "PLW1510",
            "PLW2901",
            "PYI025",
            "RSE",
            "SLOT",
            "T10",
            "YTT",
            "ERA",
            "FURB",
            "Q",
            "S102",
            "S104",
            "S307",
            "S602",
            "S604",
            "S605",
            "S606",
            "S608",
            "S609",
            "S610",
            "S611",
            "S612",
            "S701",
            "PT",
            "UP",
            "B",
            "C4",
            "PIE",
            "RET",
            "PERF",
            "RUF",
        ]
        assert "ignore" not in ruff["lint"]
        assert "per-file-ignores" not in ruff["lint"]

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

    def test_dependency_and_dead_code_policy_has_one_precise_owner(self) -> None:
        dependency = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "deptry"
        ]
        assert dependency == {"known_first_party": ["codex_responses_proxy"]}

        dead_code = tomllib.loads(
            (ROOT / ".config/checks/dead-code/vulture.toml").read_text(encoding="utf-8")
        )["tool"]["vulture"]
        assert dead_code == {"min_confidence": 100, "sort_by_size": True}

        governance = _governance_checker()
        commands = governance._commands(online_links=False)
        assert sum(command[0] == "deptry" for command in commands) == 1
        assert sum(command[0] == "vulture" for command in commands) == 1
        quality_commands = tuple(
            argument
            for command in commands
            if command[0] in {"deptry", "vulture"}
            for argument in command
        )
        assert "--ignore" not in quality_commands
        assert "--exclude" not in quality_commands
        assert "--whitelist" not in quality_commands
        assert "--baseline" not in quality_commands

    def test_governance_composition_owns_each_repository_check_once(self, mocker) -> None:
        governance = _governance_checker()
        completed = mocker.Mock(returncode=0)
        run = mocker.patch.object(governance.subprocess, "run", return_value=completed)

        governance.audit(online_links=False)

        commands = [tuple(call.args[0]) for call in run.call_args_list]
        assert commands == [
            ("cue", "vet", ".config/ci/pipeline.cue"),
            (governance.sys.executable, "-m", "tools.ci.project"),
            ("openspec", "validate", "--all", "--strict", "--no-interactive"),
            ("actionlint", ".github/workflows/verify.yml"),
            (
                "deptry",
                "src/codex_responses_proxy",
                "--config",
                "pyproject.toml",
                "--no-ansi",
            ),
            (
                "vulture",
                "src/codex_responses_proxy",
                "tools",
                "--config",
                ".config/checks/dead-code/vulture.toml",
            ),
            ("gitleaks", "git", "--platform", "gitlab", "--redact", "--no-banner", "."),
            (
                "lychee",
                "--config",
                ".config/checks/links/lychee.toml",
                "--offline",
                "./*.md",
                "./**/*.md",
            ),
            (governance.sys.executable, "tools/release/metadata.py"),
            (governance.sys.executable, "-m", "tools.quality.repository"),
        ]

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
        assert subject.fullmatch("fix(ci): provision quality projection tools")
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

    def test_worktree_fingerprint_is_path_sensitive_and_ignores_git_internals(
        self,
    ) -> None:
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

    def test_semantic_name_gate_rejects_numeric_and_cross_language_grammar(
        self,
    ) -> None:
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
