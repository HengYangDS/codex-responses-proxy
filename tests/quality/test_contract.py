"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from tests.quality.fixtures import ROOT
from tests.quality.fixtures import git as _git
from tests.quality.fixtures import repository as _test_repository
from tools.quality import commits
from tools.quality import governance
from tools.quality import responsibilities
from tools.quality.repository import __main__ as repository_audit
from tools.quality.repository.decisions import decision_record_gaps
from tools.quality.repository.names import semantic_name_gaps
from tools.quality.repository.topology import architecture_gaps


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.CompletedProcess([], 1)])
def test_governance_failure_stops_before_subsequent_commands(failure, mocker, capsys):
    mocker.patch.object(governance, "_commands", return_value=(("first",), ("second",)))
    run = mocker.patch.object(governance.subprocess, "run")
    if isinstance(failure, OSError):
        run.side_effect = failure
    else:
        run.return_value = failure
    with pytest.raises(SystemExit) as stopped:
        governance.main(())
    assert stopped.value.code == 1
    assert run.call_count == 1
    assert "first" in capsys.readouterr().err


@pytest.mark.parametrize(
    "defect", ["missing-register", "duplicate-sequence", "title", "status", "date", "section"]
)
def test_decision_register_requires_unique_complete_records(tmp_path, defect):
    directory = tmp_path / "docs/decisions"
    directory.mkdir(parents=True)
    register = directory / "decision-register.md"
    if defect == "missing-register":
        assert decision_record_gaps(tmp_path) == ["decision_record_register_missing"]
        return
    register.write_text("[decision](dr-0001-owner.md)\n")
    text = "# DR-0001: Owner\n- Status: accepted\n- Date: 2026-01-01\n## Context\n## Decision\n## Consequences\n## Revisit Trigger\n"
    replacements = {
        "title": ("# DR-0001", "# Other"),
        "status": ("accepted", "invalid"),
        "date": ("- Date: 2026-01-01", ""),
        "section": ("## Context", ""),
    }
    if defect in replacements:
        text = text.replace(*replacements[defect])
    (directory / "dr-0001-owner.md").write_text(text)
    if defect == "duplicate-sequence":
        (directory / "dr-0001-other.md").write_text(text)
    expected = {
        "duplicate-sequence": "sequence_duplicate",
        "title": "title_invalid",
        "status": "status_invalid",
        "date": "date_invalid",
        "section": "section_missing",
    }
    assert any(expected[defect] in gap for gap in decision_record_gaps(tmp_path))


