"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from tests.quality.fixtures import ROOT
from tools.ci import project
from tools.quality import python_matrix


def test_native_release_verification_scope_has_no_governance_peer_prerequisites() -> None:
    """Native lifecycle jobs must not inherit the documentation tool graph."""
    source = (ROOT / "tests/quality/test_verification.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "tools.quality"
        for alias in node.names
    }
    assert "governance" not in imported
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "peer_link_project"
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("failed", [None, "governance", "quality"])
def test_full_verification_stops_before_failed_prerequisite_dependents(
    failed: str | None, tmp_path: Path
) -> None:
    fixture = tmp_path / "noxfile.py"
    marker = tmp_path / "observed.log"
    fixture.write_text(
        "import pathlib, runpy, nox, nox.registry\n"
        f"runpy.run_path({str(ROOT / 'noxfile.py')!r})\n"
        "nox.options.default_venv_backend = 'none'\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "def observe(session):\n"
        "    with marker.open('a') as stream:\n"
        "        stream.write(session.name + '\\n')\n"
        f"    if session.name == {failed!r}:\n"
        "        session.error('required prerequisite failed')\n"
        "for name in ('governance', 'quality'):\n"
        "    registered = nox.registry.get()[name]\n"
        "    registered.func = observe\n"
        "    registered.venv_backend = 'none'\n"
        "for version in ('3.13', '3.14'):\n"
        "    nox.session(python=False, name='tests-' + version)(observe)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "nox", "-f", str(fixture), "-s", "full"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert (completed.returncode == 0) is (failed is None), completed.stderr
    expected = (
        ["governance"]
        if failed == "governance"
        else ["governance", "quality"]
        if failed == "quality"
        else ["governance", "quality", "tests-3.13", "tests-3.14"]
    )
    assert marker.read_text().splitlines() == expected


@pytest.mark.parametrize("explicit", [False, True])
def test_matrix_cli_projects_to_exact_selected_output(explicit, tmp_path, monkeypatch):
    output = tmp_path / "output"
    args = (
        "--versions",
        str(ROOT / ".python-versions"),
        "--release",
        str(ROOT / ".python-release"),
        "--metadata",
        str(ROOT / "pyproject.toml"),
    )
    if explicit:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        python_matrix.main((*args, "--output", str(output)))
    else:
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        python_matrix.main(args)
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert json.loads(values["value"]) == (ROOT / ".python-versions").read_text().splitlines()
    assert values["release"] == (ROOT / ".python-release").read_text().strip()


def test_matrix_cli_requires_an_output_and_nonempty_unique_versions(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    with pytest.raises(SystemExit, match="output path is unavailable"):
        python_matrix.main(())
    versions = tmp_path / "versions"
    versions.write_text("")
    with pytest.raises(ValueError, match="matrix is unavailable"):
        python_matrix.write(
            versions=versions,
            release=ROOT / ".python-release",
            metadata=ROOT / "pyproject.toml",
            output=tmp_path / "output",
        )


def _load_yaml(path: Path) -> dict[str, object]:
    """Load a workflow as semantic data rather than presentation text."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert all(isinstance(key, str) for key in data)
    return {str(key): value for key, value in data.items()}


def _mapping(value: object) -> dict[str, object]:
    """Narrow one parsed configuration table for semantic assertions."""
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return {str(key): item for key, item in value.items()}


def _required_uv_version() -> str:
    metadata: object = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise TypeError("project metadata must be a table")
    tool = metadata.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    requirement: object = uv.get("required-version") if isinstance(uv, dict) else None
    if not isinstance(requirement, str) or not re.fullmatch(r"==\d+\.\d+\.\d+", requirement):
        raise AssertionError("uv must use an exact semantic version")
    return requirement.removeprefix("==")


def _native_run(
    root: Path, environment: dict[str, str], command: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    """Exercise the real selected toolchain without inheriting project discovery."""
    return subprocess.run(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def test_native_tool_diagnostics_are_utf8_even_under_an_ambient_legacy_codec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp936")
    probe = (
        "import sys; sys.stdout.buffer.write(bytes([0xE2, 0x82, 0xAC])); "
        "sys.stderr.buffer.write(bytes([0xE2, 0x82, 0xAC])); sys.exit(7)"
    )
    completed = _native_run(tmp_path, dict(os.environ), (sys.executable, "-c", probe))
    assert completed.returncode == 7
    assert completed.stdout == "\u20ac"
    assert completed.stderr == "\u20ac"


@pytest.fixture
def native_python_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Own a dependency-free native project under a nested path containing spaces."""
    root = tmp_path / "project with spaces" / "nested"
    root.mkdir(parents=True)
    for name in ("mise.toml", "mise.lock"):
        (root / name).write_bytes((ROOT / name).read_bytes())
    (root / "pyproject.toml").write_text(
        '[project]\nname = "native-environment-contract"\nversion = "0.0.0"\n'
        'requires-python = ">=3.12"\ndependencies = []\n\n'
        "[dependency-groups]\nquality = []\n\n"
        f'[tool.uv]\nrequired-version = "=={_required_uv_version()}"\n',
        encoding="utf-8",
    )
    global_config = tmp_path / "global.toml"
    global_config.write_text("", encoding="utf-8")
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("MISE_CONFIG", "MISE_GLOBAL", "MISE_CEILING", "UV_"))
        and name not in {"VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"}
    }
    environment.update(
        MISE_GLOBAL_CONFIG_FILE=str(global_config),
        MISE_SYSTEM_CONFIG_DIR=str(tmp_path / "absent-system"),
        MISE_CEILING_PATHS=str(tmp_path),
        MISE_TRUSTED_CONFIG_PATHS=str(tmp_path),
        MISE_AUTO_INSTALL="0",
        MISE_OFFLINE="1",
        UV_OFFLINE="true",
        UV_PYTHON_DOWNLOADS="never",
    )
    locked = _native_run(root, environment, ("mise", "exec", "--locked", "--", "uv", "lock"))
    assert locked.returncode == 0, locked.stderr
    assert "warning" not in locked.stderr.lower(), locked.stderr
    return root, environment


