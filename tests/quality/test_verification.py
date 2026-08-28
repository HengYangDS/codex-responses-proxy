"""Contract tests for the repository-owned Python quality policy."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from tests.quality.fixtures import ROOT
from tests.quality.fixtures import load as _load


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


class TestVerificationContracts:
    """Keep verification on mature tools and the released product artifact."""

    def test_pytest_is_the_only_behavior_test_runner(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        quality = metadata["dependency-groups"]["quality"]
        assert any(requirement.startswith("pytest==") for requirement in quality)
        assert any(requirement.startswith("pytest-mock==") for requirement in quality)
        pytest_config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
        assert "addopts = --import-mode=importlib --strict-config --strict-markers" in pytest_config
        assert "cache_dir = .cache/pytest" in pytest_config
        assert "filterwarnings = error" in pytest_config
        assert (
            "native_distribution: requires the self-contained released executable" in pytest_config
        )
        assert "python_classes = Test* *Tests *Contracts" in pytest_config
        assert "testpaths = tests" in pytest_config
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

    def test_forge_bootstrap_derives_uv_requirement_from_project_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirement = metadata["tool"]["uv"]["required-version"]
        assert requirement.startswith("==")

        for relative in (".github/workflows/verify.yml", ".gitlab-ci.yml"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert f"uv{requirement}" not in source
            assert re.search(r"\buv==\d", source) is None

        github = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        assert "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" in github
        assert "version:" not in "\n".join(
            line for line in github.splitlines() if "setup-uv" in line or "uv-version" in line
        )

        gitlab = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        uv_version = requirement.removeprefix("==")
        assert gitlab.count(f"ghcr.io/astral-sh/uv:{uv_version}-python") == 2
        pipeline = _load_yaml(ROOT / ".gitlab-ci.yml")
        job_scripts = {
            job: tuple(value.get("before_script", ()))
            for job, value in pipeline.items()
            if isinstance(value, dict) and "before_script" in value
        }
        assert job_scripts
        for job, scripts in job_scripts.items():
            metadata_checks = sum('["tool"]["uv"]["required-version"]' in item for item in scripts)
            if job == "source-and-governance":
                assert metadata_checks == 0
                assert scripts[0] == "mise install --locked"
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

    def test_nox_tests_build_and_install_the_wheel_before_running_pytest(self) -> None:
        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert set(functions) >= {
            "_build_wheel",
            "_install_wheel",
            "_assert_installed_product",
        }
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
        assert any(
            "--cache-dir" in command
            for command in commands
            if command[:3] == ("uv", "build", "--wheel")
        )
        assert any(command[:3] == ("uv", "pip", "install") for command in commands)
        install_source = ast.get_source_segment(source, functions["_install_wheel"]) or ""
        assert '"--no-deps"' not in install_source
        tests_calls = {
            node.func.id
            for node in ast.walk(functions["tests"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert tests_calls >= {
            "_build_wheel",
            "_install_wheel",
            "_assert_installed_product",
        }
        assert "_build_executable" not in tests_calls
        tests_source = ast.get_source_segment(source, functions["tests"]) or ""
        quality_source = ast.get_source_segment(source, functions["quality"]) or ""
        assert "PYTEST_CONFIG" not in source
        assert 'ROOT / "pytest.ini"' not in source
        assert 'f"--rootdir={ROOT}"' not in source
        assert '"compileall",' in tests_source
        for owner_source in (tests_source, quality_source):
            assert '"not native_distribution and not repository_toolchain"' in owner_source
        for owner_source in (tests_source, quality_source):
            assert 'product_identity.environment_name("EXECUTABLE")' in owner_source
        assert "PYTHONPATH=src" not in source

    def test_nox_tool_environment_contains_product_runtime_dependencies(self) -> None:
        """Repository tools must run from one lock-derived, self-contained environment."""

        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        install_tools = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_install_tools"
        )
        install_source = ast.get_source_segment(source, install_tools) or ""
        groups = install_tools.args.vararg
        assert groups is not None
        assert groups.arg == "groups"
        assert 'groups or ("quality",)' in install_source
        assert 'command.extend(("--group", group))' in install_source
        assert '"--only-group"' not in install_source

    def test_nox_release_exports_one_manifest_bound_native_asset_set(self) -> None:
        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        release_source = ast.get_source_segment(source, functions["release"]) or ""
        assert '"tests/cli/test_interface.py"' in release_source
        assert '"tests/service/handoff/test_subprocess.py"' in release_source
        assert 'product_identity.environment_name("NATIVE_EXECUTABLE"): str(executable)' in (
            release_source
        )
        assert '"-m", "tests.' not in release_source
        release_calls = {
            node.func.id
            for node in ast.walk(functions["release"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_package_release_asset" in release_calls
        package_source = ast.get_source_segment(source, functions["_package_release_asset"]) or ""
        assert "tools.release.assets" in package_source
        assert "--bundle" in package_source
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
        assert native_build_owners == {"_build_native_candidate"}

    def test_linux_asset_construction_defers_service_acceptance_to_the_native_host(
        self,
    ) -> None:
        """Keep containerized construction independent of a host service manager."""

        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        asset_source = ast.get_source_segment(source, functions["release_asset"]) or ""

        assert '"tests/cli/test_interface.py"' in asset_source
        assert '"tests/service/handoff/test_subprocess.py"' in asset_source
        assert '"tests/release/test_native_lifecycle.py"' not in asset_source
        assert "_package_release_asset" in asset_source

    def test_release_compatibility_uses_one_verified_published_predecessor(
        self,
    ) -> None:
        """A release candidate must upgrade a real signed predecessor, never a relabeled build."""

        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        compatibility = functions["release_compatibility"]
        compatibility_source = ast.get_source_segment(source, compatibility) or ""
        lifecycle = (ROOT / "tests/release/test_native_lifecycle.py").read_text(encoding="utf-8")

        assert 'product_identity.environment_name("PREVIOUS_RELEASE_ASSET")' in (
            compatibility_source
        )
        assert 'product_identity.environment_name("PREVIOUS_RELEASE_TRUST_ANCHOR")' in (
            compatibility_source
        )
        assert '"tests/release/test_native_compatibility.py"' in compatibility_source
        assert "_previous_patch" not in lifecycle

    def test_native_distribution_tests_are_explicit_and_release_owned(self) -> None:
        pytest_config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
        assert (
            "native_distribution: requires the self-contained released executable" in pytest_config
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
            "locked": True,
        }

    def test_native_release_tools_are_isolated_from_quality(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        groups = metadata["dependency-groups"]
        quality = {requirement.partition("==")[0] for requirement in groups["quality"]}
        release = {requirement.partition("==")[0] for requirement in groups["release"]}

        assert quality.isdisjoint(release)
        assert release == {"pyinstaller"}

        noxfile = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        release_session = noxfile.split("def release(session: nox.Session)", 1)[1].split(
            "\ndef _install_tools", 1
        )[0]
        assert '_install_tools(session, "quality", "release")' in release_session

    def test_developer_bootstrap_installs_product_and_quality_groups(self) -> None:
        for relative in ("AGENTS.md", "CONTRIBUTING.md", "README.md"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            assert "uv sync --locked --all-groups" in source
            assert "uv sync --locked --only-group quality" not in source

    def test_repository_declares_the_supported_python_matrix_once(self) -> None:
        assert (ROOT / ".python-versions").read_text(encoding="utf-8") == "3.12\n3.13\n3.14\n"
        assert (ROOT / ".python-release").read_text(encoding="utf-8") == "3.14.7\n"
        assert not (ROOT / ".python-version").exists()
        noxfile = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        assert 'PYTHONS = tuple((ROOT / ".python-versions").read_text' in noxfile
        assert "MIN_PYTHON, *_, MAX_PYTHON = PYTHONS" in noxfile
        assert 'RELEASE_PYTHON = (ROOT / ".python-release").read_text' in noxfile
        assert '("3.12", "3.13", "3.14")' not in noxfile
        assert '@nox.session(python="3.12")' not in noxfile
        assert '@nox.session(python="3.14")' not in noxfile
        assert '"--python-version",\n        "3.12"' not in noxfile
        for session in ("quick", "full", "release"):
            assert f"def {session}(session: nox.Session)" in noxfile

        tree = ast.parse(noxfile)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        full_source = ast.get_source_segment(noxfile, functions["full"]) or ""
        assert 'session.notify("governance")' in full_source
        assert 'session.notify("quick")' not in full_source
        assert "for python in PYTHONS[1:]" in full_source
        assert 'session.notify(f"tests-{python}")' in full_source
        assert 'session.notify("tests",' not in full_source

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

    def test_release_black_box_commands_are_isolated_from_the_live_installation(
        self,
    ) -> None:
        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_without_python"
        )
        owner_source = ast.get_source_segment(source, function) or ""

        assert 'product_identity.environment_name("HOME"): str(sandbox / "payload")' in (
            owner_source
        )
        assert 'product_identity.environment_name("STATE_HOME"): str(sandbox / "state")' in (
            owner_source
        )
        assert '"HOME": str(sandbox / "home")' in owner_source
        assert '"USERPROFILE": str(sandbox / "home")' in owner_source
        assert '"HOME": str(Path.home())' not in owner_source
        acceptance = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_accept_native_executable"
        )
        acceptance_source = ast.get_source_segment(source, acceptance) or ""
        assert "isolated_listener=True" in acceptance_source

    def test_release_collects_ctypes_as_source_outside_the_pyz_archive(self) -> None:
        """Avoid marshal identity drift in the Python 3.14 ``ctypes`` code object."""

        source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        hook = ROOT / "tools" / "release" / "hooks" / "hook-ctypes.py"

        assert '"--additional-hooks-dir"' in source
        assert 'ROOT / "tools/release/hooks"' in source
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

    def test_release_runtime_uses_the_session_interpreter(self, mocker: MockerFixture) -> None:
        """Compare the release session interpreter, not the Nox launcher."""

        module = _load("codex_responses_proxy_noxfile", "noxfile.py")
        session = mocker.Mock()
        session.run.return_value = "3.14.7\n"

        module._assert_release_runtime(session)

        session.run.assert_called_once_with(
            "python",
            "-c",
            "import platform; print(platform.python_version())",
            env=module._environment(),
            silent=True,
        )
        session.run.return_value = "3.14.6\n"
        session.error.side_effect = RuntimeError
        with pytest.raises(RuntimeError):
            module._assert_release_runtime(session)

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

        nox_source = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        assert "def performance(session: nox.Session)" in nox_source
        assert '"tools.performance.benchmark"' in nox_source
        assert '"tools.performance.memory"' in nox_source
        assert '"tools.performance.verify"' in nox_source

        github = _load_yaml(ROOT / ".github/workflows/verify.yml")
        gitlab = _load_yaml(ROOT / ".gitlab-ci.yml")
        github_jobs = _mapping(github["jobs"])
        assert "performance" in github_jobs
        assert "uv run --locked --group quality nox -s performance" in str(
            github_jobs["performance"]
        )
        assert "verify-performance" in gitlab
        assert "nox -s performance" in str(gitlab["verify-performance"])