def test_pytest_owns_temporary_directory_retirement(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.getini("tmp_path_retention_policy") == "none"
    assert int(pytestconfig.getini("tmp_path_retention_count")) == 0


class TestQualityPolicyContracts:
    """Keep the repository quality scope executable rather than documentary."""

    def test_release_artifacts_have_one_construction_owner(self) -> None:
        package = importlib.util.find_spec("tools.release.artifact")
        assert package is not None
        assert package.submodule_search_locations is not None
        for concern in ("bundle", "format", "assembly", "signing", "__main__"):
            owner = importlib.util.find_spec(f"tools.release.artifact.{concern}")
            assert owner is not None

    def test_repository_checks_share_one_semantic_package(self) -> None:
        """Repository topology, naming, and decisions belong to one audit package."""
        package = importlib.util.find_spec("tools.quality.repository")
        assert package is not None
        assert package.submodule_search_locations is not None
        for concern in ("topology", "names", "decisions"):
            owner = importlib.util.find_spec(f"tools.quality.repository.{concern}")
            assert owner is not None

    def test_current_repository_policy_is_internally_consistent(self) -> None:
        report = repository_audit.audit()
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

    def test_openspec_material_scope_covers_every_repository_carrier(self) -> None:
        profile = tomllib.loads((ROOT / ".ethos/profile.toml").read_text(encoding="utf-8"))

        assert profile["openspec"]["material_paths"] == ["**"]

    def test_default_proof_gates_bind_product_verifiers(self) -> None:
        profile = tomllib.loads((ROOT / ".ethos/profile.toml").read_text(encoding="utf-8"))
        proof = profile["proof"]
        selected = set(proof["code_correctness_gates"])
        bindings = {
            gate["id"]: (
                gate.get("verification_providers"),
                gate.get("execution_mode"),
                gate.get("tool_adapter"),
            )
            for gate in proof["gates"]
            if gate["id"] in selected
        }

        assert bindings == {
            "python-quality": (
                ["ethos.adapters.gates.code_quality:static_report"],
                "verified-command",
                "ethos",
            ),
            "python-matrix": (
                ["ethos.adapters.gates.code_quality:behavior_report"],
                "verified-command",
                "ethos",
            ),
        }
        for gate in proof["gates"]:
            if gate["id"] in selected:
                command = gate["command"]
                assert command[:8] == [
                    "mise",
                    "exec",
                    "--locked",
                    "--",
                    "uv",
                    "run",
                    "--locked",
                    "--group",
                ]
                assert command[8] == "quality"
                assert "--no-sync" not in command
                assert "--python" not in command

    def test_publication_topology_has_only_declared_independent_peers(self) -> None:
        publication = tomllib.loads((ROOT / ".ethos/release.toml").read_text(encoding="utf-8"))[
            "publication"
        ]

        assert set(publication) == {
            "local_verification_command",
            "local_installation_command",
            "peers",
        }
        assert publication["local_verification_command"] == "mise run check"
        assert publication["local_installation_command"] == "mise run native"
        peers = publication["peers"]
        assert all(isinstance(peer.get("forge_repository"), str) for peer in peers)
        assert [
            {key: value for key, value in peer.items() if key != "forge_repository"}
            for peer in peers
        ] == [
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

        assert policy == {
            "release_branch": "main",
            "accepted_branch": "dev",
            "candidate_branch": "candidate/dev",
            "release_mirror": "accepted_ff",
            "work_branch_prefix": "work/",
            "proposal_branch_prefix": "proposal/",
            "canonical_sibling_worktrees": True,
        }

    def test_quality_policy_has_one_explicit_owner_per_concern(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        tool = pyproject.get("tool", {})

        for path in (
            ".config/quality/native/ruff.toml",
            "pytest.toml",
            ".config/quality/native/ty.toml",
            ".config/quality/native/coverage.toml",
            ".config/quality/policy/coverage.toml",
            ".config/quality/policy/architecture.toml",
            ".config/quality/policy/text.toml",
            ".config/quality/native/lychee.toml",
            ".editorconfig",
        ):
            assert (ROOT / path).is_file(), path
        assert not (ROOT / "pytest.ini").exists()
        assert not (ROOT / ".config/quality/native/coverage.ini").exists()

        for duplicate in ("ruff", "pytest", "ty", "coverage"):
            assert duplicate not in tool
        repository = tool.get("codex-responses-proxy", {})
        assert "quality" not in repository

        governance = (ROOT / "docs/governance/release-and-change-policy.md").read_text(
            encoding="utf-8"
        )
        assert "`pytest.toml` therefore owns test discovery and warning policy" in governance
        assert "`.config/quality/policy/` owns quality policy" not in governance

        ruff = tomllib.loads(
            (ROOT / ".config/quality/native/ruff.toml").read_text(encoding="utf-8")
        )
        selected = ruff["lint"]["select"]
        assert len(selected) == len(set(selected))
        assert {"F", "I", "N", "PT", "UP", "B", "RET", "PERF", "RUF"} <= set(selected)
        assert "ANN" not in selected
        assert any(rule == "S" or rule.startswith("S") for rule in selected)
        assert "D" in selected
        assert "ignore" not in ruff["lint"]
        assert ruff["lint"]["pydocstyle"] == {"convention": "google"}
        assert ruff["lint"]["per-file-ignores"] == {"tests/**": ["D1"]}

        rationale = {
            "risk_model",
            "measurement",
            "false_positive_cost",
            "remediation",
            "review_condition",
        }
        for relative in (
            ".config/quality/policy/architecture.toml",
            ".config/quality/policy/coverage.toml",
            ".config/quality/policy/text.toml",
        ):
            policy = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))
            assert all(
                isinstance(policy.get(field), str) and policy[field].strip() for field in rationale
            ), relative

    def test_dependency_and_dead_code_policy_has_one_precise_owner(self) -> None:
        dependency = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "deptry"
        ]
        assert dependency == {
            "known_first_party": ["codex_responses_proxy"],
            "package_module_name_map": {"pyinstaller": ["PyInstaller"]},
        }

        dead_code = tomllib.loads(
            (ROOT / ".config/quality/native/vulture.toml").read_text(encoding="utf-8")
        )["tool"]["vulture"]
        assert dead_code == {"min_confidence": 100, "sort_by_size": True}

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
        completed = mocker.Mock(returncode=0)
        tracked = mocker.Mock(
            returncode=0,
            stdout=(
                b"README.md\0.gitlab-ci.yml\0package.json\0"
                b".config/quality/native/prettier.json\0mise.toml\0"
                b"openspec/changes/archive/old.md\0"
            ),
        )
        run = mocker.patch.object(
            governance.subprocess,
            "run",
            side_effect=[tracked, tracked, *([completed] * 18)],
        )

        governance.audit(online_links=False)

        commands = [tuple(call.args[0]) for call in run.call_args_list[2:]]
        assert commands == [
            (
                "npm",
                "exec",
                "--offline",
                "--",
                "prettier",
                "--check",
                "--config",
                ".config/quality/native/prettier.json",
                "--ignore-path",
                ".config/quality/native/prettier.ignore",
                "README.md",
                ".gitlab-ci.yml",
                "package.json",
                ".config/quality/native/prettier.json",
            ),
            (
                "taplo",
                "format",
                "--check",
                "--config",
                ".config/quality/native/taplo.toml",
                "mise.toml",
            ),
            (
                "npm",
                "exec",
                "--offline",
                "--",
                "markdownlint-cli2",
                "--config",
                ".config/quality/native/markdownlint-cli2.mjs",
                "--no-globs",
                "README.md",
            ),
            (
                "vale",
                "--config=.config/quality/native/vale.ini",
                "--no-global",
                "--no-color",
                "README.md",
            ),
            ("cue", "fmt", "--check", "--files", ".config/ci/pipeline.cue"),
            ("cue", "vet", ".config/ci/pipeline.cue"),
            (governance.sys.executable, "-m", "tools.ci.project"),
            (
                governance.sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "repository_toolchain",
                "tests/quality/test_verification.py",
                "tests/quality/test_contract.py",
            ),
            ("node", "--test", "tests/quality/markdown-policy.test.mjs"),
            (
                "npm",
                "exec",
                "--offline",
                "--",
                "openspec",
                "validate",
                "--all",
                "--strict",
                "--no-interactive",
            ),
            ("actionlint",),
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
                ".config/quality/native/vulture.toml",
            ),
            ("gitleaks", "git", "--platform", "gitlab", "--redact", "--no-banner", "."),
            (
                "lychee",
                "--config",
                ".config/quality/native/lychee.toml",
                "--offline",
                "README.md",
            ),
            (governance.sys.executable, "-m", "tools.release.metadata"),
            (governance.sys.executable, "-m", "tools.quality.hard_coding"),
            (governance.sys.executable, "-m", "tools.quality.repository"),
        ]

    def test_structured_text_formatters_have_disjoint_native_ownership(self) -> None:
        policy = tomllib.loads(
            (ROOT / ".config/quality/responsibility-map.toml").read_text(encoding="utf-8")
        )
        concerns = {concern["id"]: concern for concern in policy["concerns"]}

        assert concerns["structured-text-format"] == {
            "id": "structured-text-format",
            "owner": "prettier",
            "scope": "prettier-formatted",
            "session": "governance",
            "configuration": [
                ".config/quality/native/prettier.json",
                ".config/quality/native/prettier.ignore",
            ],
            "risk_model": concerns["structured-text-format"]["risk_model"],
            "measurement": concerns["structured-text-format"]["measurement"],
            "false_positive_cost": concerns["structured-text-format"]["false_positive_cost"],
            "remediation": concerns["structured-text-format"]["remediation"],
            "review_condition": concerns["structured-text-format"]["review_condition"],
        }
        assert concerns["toml-format"]["owner"] == "taplo"
        assert concerns["toml-format"]["scope"] == "toml-formatted"
        assert concerns["toml-format"]["configuration"] == [".config/quality/native/taplo.toml"]
        assert concerns["cue-format"]["owner"] == "cue"
        assert concerns["cue-format"]["scope"] == "cue-formatted"
        assert concerns["cue-format"]["configuration"] == [".config/ci/pipeline.cue"]

        scopes = {scope["id"]: scope["roles"] for scope in policy["scopes"]}
        assert set(scopes["prettier-formatted"]) & set(scopes["python"]) == {"test-code"}
        assert set(scopes["toml-formatted"]).isdisjoint(scopes["python"])
        assert scopes["cue-formatted"] == ["ci-model"]
        assert {"quality-tool-configuration", "toolchain"} <= set(scopes["prettier-formatted"])
        assignments = responsibilities.audit(ROOT)["assignments"]
        formatted = governance._commands(online_links=False)[0][10:]
        assert {assignments[path] for path in formatted} <= set(scopes["prettier-formatted"])

    def test_editor_defaults_and_text_layout_policy_are_aligned(self) -> None:
        editor = (ROOT / ".editorconfig").read_text(encoding="utf-8")
        taplo = tomllib.loads(
            (ROOT / ".config/quality/native/taplo.toml").read_text(encoding="utf-8")
        )
        policy = tomllib.loads(
            (ROOT / ".config/quality/policy/text.toml").read_text(encoding="utf-8")
        )

        assert "charset = utf-8" in editor
        assert "end_of_line = lf" in editor
        assert "insert_final_newline = true" in editor
        assert "trim_trailing_whitespace = true" in editor
        assert "[*.toml]\nindent_size = 2\n" in editor
        assert "[*.{json,jsonc}]\nindent_style = space\nindent_size = 2\n" in editor
        assert taplo["formatting"]["indent_string"] == "  "
        assert policy["encoding"] == "utf-8"
        assert policy["line_ending"] == "lf"
        assert policy["insert_final_newline"] is True
        assert policy["trim_trailing_whitespace"] is True
        assert {".json", ".jsonc", ".mjs", ".txt"} <= set(policy["tracked_suffixes"])

    def test_git_checkout_preserves_lf_text_and_binary_bytes(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        policy = tomllib.loads(
            (ROOT / ".config/quality/policy/text.toml").read_text(encoding="utf-8")
        )
        roles = tomllib.loads(
            (ROOT / ".config/quality/responsibility-map.toml").read_text(encoding="utf-8")
        )["roles"]
        source_control = next(
            role for role in roles if role["id"] == "source-control-configuration"
        )
        assert attributes == "* text=auto eol=lf\n"
        assert ".gitattributes" in policy["tracked_names"]
        assert ".gitattributes" in source_control["files"]

        with _test_repository(("note.md", "payload.bin")) as root:
            (root / ".gitattributes").write_text(attributes, encoding="utf-8")
            (root / "note.md").write_bytes(b"one\ntwo\n")
            binary = b"\x00one\r\ntwo\n"
            (root / "payload.bin").write_bytes(binary)
            _git(root, "add", "--", ".gitattributes", "note.md", "payload.bin")
            _git(
                root,
                "-c",
                "core.autocrlf=true",
                "checkout-index",
                "-f",
                "--",
                "note.md",
                "payload.bin",
            )
            assert (root / "note.md").read_bytes() == b"one\ntwo\n"
            assert (root / "payload.bin").read_bytes() == binary

    def test_commit_policy_is_declared_for_native_hook_enforcement(self) -> None:
        workspace = tomllib.loads((ROOT / ".ethos/workspace.toml").read_text(encoding="utf-8"))

        assert workspace["commit_policy"]["signing_required"] is True
        assert workspace["commit_policy"]["signing_format"] == "ssh"
        assert isinstance(workspace["commit_policy"]["subject_pattern"], str)

    def test_commit_subjects_validate_an_accepted_tip(self) -> None:
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
                "invalid accepted subject",
            )
            tip = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            _git(root, "update-ref", "refs/heads/candidate/dev", tip)

            assert commits.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid accepted subject"
            ]

    def test_event_range_rejects_invalid_middle_commit_after_refs_advance(self, monkeypatch):
        with _test_repository(("tracked.txt",)) as root:
            revisions = []
            for subject in (
                "test(quality): baseline",
                "invalid middle subject",
                "fix(quality): valid tip",
            ):
                _git(
                    root,
                    "-c",
                    "user.name=Test Author",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--allow-empty",
                    "-qm",
                    subject,
                )
                revisions.append(_git(root, "rev-parse", "HEAD").stdout.strip().decode())
            _git(root, "update-ref", "refs/heads/candidate/dev", revisions[-1])
            monkeypatch.setenv("CODEX_RESPONSES_PROXY_COMMIT_BASE", revisions[0])
            monkeypatch.setenv("CODEX_RESPONSES_PROXY_COMMIT_HEAD", revisions[-1])

            assert commits.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid middle subject"
            ]

    def test_zero_event_base_checks_current_commit_not_historical_subjects(self, monkeypatch):
        with _test_repository(("tracked.txt",)) as root:
            for subject in (
                "invalid historical subject",
                "fix(quality): accepted current subject",
            ):
                _git(
                    root,
                    "-c",
                    "user.name=Test Author",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--allow-empty",
                    "-qm",
                    subject,
                )
            head = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            monkeypatch.setenv("CODEX_RESPONSES_PROXY_COMMIT_BASE", "0" * len(head))
            monkeypatch.setenv("CODEX_RESPONSES_PROXY_COMMIT_HEAD", head)

            assert commits.commit_subject_gaps(root) == []

    def test_commit_checker_derives_event_namespace_without_product_import(self, monkeypatch):
        source = (ROOT / "tools/quality/commits.py").read_text(encoding="utf-8")
        assert "from codex_responses_proxy" not in source
        monkeypatch.setattr(commits, "PROJECT", ROOT / "pyproject.toml")
        assert commits._environment_name("COMMIT_HEAD") == ("CODEX_RESPONSES_PROXY_COMMIT_HEAD")

    @pytest.mark.parametrize(
        ("base", "head", "expected"),
        [
            (None, "tip", "commit_event_objects_invalid"),
            ("tip", None, "commit_event_objects_invalid"),
            ("--all", "tip", "commit_event_objects_invalid"),
            ("tip", "f" * 40, "commit_event_head_mismatch"),
            ("f" * 40, "tip", "commit_event_base_unavailable"),
            ("ahead", "tip", "commit_event_base_not_ancestor"),
            ("tip", "tip", "commit_subject_invalid:invalid event subject"),
            ("0" * 40, "tip", "commit_subject_invalid:invalid event subject"),
        ],
    )
    def test_event_objects_are_complete_and_checkout_bound(self, base, head, expected, monkeypatch):
        with _test_repository(("tracked.txt",)) as root:
            _git(
                root,
                "-c",
                "user.name=Test Author",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "invalid event subject",
            )
            tip = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
            if base == "ahead":
                _git(
                    root,
                    "-c",
                    "user.name=Test Author",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--allow-empty",
                    "-qm",
                    "test(quality): future base",
                )
                base = _git(root, "rev-parse", "HEAD").stdout.strip().decode()
                _git(root, "checkout", "--detach", tip)
            for suffix, value in (("BASE", base), ("HEAD", head)):
                name = f"CODEX_RESPONSES_PROXY_COMMIT_{suffix}"
                if value is None:
                    monkeypatch.delenv(name, raising=False)
                else:
                    monkeypatch.setenv(name, tip if value == "tip" else value)
            assert commits.commit_subject_gaps(root) == [expected]

    def test_commit_subjects_consume_the_tracked_positive_grammar(self) -> None:
        assert commits.commit_subject_gaps(ROOT) == []

        policy = tomllib.loads((ROOT / ".ethos/workspace.toml").read_text(encoding="utf-8"))
        subject = commits.commit_subject_pattern(policy["commit_policy"])

        assert subject.fullmatch("refactor(quality): centralize repository policy owners")
        assert subject.fullmatch("fix(ci): provision quality projection tools")
        assert subject.fullmatch("fix(install): restore exact payload on rollback")
        assert subject.fullmatch("fix(supervision): classify zombie tombstones")
        assert not subject.fullmatch("refactor: centralize repository policy owners")
        assert not subject.fullmatch("fix(arbitrary): restore exact payload on rollback")
        assert not subject.fullmatch("materialize quality-policy-ssot carrier")

    def test_commit_subject_grammar_allows_internal_semver_periods(self) -> None:
        policy = tomllib.loads((ROOT / ".ethos/workspace.toml").read_text(encoding="utf-8"))
        subject = commits.commit_subject_pattern(policy["commit_policy"])

        assert subject.fullmatch("chore(release): prepare v2.0.22")
        assert not subject.fullmatch("chore(release): prepare v2.0.22.")

    def test_commit_subjects_use_remote_main_when_candidate_is_local_only(self) -> None:
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

            assert commits.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid hosted subject"
            ]

    def test_commit_subjects_validate_head_without_an_integration_ref(self) -> None:
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

            assert commits.commit_subject_gaps(root) == [
                "commit_subject_invalid:invalid root subject"
            ]

    def test_commit_subjects_skip_an_integration_ref_ahead_of_head(self) -> None:
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

            assert commits.commit_subject_gaps(root) == [
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
        assert any(requirement.startswith("cyclopts==") for requirement in dependencies)
        offenders = []
        for root in (ROOT / "src", ROOT / "tools"):
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                if "import argparse" in source or "from argparse" in source:
                    offenders.append(path.relative_to(ROOT).as_posix())
        assert offenders == []

    def test_runtime_dependencies_are_exactly_pinned(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = pyproject["project"]["dependencies"]

        assert all(
            name and separator == "==" and version
            for name, separator, version in (
                requirement.partition("==") for requirement in dependencies
            )
        )

    def test_repository_cli_is_quiet_on_success_and_diagnostic_on_failure(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(repository_audit, "audit", return_value={"ok": True, "gaps": []})
        output = mocker.patch("builtins.print")
        repository_audit.main()
        output.assert_not_called()

        mocker.patch.object(
            repository_audit, "audit", return_value={"ok": False, "gaps": ["invalid_contract"]}
        )
        output.reset_mock()
        with pytest.raises(SystemExit):
            repository_audit.main()
        output.assert_called_once()

    def test_current_product_architecture_is_acyclic_and_directional(self) -> None:
        assert architecture_gaps(ROOT) == []

    def test_decision_records_have_one_register_and_semantic_names(self) -> None:
        assert decision_record_gaps(ROOT) == []

    def test_decision_record_gate_rejects_numeric_and_unregistered_names(self) -> None:
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

            gaps = decision_record_gaps(root)

        assert "decision_record_name_invalid:docs/decisions/0001-vague.md" in gaps
        assert "decision_record_unregistered:docs/decisions/dr-0002-release-trust.md" in gaps

    def test_decision_record_gate_requires_unique_registration_without_history_ratchets(
        self,
    ) -> None:
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

            gaps = decision_record_gaps(root)

        assert "decision_record_sequence_gap:0002" not in gaps
        assert "decision_record_registration_duplicate:docs/decisions/dr-0001-boundary.md" in gaps

    def test_tracked_project_files_follow_semantic_type_grammars(self) -> None:
        assert semantic_name_gaps(ROOT) == []

    def test_semantic_name_gate_rejects_numeric_and_cross_language_grammar(
        self,
    ) -> None:
        with _test_repository(
            (
                "src/valid_name.py",
                "src/invalid-name.py",
                "scripts/release/check_release.sh",
                "docs/2026-plan.md",
            )
        ) as root:
            gaps = semantic_name_gaps(root)

        assert "semantic_name_invalid:python:src/invalid-name.py" in gaps
        assert "semantic_name_invalid:shell:scripts/release/check_release.sh" in gaps
        assert "semantic_name_invalid:markdown:docs/2026-plan.md" in gaps

    def test_semantic_name_gate_exempts_only_openspec_history(self) -> None:
        with _test_repository(
            (
                "docs/2026-plan.md",
                "openspec/changes/archive/2026-08-07-release/specs/product/spec.md",
            )
        ) as root:
            gaps = semantic_name_gaps(root)

        assert gaps == ["semantic_name_invalid:markdown:docs/2026-plan.md"]

    def test_semantic_name_gate_accepts_official_pyinstaller_hook_modules(self) -> None:
        with _test_repository(("tools/release/hooks/hook-ctypes.py",)) as root:
            gaps = semantic_name_gaps(root)

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
        assert [name for name in ("listener",) if (tests / name).exists()] == []
        assert (tests / "relay/proxy_fixture.py").is_file()
        assert (tests / "runtime/test_process_environment.py").is_file()
        assert (tests / "service/test_entrypoint.py").is_file()
        assert (tests / "service/handoff/test_state_machine.py").is_file()
        assert (tests / "lifecycle/deployment/test_handoff.py").is_file()

    def test_protocol_and_relay_tests_follow_terminal_ownership(self) -> None:
        tests = ROOT / "tests"
        owners = (
            "protocol/replay/test_projection.py",
            "protocol/replay/test_content.py",
            "protocol/replay/test_history.py",
            "protocol/replay/test_admission.py",
            "protocol/replay/test_items.py",
            "protocol/test_response.py",
            "protocol/recovery/test_input.py",
            "protocol/recovery/test_execution.py",
            "relay/test_empty_response.py",
            "relay/test_routes.py",
        )
        assert all((tests / owner).is_file() for owner in owners)


def test_formatter_defers_digest_bound_aube_bytes_to_the_native_owner() -> None:
    commands = governance._commands(online_links=False)
    prettier = commands[0]
    assert "--ignore-path" in prettier
    ignore = prettier[prettier.index("--ignore-path") + 1]
    assert ignore == ".config/quality/native/prettier.ignore"
    patterns = (ROOT / ignore).read_text(encoding="utf-8")
    assert "../../../.mise/locks/**/aube-lock.yaml" in patterns
    assert len([line for line in patterns.splitlines() if line and not line.startswith("#")]) == 1


def test_markdown_lint_is_one_locked_native_governance_owner() -> None:
    metadata = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert metadata["devDependencies"].get("markdownlint-cli2") == "0.23.3"
    selected = [
        command
        for command in governance._commands(online_links=False)
        if "markdownlint-cli2" in command
    ]
    assert len(selected) == 1
    command = selected[0]
    assert command[:6] == ("npm", "exec", "--offline", "--", "markdownlint-cli2", "--config")
    assert command[6] == ".config/quality/native/markdownlint-cli2.mjs"
    assert "--fix" not in command
    assert "--no-globs" in command
    assert "README.md" in command
    assert "openspec/changes/terminal-product-convergence/tasks.md" in command
    assert not any(path.startswith("openspec/changes/archive/") for path in command)
    policy = tomllib.loads(
        (ROOT / ".config/quality/responsibility-map.toml").read_text(encoding="utf-8")
    )
    concern = next(item for item in policy["concerns"] if item["id"] == "markdown-lint")
    scope = next(item for item in policy["scopes"] if item["id"] == concern["scope"])
    assignments = responsibilities.audit(ROOT)["assignments"]
    assert {assignments[path] for path in command[8:]} <= set(scope["roles"])


def test_english_quality_uses_one_native_owner_and_current_scope() -> None:
    toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    locked = tomllib.loads((ROOT / "mise.lock").read_text(encoding="utf-8"))
    vale = locked["tools"]["aqua:vale-cli/vale"]
    assert len(vale) == 1
    assert vale[0]["version"] == toolchain["tools"]["aqua:vale-cli/vale"]
    selected = [
        command for command in governance._commands(online_links=False) if command[0] == "vale"
    ]
    assert len(selected) == 1
    command = selected[0]
    assert "--config=.config/quality/native/vale.ini" in command
    assert "--no-global" in command
    assert "--no-exit" not in command
    assert "README.md" in command
    assert "openspec/changes/terminal-product-convergence/tasks.md" in command
    assert not any(path.startswith("openspec/changes/archive/") for path in command)
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert not any(
        name.startswith(("textlint", "@textlint", "cspell")) for name in package["devDependencies"]
    )


@pytest.mark.repository_toolchain
def test_native_english_rule_tests_reject_a_rule_that_never_fires(tmp_path: Path) -> None:
    rule = ROOT / ".config/quality/native/vale/styles/Plain/Concise.yml"

    def check(directory: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                "vale",
                "--config=" + str(ROOT / ".config/quality/native/vale.ini"),
                "--no-global",
                "--no-color",
                "--output=JSON",
                "test",
                "--coverage",
                str(directory),
            ),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

    valid = check(rule.parent)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    report = json.loads(valid.stdout)
    assert report["failed"] == 0
    assert report["passed"] > 0
    assert all(item["passed"] for item in report["results"])
    assert not report.get("uncovered")
    rules = tmp_path / "Plain"
    rules.mkdir()
    content = yaml.safe_load(rule.read_text(encoding="utf-8"))
    content["tests"] = [
        {
            "name": "unchanged uncertainty",
            "input": "The decision may change when evidence is incomplete.",
            "want": "",
        }
    ]
    (rules / rule.name).write_text(yaml.safe_dump(content), encoding="utf-8")
    rejected = check(rules)
    assert rejected.returncode != 0, rejected.stdout + rejected.stderr
    assert "Plain.Concise" in json.loads(rejected.stdout)["uncovered"]


@pytest.mark.repository_toolchain
@pytest.mark.parametrize(
    ("source", "valid"),
    [
        ("# Fixture\n\nRead the current source.\n", True),
        ("# Fixture\n\nRead the the source.\n", False),
        ("# Fixture\n\n> Read the the source.\n", False),
        ("# Fixture\n\n| Rule |\n| --- |\n| Read the the source. |\n", False),
        ("# Fixture\n\nUse Gitlab.\n", False),
        ("# Fixture\n\n> Use Gitlab.\n", False),
        ("# Fixture\n\n| Tool |\n| --- |\n| Gitlab |\n", False),
        ("# Fixture\n\nUse GitLab and Nox in the worktree's namespace.\n", True),
        ("# Fixture\n\nRead the worktreex and namespacex.\n", False),
        ("# Fixture\n\nRead the noninteractivel output.\n", False),
        ("# Fixture\n\nIn order to verify, read the source.\n", False),
        ("# Fixture\n\n```text\nRead the the source in Gitlab.\n```\n", True),
        ("# Fixture\n\nRead `the the` field.\n", True),
        ("# Fixture\n\nRead [the source](https://example.com/veriffication).\n", True),
        ("# Fixture\n\nRead the veriffication result.\n", False),
        ("# Fixture\n\n> Read the veriffication result.\n", False),
        ("# Fixture\n\n| Rule |\n| --- |\n| Read the veriffication result. |\n", False),
        ("# Fixture\n\n```text\nveriffication\n```\n", True),
        ("# Fixture\n\nRead the `veriffication` field.\n", True),
    ],
)
def test_native_english_cli_checks_real_current_prose_without_source_writes(
    source: str, valid: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = "openspec/changes/fixture/proposal.md"
    archived = "openspec/changes/archive/fixture/proposal.md"
    with _test_repository(("README.md", current, archived, ".gitignore")) as root:
        (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (root / current).write_text(source, encoding="utf-8")
        (root / archived).write_text("Read the the veriffication result.\n", encoding="utf-8")
        (root / ".gitignore").write_text("private.md\n", encoding="utf-8")
        (root / "private.md").write_text("Read the the veriffication result.\n", encoding="utf-8")
        monkeypatch.setattr(governance, "ROOT", root)
        command = next(
            item for item in governance._commands(online_links=False) if item[0] == "vale"
        )
        config = "--config=.config/quality/native/vale.ini"
        native = tuple(
            "--config=" + str(ROOT / config.removeprefix("--config="))
            if argument == config
            else argument
            for argument in command
        )
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            native,
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        assert (completed.returncode == 0) is valid, completed.stdout + completed.stderr
        assert current in command
        assert archived not in command
        assert "private.md" not in command
        assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.repository_toolchain
@pytest.mark.parametrize(
    ("name", "source", "valid"),
    [
        ("README.md", "# Fixture\n\nClear prose.\n", True),
        ("README.md", "## Missing title\n", False),
        (
            "CHANGELOG.md",
            "# Changelog\n\n## One\n\n### Fixed\n\n- First.\n\n## Two\n\n### Fixed\n\n- Second.\n",
            True,
        ),
        ("README.md", "# Fixture\n\n## Same\n\n## Same\n", False),
        ("README.md", "# Fixture\n\nFirst.\n\n\nSecond.\n", False),
        ("README.md", "# Fixture\n\n<!-- markdownlint-disable -->\n\n## Same\n\n## Same\n", False),
        ("README.md", "# Fixture\n\n<!-- vale off -->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\n<!-- v&#97;le off -->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\n<!-- vale&#32;off -->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\n<!-- vale Vale.Repetition = NO -->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\n<!-- vale styles = Plain -->\n\nClear prose.\n", False),
        (
            "README.md",
            '# Fixture\n\n<!-- vale Vale.Repetition["the"] = NO -->\n\nClear prose.\n',
            False,
        ),
        ("README.md", "# Fixture\n\n<!--\nvale off\n-->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\nRead the <!-- vale off -->the source.\n", False),
        ("README.md", "# Fixture\n\n> <!-- vale off -->\n>\n> Clear prose.\n", False),
        ("README.md", "# Fixture\n\n- <!-- vale off -->\n  Clear prose.\n", False),
        ("README.md", "# Fixture\n\n| Rule |\n| --- |\n| <!-- vale off -->Clear prose. |\n", False),
        ("README.md", "# Fixture\n\n<!-- ordinary -->\n<!-- vale off -->\n\nClear prose.\n", False),
        ("README.md", "# Fixture\n\nRead `<!-- vale off -->` as literal code.\n", True),
        ("README.md", "# Fixture\n\n```html\n<!-- vale off -->\n```\n", True),
        ("README.md", "# Fixture\n\n<!-- source: current -->\n\nClear prose.\n", True),
        (
            "README.md",
            "# Fixture\n\n<!-- vale is the prose checker, not policy. -->\n\nClear prose.\n",
            True,
        ),
        (
            "openspec/changes/fixture/specs/topic/spec.md",
            "# Spec Delta\n\n## ADDED Requirements\n",
            True,
        ),
        (
            "openspec/changes/fixture/tasks.md",
            "# Tasks\n\n## 1. Work\n\n- [ ] Complete the task.\n",
            True,
        ),
        ("openspec/changes/fixture/proposal.md", "# Proposal\n\n## Why\n", True),
        ("openspec/changes/fixture/design.md", "# Design\n\n## Context\n", True),
        ("openspec/changes/fixture/specs/topic/spec.md", "## ADDED Requirements\n", False),
        ("openspec/changes/fixture/proposal.md", "Missing section.\n", False),
        ("README.md", "# Fixture\n\n" + "readable " * 12 + "prose.\n", False),
        ("README.md", "# Fixture\n\n[Missing]()\n", False),
        ("README.md", "# Fixture\n\n```\ncode\n```\n", False),
        ("README.md", "# Fixture\n\n- First.\n+ Second.\n", False),
        ("README.md", "# Fixture\n\n| One | Two |\n| --- | --- |\n| Only |\n", False),
        ("README.md", "# Fixture\n\n" + "a" * 120 + "\n", True),
        ("README.md", "# Fixture\n\n```python\n" + "a" * 120 + "\n```\n", True),
        ("README.md", "# " + "a" * 120 + "\n", True),
    ],
)
def test_native_markdown_rules_reject_real_invalid_carriers_without_source_writes(
    tmp_path: Path, name: str, source: str, valid: bool
) -> None:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    config = ROOT / ".config/quality/native/markdownlint-cli2.mjs"
    before = {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()}
    completed = subprocess.run(
        (
            "node",
            str(ROOT / "node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs"),
            "--config",
            str(config),
            "--no-globs",
            str(path),
        ),
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert (completed.returncode == 0) is valid, completed.stderr
    assert {item: item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()} == before


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("valid", [True, False])
def test_native_markdown_command_checks_the_declared_current_files(
    valid: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = "openspec/changes/fixture/proposal.md"
    archived = "openspec/changes/archive/fixture/proposal.md"
    with _test_repository(("README.md", current, archived, ".gitignore")) as root:
        (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (root / current).write_text(
            "# Proposal\n" if valid else "## Missing native title\n", encoding="utf-8"
        )
        (root / archived).write_text("Missing title.\n", encoding="utf-8")
        (root / ".gitignore").write_text("private.md\n", encoding="utf-8")
        (root / "private.md").write_text("Untracked invalid source.\n", encoding="utf-8")
        config = root / ".config/quality/native/markdownlint-cli2.mjs"
        config.parent.mkdir(parents=True)
        native_policy = (ROOT / config.relative_to(root)).as_uri()
        config.write_text(f'export {{ default }} from "{native_policy}";\n', encoding="utf-8")
        _git(root, "add", "--", ".gitignore")
        monkeypatch.setattr(governance, "ROOT", root)
        command = next(
            item for item in governance._commands(online_links=False) if "markdownlint-cli2" in item
        )
        native = (
            "node",
            str(ROOT / "node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs"),
            *command[5:],
        )
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            native,
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        assert (completed.returncode == 0) is valid, completed.stdout + completed.stderr
        assert "Linting: 2 files" in completed.stdout
        assert current in command
        assert archived not in command
        assert "private.md" not in command
        assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("suffix", [".json", ".jsonc"])
@pytest.mark.parametrize("state", ["formatted", "unformatted", "malformed"])
def test_governance_formatter_checks_tracked_current_json_without_writes(
    suffix: str, state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = f".config/settings{suffix}"
    archived = f"openspec/changes/archive/old/settings{suffix}"
    ignored = f"private{suffix}"
    with _test_repository(("README.md", current, archived, ".gitignore")) as root:
        (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (root / ".gitignore").write_text(f"{ignored}\n", encoding="utf-8")
        (root / ignored).write_text("untracked invalid data\n", encoding="utf-8")
        comma = "," if suffix == ".jsonc" else ""
        source = {
            "formatted": f'{{\n  "enabled": true{comma}\n}}\n',
            "unformatted": '{"enabled":true}\n',
            "malformed": '{"enabled":}\n',
        }[state]
        (root / current).write_text(source, encoding="utf-8")
        _git(root, "add", "--", ".gitignore")
        monkeypatch.setattr(governance, "ROOT", root)
        command = governance._commands(online_links=False)[0]
        config = command.index("--config") + 1
        ignore = command.index("--ignore-path") + 1
        native = (
            *command[:config],
            str(ROOT / command[config]),
            *command[config + 1 : ignore],
            str(ROOT / command[ignore]),
            *(str(root / path) for path in command[ignore + 1 :]),
        )
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        completed = subprocess.run(
            native,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        assert (completed.returncode == 0) is (state == "formatted"), completed.stdout
        assert str(root / current) in native
        assert str(root / archived) not in native
        assert str(root / ignored) not in native
        assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.repository_toolchain
def test_native_ignore_resolves_from_its_actual_configuration_directory() -> None:
    ignored = subprocess.run(
        [
            "npm",
            "exec",
            "--offline",
            "--",
            "prettier",
            "--file-info",
            ".mise/locks/npm/12.2.0/aube-lock.yaml",
            "--ignore-path",
            ".config/quality/native/prettier.ignore",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"ignored": true' in ignored.stdout
    authored = subprocess.run(
        [
            "npm",
            "exec",
            "--offline",
            "--",
            "prettier",
            "--file-info",
            ".gitlab-ci.yml",
            "--ignore-path",
            ".config/quality/native/prettier.ignore",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"ignored": false' in authored.stdout