class TestVerificationContracts:
    """Keep verification on mature tools and the released product artifact."""

    @pytest.mark.parametrize("initial", [None, b"stale\n", b"current\n"])
    def test_ci_projection_checks_then_restores_only_owned_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, initial: bytes | None
    ) -> None:
        path = tmp_path / "nested" / "workflow.yml"
        foreign = tmp_path / "notes.txt"
        foreign.write_bytes(b"user owned\n")
        if initial is not None:
            path.parent.mkdir()
            path.write_bytes(initial)
        monkeypatch.setattr(project, "ROOT", tmp_path)
        monkeypatch.setattr(project, "PROJECTIONS", (project.Projection(path, "workflow"),))
        monkeypatch.setattr(project, "render", lambda _expression: b"current\n")

        if initial == b"current\n":
            project.main(())
        else:
            with pytest.raises(
                SystemExit, match=re.escape("projection drift: nested/workflow.yml")
            ):
                project.main(())
        assert (path.read_bytes() if path.exists() else None) == initial
        project.main(("--write",))
        assert path.read_bytes() == b"current\n"
        project.main(())
        assert foreign.read_bytes() == b"user owned\n"
        assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == {
            Path("notes.txt"),
            Path("nested"),
            Path("nested/workflow.yml"),
        }

    def test_ci_projection_renderer_binds_the_locked_repository(self, mocker) -> None:
        command = mocker.patch.object(
            project.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"yaml\n")
        )

        assert project.render("workflow") == b"yaml\n"

        args = command.call_args.args[0]
        assert args[:5] == ("mise", "exec", "--locked", "--", "cue")
        assert args[5:] == (
            "export",
            str(project.MODEL),
            "--expression",
            "workflow",
            "--out",
            "yaml",
        )
        assert command.call_args.kwargs["check"] is True
        assert command.call_args.kwargs["cwd"] == project.ROOT
        assert command.call_args.kwargs["env"]["MISE_CONFIG_FILE"] == str(project.MISE)
        command.side_effect = subprocess.CalledProcessError(1, args)
        with pytest.raises(subprocess.CalledProcessError):
            project.render("workflow")

    def test_pytest_is_the_only_behavior_test_runner(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        quality = metadata["dependency-groups"]["quality"]
        assert any(requirement.startswith("pytest==") for requirement in quality)
        assert any(requirement.startswith("pytest-mock==") for requirement in quality)
        pytest_config = tomllib.loads((ROOT / "pytest.toml").read_text(encoding="utf-8"))["pytest"]
        assert pytest_config["addopts"] == [
            "--import-mode=importlib",
            "--strict-config",
            "--strict-markers",
        ]
        assert pytest_config["cache_dir"] == ".cache/pytest"
        assert pytest_config["tmp_path_retention_policy"] == "none"
        assert pytest_config["tmp_path_retention_count"] == "0"
        assert pytest_config["filterwarnings"] == ["error"]
        assert (
            "native_distribution: requires the self-contained released executable"
            in pytest_config["markers"]
        )
        assert pytest_config["python_classes"] == ["Test*", "*Tests", "*Contracts"]
        assert pytest_config["testpaths"] == ["tests"]
        direct_test_commands = []
        for relative in (
            ".gitlab-ci.yml",
            ".github/workflows/admission.yml",
            ".github/workflows/verify.yml",
            "noxfile.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for lineno, line in enumerate(source.splitlines(), 1):
                if "python tests/" in line or '"-m", "tests.' in line:
                    direct_test_commands.append(f"{relative}:{lineno}:{line.strip()}")
        assert direct_test_commands == []
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        metadata_job = gitlab.split("verify-accepted-source:", 1)[1].split(
            "verify-release-tag:", 1
        )[0]
        assert "*install-uv" not in metadata_job
        assert (
            "uv sync --locked --group quality --python python --no-python-downloads" in metadata_job
        )
        assert "uv sync --locked --all-groups" not in metadata_job
        locked_python = "uv run --locked --no-sync --python python --no-python-downloads"
        assert "python tools/" not in metadata_job.replace(f"{locked_python} python tools/", "")
        assert f"{locked_python} python -m tools.release.metadata" in metadata_job
        assert f"{locked_python} python -m tools.quality.repository" in metadata_job
        assert "python -m pytest" not in metadata_job

    def test_uv_cache_writers_are_scoped_to_job_and_matrix_member(self) -> None:
        jobs = _mapping(_load_yaml(ROOT / ".github/workflows/verify.yml")["jobs"])
        writers = []
        for job_value in jobs.values():
            steps = _mapping(job_value)["steps"]
            assert isinstance(steps, list)
            for step_value in steps:
                step = _mapping(step_value)
                if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                    writers.append(_mapping(step.get("with", {})))
        assert writers
        for settings in writers:
            assert settings.get("cache-suffix") == "${{ github.job }}-${{ strategy.job-index }}"

    def test_forge_bootstrap_derives_uv_requirement_from_project_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirement = metadata["tool"]["uv"]["required-version"]
        assert requirement.startswith("==")

        for relative in (".github/workflows/verify.yml", ".gitlab-ci.yml"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert f"uv{requirement}" not in source
            assert re.search(r"\buv==\d", source) is None

        github = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        assert "astral-sh/setup-uv@" in github
        assert "version:" not in "\n".join(
            line for line in github.splitlines() if "setup-uv" in line or "uv-version" in line
        )

        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        uv_version = requirement.removeprefix("==")
        assert gitlab.count(f"ghcr.io/astral-sh/uv:{uv_version}-python") == 2
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["tools"]["uv"] == uv_version
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        job_scripts = {
            job: tuple(value.get("before_script", ()))
            for job, value in pipeline.items()
            if isinstance(value, dict) and "before_script" in value
        }
        assert job_scripts
        for job, scripts in job_scripts.items():
            metadata_checks = sum('["tool"]["uv"]["required-version"]' in item for item in scripts)
            if job.removesuffix("-review") in {
                "source-and-governance",
                "verify-macos-native",
                "verify-macos-native-review",
                "verify-windows-native",
                "verify-windows-native-review",
            }:
                assert metadata_checks == 0
                if job.removesuffix("-review") == "source-and-governance":
                    assert scripts[:3] == (
                        "apt-get update -qq",
                        "apt-get install -qq -y --no-install-recommends libatomic1",
                        "mise install --locked",
                    )
                    assert scripts[3:5] == ("npm ci --ignore-scripts", "npm audit signatures")
                else:
                    assert scripts[0] == "mise install --locked"
                    assert "mise exec --locked -- uv sync --locked --group quality" in scripts
                continue
            assert metadata_checks == 1
        assert 'UV_VERSION="${UV_VERSION#uv }"' in gitlab
        assert 'ACTUAL_UV_VERSION="${UV_VERSION%% *}"' in gitlab
        assert 'EXPECTED_UV_VERSION="${UV_REQUIREMENT#==}"' in gitlab
        assert "uv version mismatch: expected %s, actual %s" in gitlab
        assert "&install-uv" not in gitlab
        assert "*install-uv" not in gitlab
        assert "python -m pip install" not in gitlab

    @pytest.mark.parametrize(
        ("reported_version", "expected_returncode"),
        [
            (f"uv {_required_uv_version()} (x86_64-unknown-linux-musl)", 0),
            ("uv 9.9.9 (x86_64-unknown-linux-musl)", 1),
        ],
    )
    @pytest.mark.skipif(os.name == "nt", reason="GitLab executes this contract with POSIX sh")
    def test_gitlab_uv_contract_uses_the_machine_version_token(
        self, tmp_path: Path, reported_version: str, expected_returncode: int
    ) -> None:
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        verify_python = _mapping(pipeline["verify-python"])
        before_script = verify_python["before_script"]
        assert isinstance(before_script, list)
        script = next(
            item
            for item in before_script
            if isinstance(item, str)
            if '["tool"]["uv"]["required-version"]' in item
        )
        executable = tmp_path / "uv"
        executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{reported_version}'\n")
        executable.chmod(0o700)

        completed = subprocess.run(
            ["/bin/sh", "-eu", "-c", script],
            cwd=ROOT,
            env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
            check=False,
        )

        assert completed.returncode == expected_returncode

    def test_test_suite_has_no_unittest_compatibility_surface(self) -> None:
        offenders = []
        for path in sorted((ROOT / "tests").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Import)
                    and any(
                        alias.name == "unittest" or alias.name.startswith("unittest.")
                        for alias in node.names
                    )
                ) or (
                    isinstance(node, ast.ImportFrom)
                    and (
                        node.module == "unittest"
                        or (node.module is not None and node.module.startswith("unittest."))
                    )
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

    def test_root_pytest_toml_is_discovered_without_invocation_flags(self, tmp_path: Path) -> None:
        config = tmp_path / "pytest.toml"
        config.write_bytes((ROOT / "pytest.toml").read_bytes())
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_discovery.py").write_text(
            "class SampleContracts:\n    def test_native_discovery(self):\n        assert True\n",
            encoding="utf-8",
        )
        command = [sys.executable, "-m", "pytest", "--collect-only", "-vv"]
        environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        discovered = subprocess.run(
            command,
            cwd=tmp_path,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert discovered.returncode == 0, discovered.stderr
        assert f"rootdir: {tmp_path}" in discovered.stdout
        assert "configfile: pytest.toml" in discovered.stdout
        assert "1 test collected" in discovered.stdout

    def test_native_distribution_tests_are_explicit_and_release_owned(self) -> None:
        pytest_config = tomllib.loads((ROOT / "pytest.toml").read_text(encoding="utf-8"))["pytest"]
        assert (
            "native_distribution: requires the self-contained released executable"
            in pytest_config["markers"]
        )
        source = (ROOT / "tests/service/handoff/test_subprocess.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        pytestmark = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            )
        )
        assert isinstance(pytestmark.value, ast.List)
        markers = {ast.unparse(element) for element in pytestmark.value.elts}

        lifecycle = (ROOT / "tests/release/test_native_lifecycle.py").read_text(encoding="utf-8")
        lifecycle_tree = ast.parse(lifecycle)
        lifecycle_marks = next(
            node
            for node in lifecycle_tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            )
        )
        assert isinstance(lifecycle_marks.value, ast.List)
        assert not any("skipif" in ast.unparse(element) for element in lifecycle_marks.value.elts)
        assert "pytest.skip" not in lifecycle
        assert "pytest.mark.native_distribution" in markers
        assert "pytest.mark.usefixtures(preserve_native_host_projection.__name__)" in markers

    def test_quality_environment_is_repository_owned_and_locked(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = metadata["dependency-groups"]["quality"]
        names = [requirement.partition("==")[0] for requirement in requirements]
        assert set(names) == {
            "coverage",
            "deptry",
            "hatchling",
            "nox",
            "pyperf",
            "pytest",
            "pytest-mock",
            "pytest-subtests",
            "pyyaml",
            "ruff",
            "semver",
            "ty",
            "vulture",
        }
        assert len(names) == len(set(names))
        assert all(
            name and separator == "==" and version
            for name, separator, version in (
                requirement.partition("==") for requirement in requirements
            )
        )
        assert re.fullmatch(r"==\d+\.\d+\.\d+", metadata["tool"]["uv"]["required-version"])
        assert metadata["tool"]["uv"]["link-mode"] == "copy"
        assert (ROOT / "uv.lock").is_file()

        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["settings"] == {
            "idiomatic_version_file_enable_tools": [],
            "legacy_version_file": False,
            "locked": True,
            "not_found_system_fallback": False,
            "use_versions_host": False,
        }

    def test_native_release_tools_are_isolated_from_quality(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        groups = metadata["dependency-groups"]
        quality = {requirement.partition("==")[0] for requirement in groups["quality"]}
        release = {requirement.partition("==")[0] for requirement in groups["release"]}

        assert quality.isdisjoint(release)
        assert release == {"pyinstaller"}

    def test_developer_bootstrap_installs_product_and_quality_groups(self) -> None:
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        environment = toolchain["env"]
        assert environment["UV_PROJECT_ENVIRONMENT"] == "{{config_root}}/.venv"
        assert environment["VIRTUAL_ENV"] is False
        assert environment["UV_PYTHON"] == {
            "value": "{% if tools.python is defined %}{{exec(command='mise which python') | trim}}{% endif %}",
            "tools": True,
        }
        assert environment["PYTHONHOME"] is False
        assert environment["PYTHONPATH"] is False
        assert environment["PYTHONNOUSERSITE"] == "1"
        assert toolchain["tasks"]["bootstrap"]["run"] == [
            "uv sync --locked --all-groups",
            "npm ci --ignore-scripts",
            "npm audit signatures",
        ]
        assert toolchain["tasks"]["toolchain:verify"]["run"] == [
            f"mise which {name}"
            for name in (
                "node",
                "python",
                "uv",
                "npm",
                "cue",
                "taplo",
                "gitleaks",
                "actionlint",
                "lychee",
                "vale",
                "gh",
                "glab",
            )
        ]
        for task in ("bootstrap", "quick", "check", "native", "release"):
            assert toolchain["tasks"][task]["depends"] == ["toolchain:verify"]
        for relative in ("AGENTS.md", "CONTRIBUTING.md", "README.md"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert "mise run bootstrap" in source
            assert "mise run check" in source

    @pytest.mark.parametrize(
        ("task", "session"),
        [
            ("quick", "quick"),
            ("check", "full"),
            ("native", "release"),
            ("release", "release_asset"),
        ],
    )
    def test_developer_tasks_delegate_to_existing_verification(
        self, task: str, session: str
    ) -> None:
        toolchain = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
        assert toolchain["tasks"][task]["run"] == (
            "uv run --locked --group quality nox -s " + session
        )

    @pytest.mark.parametrize(
        ("relative", "source", "expected"),
        [
            (
                "src/codex_responses_proxy/probe.py",
                "def answer():\n    return 42\n",
                {"D100", "D103"},
            ),
            ("tools/probe.py", "def answer():\n    return 42\n", {"D100", "D103"}),
            ("noxfile.py", "def answer():\n    return 42\n", {"D100", "D103"}),
            ("tests/probe.py", "def answer():\n    return 42\n", set()),
            (
                "tests/probe.py",
                'def answer():\n    """Return the answer"""\n    return 42\n',
                {"D415"},
            ),
        ],
    )
    def test_native_ruff_applies_documentation_policy_by_semantic_role(
        self, relative: str, source: str, expected: set[str]
    ) -> None:
        result = subprocess.run(
            (
                "ruff",
                "check",
                "--config",
                str(ROOT / ".config/quality/native/ruff.toml"),
                "--output-format",
                "json",
                "--stdin-filename",
                str(ROOT / relative),
                "-",
            ),
            input=source,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == bool(expected), result.stderr
        assert {item["code"] for item in json.loads(result.stdout)} == expected

    def test_repository_declares_the_supported_python_matrix_once(self) -> None:
        github = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        supported = (ROOT / ".python-versions").read_text(encoding="utf-8").splitlines()
        uv_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
            "uv"
        ]["required-version"].removeprefix("==")
        image_pattern = re.compile(
            r"^ghcr\.io/astral-sh/uv:(?P<uv>\d+\.\d+\.\d+)-python"
            r"(?P<minor>\d+\.\d+)-trixie-slim"
            r"@sha256:(?P<digest>[0-9a-f]{64})$"
        )
        image_values = dict(
            re.findall(r"^  (UV_PYTHON_(?:FLOOR|LATEST)_IMAGE): (\S+)$", gitlab, re.MULTILINE)
        )
        assert set(image_values) == {"UV_PYTHON_FLOOR_IMAGE", "UV_PYTHON_LATEST_IMAGE"}
        floor_image = image_pattern.fullmatch(image_values["UV_PYTHON_FLOOR_IMAGE"])
        latest_image = image_pattern.fullmatch(image_values["UV_PYTHON_LATEST_IMAGE"])
        assert floor_image is not None
        assert latest_image is not None
        assert floor_image.group("uv") == uv_version
        assert latest_image.group("uv") == uv_version
        assert floor_image.group("minor") == supported[0]
        assert latest_image.group("minor") == supported[-1]
        assert "python -m tools.quality.python_matrix" in github
        assert 'print(f"floor={versions[0]}"' not in github
        assert 'print(f"latest={versions[-1]}"' not in github
        assert "needs.python-matrix.outputs.floor" in github
        assert "needs.python-matrix.outputs.latest" in github
        assert "needs.python-matrix.outputs.release" in github
        assert "python-version: ${{ needs.python-matrix.outputs.release }}" in github
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        assert _mapping(pipeline["default"])["image"] == {"name": "$UV_PYTHON_LATEST_IMAGE"}
        assert _mapping(pipeline["verify-python-quality"])["image"] == {
            "name": "$UV_PYTHON_FLOOR_IMAGE"
        }
        assert "LINUX_RELEASE_IMAGE" not in gitlab

    def test_release_collects_ctypes_as_source_outside_the_pyz_archive(self) -> None:
        """Avoid marshal identity drift in the Python 3.14 ``ctypes`` code object."""
        hook = ROOT / "tools" / "release" / "hooks" / "hook-ctypes.py"

        hook_tree = ast.parse(hook.read_text(encoding="utf-8"))
        executable_statements = hook_tree.body[1:]

        assert ast.get_docstring(hook_tree)
        assert len(executable_statements) == 1
        assignment = executable_statements[0]
        assert isinstance(assignment, ast.Assign)
        assert [target.id for target in assignment.targets if isinstance(target, ast.Name)] == [
            "module_collection_mode"
        ]
        assert ast.literal_eval(assignment.value) == "py"

    def test_forge_quality_jobs_use_the_locked_runner(self) -> None:
        github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        quality_job = github.split("  python-quality:", 1)[1].split("  native-assets:", 1)[0]
        assert "uv run --locked --group quality nox -s quality" in quality_job
        assert "uv sync --locked --only-group quality" not in quality_job
        assert "uv sync --locked --group quality --python python --no-python-downloads" in gitlab
        assert (
            "uv run --locked --no-sync --python python --no-python-downloads nox -s quality"
            in gitlab
        )
        assert "fetch-depth: 0" in quality_job
        assert "fetch-tags: true" in quality_job
        assert "python -m tools.quality.repository" not in quality_job
        assert "uv run --locked --group quality nox -s quality" in github
        assert "python -m tools.quality.repository" in gitlab

    def test_hosted_governance_tools_use_the_complete_locked_environment(self) -> None:
        github = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        source = gitlab.split("source-and-governance:", 1)[1].split("verify-python:", 1)[0]
        assert "uv sync --locked --group quality --python python --no-python-downloads" in source
        assert "uv sync --locked --all-groups" in github

    def test_performance_is_an_independent_locked_proof_surface(self) -> None:
        """Performance must be measured explicitly, not inferred from functional tests."""
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        quality = metadata["dependency-groups"]["quality"]
        assert "pyperf==2.10.0" in quality
        assert (ROOT / ".config/quality/policy/performance.toml").is_file()
        assert (ROOT / "tools/performance/benchmark.py").is_file()
        assert (ROOT / "tools/performance/memory.py").is_file()

        github = _load_yaml(ROOT / ".github/workflows/verify.yml")
        gitlab = _load_yaml(ROOT / ".gitlab-ci.yml")
        github_jobs = _mapping(github["jobs"])
        assert "performance" in github_jobs
        assert "uv run --locked --group quality nox -s performance" in str(
            github_jobs["performance"]
        )
        assert "verify-performance" in gitlab
        assert "nox -s performance" in str(gitlab["verify-performance"])


def test_package_manager_has_native_precedence_over_bundled_npm() -> None:
    configuration = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert configuration["tool_alias"]["npm"] == "npm:npm"
    assert configuration["tools"]["npm"] == "12.2.0"
    model = (ROOT / ".config/ci/pipeline.cue").read_text(encoding="utf-8")
    assert 'quality:         "python,uv,node,npm,' in model


def test_operator_forge_cli_is_bound_to_the_existing_toolchain() -> None:
    configuration = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert configuration["tools"]["glab"] == "1.120.0"
    assert "mise which glab" in configuration["tasks"]["toolchain:verify"]["run"]


def test_gitlab_linux_tags_bind_directly_without_recursive_aliases() -> None:
    """Each event selects a single-level native scheduling variable."""
    pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
    for name in (
        "source-and-governance",
        "verify-python",
        "verify-python-quality",
        "verify-performance",
    ):
        for suffix, selector in (
            ("", "$CODEX_RESPONSES_PROXY_GITLAB_LINUX_RUNNER_TAG"),
            ("-review", "$CODEX_RESPONSES_PROXY_GITLAB_LINUX_REVIEW_RUNNER_TAG"),
        ):
            job = _mapping(pipeline[name + suffix])
            assert job["tags"] == [selector]
            assert "CODEX_RESPONSES_PROXY_GITLAB_LINUX_JOB_TAG" not in str(job["rules"])
            event = str(job["rules"])
            assert ("merge_request_event" in event) == bool(suffix)
    assert "CODEX_RESPONSES_PROXY_GITLAB_LINUX_JOB_TAG" not in str(pipeline)


@pytest.mark.parametrize(
    "job_name",
    [
        "verify-macos-native",
        "verify-macos-native-review",
        "verify-windows-native",
        "verify-windows-native-review",
    ],
)
def test_native_ci_uses_the_single_tool_bound_environment(job_name: str) -> None:
    pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
    job = _mapping(pipeline[job_name])
    bootstrap = job["before_script"]
    scripts = job["script"]
    assert isinstance(bootstrap, list)
    assert isinstance(scripts, list)
    sync = [entry for entry in bootstrap if isinstance(entry, str) and "uv sync" in entry]
    assert sync == ["mise exec --locked -- uv sync --locked --group quality"]
    assert all(
        isinstance(entry, str) and "uv run --locked --group quality" in entry for entry in scripts
    )
    assert "--no-sync" not in str(scripts)
    assert "--python" not in str(scripts)
    assert (
        "mise exec --locked -- uv run --locked --group quality python -m pytest -q "
        "-m repository_toolchain tests/quality/test_verification.py"
    ) in scripts


@pytest.mark.repository_toolchain
def test_native_environment_resolves_the_locked_python_owner(
    native_python_project: tuple[Path, dict[str, str]],
) -> None:
    root, environment = native_python_project
    discovered = _native_run(root, environment, ("mise", "config", "--json"))
    assert discovered.returncode == 0, discovered.stderr
    assert {Path(item["path"]) for item in json.loads(discovered.stdout)} == {
        root / "mise.toml",
        root.parents[1] / "global.toml",
    }
    selected = _native_run(root, environment, ("mise", "env", "--json"))
    assert selected.returncode == 0, selected.stderr
    assert selected.stderr == ""
    native = json.loads(selected.stdout)
    assert Path(native["UV_PROJECT_ENVIRONMENT"]) == root / ".venv"
    interpreter = Path(native.get("UV_PYTHON", ""))
    assert interpreter.is_absolute(), native.get("UV_PYTHON")
    assert interpreter.is_file(), native.get("UV_PYTHON")
    resolved = _native_run(root, environment, ("mise", "which", "python"))
    assert resolved.returncode == 0, resolved.stderr
    assert interpreter.samefile(resolved.stdout.strip())


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("tools", ["python,uv", "gh"])
def test_native_environment_binding_applies_only_to_the_selected_tool_plane(
    native_python_project: tuple[Path, dict[str, str]], tools: str
) -> None:
    root, environment = native_python_project
    observed = _native_run(
        root, {**environment, "MISE_ENABLE_TOOLS": tools}, ("mise", "env", "--json")
    )
    assert observed.returncode == 0, observed.stderr
    assert observed.stderr == ""
    selected = json.loads(observed.stdout)
    if tools == "gh":
        assert not selected.get("UV_PYTHON"), selected.get("UV_PYTHON")
    else:
        assert Path(selected["UV_PYTHON"]).is_absolute()
    assert Path(selected["UV_PROJECT_ENVIRONMENT"]) == root / ".venv"


@pytest.mark.repository_toolchain
@pytest.mark.parametrize("consumer", ["proof", "native-ci"])
@pytest.mark.parametrize("state", ["ready", "missing", "stale", "stale-lock"])
def test_native_uv_execution_normalizes_only_its_owned_environment(
    native_python_project: tuple[Path, dict[str, str]], consumer: str, state: str
) -> None:
    root, environment = native_python_project
    profile = tomllib.loads((ROOT / ".ethos/profile.toml").read_text(encoding="utf-8"))
    if consumer == "proof":
        command = profile["proof"]["gates"][0]["command"]
        prefix = tuple(command[: command.index("nox")])
    else:
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        scripts = _mapping(pipeline["verify-windows-native"])["script"]
        assert isinstance(scripts, list)
        command = next(item for item in scripts if isinstance(item, str) and "nox -s" in item)
        prefix = tuple(command.split(" nox -s", 1)[0].split())
    local = root / ".venv"
    if state != "missing":
        created = _native_run(
            root, environment, ("mise", "exec", "--locked", "--", "uv", "venv", str(local))
        )
        assert created.returncode == 0, created.stderr
    if state == "stale":
        config = local / "pyvenv.cfg"
        config.write_text(
            re.sub(r"version_info = [^\n]+", "version_info = 0.0.0", config.read_text()),
            encoding="utf-8",
        )
    if state == "stale-lock":
        metadata = root / "pyproject.toml"
        metadata.write_text(metadata.read_text().replace('version = "0.0.0"', 'version = "0.0.1"'))
    preserved = {
        name: (root / name).read_bytes()
        for name in ("mise.toml", "mise.lock", "pyproject.toml", "uv.lock")
    }
    probe = (
        "import json, sys; "
        "print(json.dumps({'version': list(sys.version_info[:3]), 'prefix': sys.prefix}))"
    )
    observed = _native_run(root, environment, (*prefix, "python", "-c", probe))
    if state == "stale-lock":
        assert observed.returncode != 0, observed.stdout
        assert observed.stdout == ""
    else:
        assert observed.returncode == 0, observed.stderr
        assert "warning" not in observed.stderr.lower(), observed.stderr
        actual = json.loads(observed.stdout)
        expected = tomllib.loads(preserved["mise.toml"].decode())["tools"]["python"]
        assert actual["version"] == [int(part) for part in expected.split(".")]
        assert Path(actual["prefix"]) == local
    assert {name: (root / name).read_bytes() for name in preserved} == preserved


@pytest.mark.repository_toolchain
def test_native_uv_preserves_a_ready_environment_between_sequential_consumers(
    native_python_project: tuple[Path, dict[str, str]],
) -> None:
    root, environment = native_python_project
    prefix = ("mise", "exec", "--locked", "--", "uv")
    synchronized = _native_run(
        root, environment, (*prefix, "sync", "--locked", "--group", "quality")
    )
    assert synchronized.returncode == 0, synchronized.stderr
    local = root / ".venv"
    config = local / "pyvenv.cfg"
    original = config.read_bytes()
    marker = local / "owned-environment-marker"
    marker.write_bytes(b"preserve the ready environment\n")
    for _ in range(2):
        observed = _native_run(
            root,
            environment,
            (*prefix, "run", "--locked", "--group", "quality", "python", "-c", "print('ready')"),
        )
        assert observed.returncode == 0, observed.stderr
        assert observed.stdout.strip() == "ready"
        assert "Removed virtual environment" not in observed.stderr
        assert config.read_bytes() == original
        assert marker.read_bytes() == b"preserve the ready environment\n"
