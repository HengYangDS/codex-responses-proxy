"""Black-box contracts for the installed proxy product interface."""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import runpy
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from codex_responses_proxy import errors
from codex_responses_proxy.cli import application

ROOT = Path(__file__).resolve().parents[2]


class ProductInterfaceContracts:
    """Keep one executable and one bounded public command grammar."""

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = application.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_exposes_exactly_the_declared_public_commands(self) -> None:
        code, stdout, stderr = self.invoke("--help")
        assert code == 0
        assert stderr == ""
        assert all(command in stdout for command in application.PUBLIC_COMMANDS)

    def test_empty_and_subcommand_help_are_successful(self) -> None:
        for arguments in ((), ("status", "--help")):
            code, stdout, stderr = self.invoke(*arguments)
            assert code == 0
            assert "Usage: codex-responses-proxy" in stdout
            assert stderr == ""

    def test_parse_failures_are_bounded_in_text_and_json(self) -> None:
        cases = (
            (("status", "--port", "not-an-integer"), False),
            (("--json",), True),
        )
        for arguments, as_json in cases:
            code, stdout, stderr = self.invoke(*arguments)
            assert code == 2
            assert stdout == ""
            if as_json:
                assert json.loads(stderr)["error"]["message"]
            else:
                assert "Action required" in stderr
                assert "Problem" in stderr
                assert "Next" in stderr
            assert "Traceback" not in stderr
            assert "Warning" not in stderr

    def test_module_boundary_delegates_exit_status(self, *, mocker) -> None:
        main = mocker.patch.object(application, "main", return_value=7)
        with pytest.raises(SystemExit, match="7"):
            runpy.run_module("codex_responses_proxy.cli.__main__", run_name="__main__")
        main.assert_called_once_with()

    def test_version_uses_release_owner_without_traceback_or_warning(self) -> None:
        code, stdout, stderr = self.invoke("version")
        assert code == 0
        assert stdout.strip() == application._release_version()
        assert stderr == ""

    def test_version_uses_installed_distribution_metadata_without_a_checkout_file(
        self, *, mocker
    ) -> None:
        expected = importlib.metadata.version("codex-responses-proxy")
        mocker.patch.object(application, "_source_version", return_value=None)
        code, stdout, stderr = self.invoke("version")
        assert code == 0
        assert stdout.strip() == expected
        assert stderr == ""

    def test_expected_errors_are_concise_and_machine_readable(self, *, mocker) -> None:
        mocker.patch.object(application, "dispatch", side_effect=ValueError("invalid value"))
        code, stdout, stderr = self.invoke("doctor", "--json")
        assert code == 2
        assert stdout == ""
        payload = json.loads(stderr)
        assert payload["error"]["message"] == "invalid value"
        assert "Traceback" not in stderr
        assert "Warning" not in stderr

    def test_unknown_command_is_a_clean_usage_error(self) -> None:
        code, stdout, stderr = self.invoke("unknown")
        assert code == 2
        assert stdout == ""
        assert "unknown command" in stderr
        assert "Traceback" not in stderr

    def test_human_error_has_problem_and_next_action_without_internal_leakage(
        self, *, mocker
    ) -> None:
        mocker.patch.object(application, "dispatch", side_effect=ValueError("listener unavailable"))

        code, stdout, stderr = self.invoke("status")

        assert code == 2
        assert stdout == ""
        assert "Problem" in stderr
        assert "listener unavailable" in stderr
        assert "Next" in stderr
        assert "codex-responses-proxy doctor" in stderr
        assert "python -m" not in stderr
        assert "Traceback" not in stderr

    def test_internal_assembly_failures_are_bounded_without_traceback(self, *, mocker) -> None:
        mocker.patch.object(
            application,
            "dispatch",
            side_effect=errors.ProductAssemblyError(
                "product installation is incomplete; reinstall the verified release"
            ),
        )

        code, stdout, stderr = self.invoke(
            "install",
            "--asset",
            "release.tar.gz",
            "--trust-anchor",
            "allowed-signers",
        )

        assert code == 2
        assert stdout == ""
        assert "product installation is incomplete" in stderr
        assert "reinstall the verified release" in stderr
        assert "codex_responses_proxy" not in stderr
        assert "Traceback" not in stderr
        assert "Warning" not in stderr

    def test_built_executable_contains_the_native_platform_adapter(self) -> None:
        executable = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        if executable is None:
            pytest.skip("native executable supplied by release session")
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [executable, "status", "--json"],
                cwd=home,
                env={"PATH": home, "HOME": home},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        assert result.returncode in {0, 2}, result.stderr
        assert "No module named" not in result.stderr
        assert "Traceback" not in result.stderr
        assert "Warning" not in result.stderr
        if result.stderr:
            assert "product installation is incomplete" not in result.stderr

    def test_built_executable_runs_without_python_on_path(self) -> None:
        executable = os.environ.get("CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE")
        if executable is None:
            pytest.skip("native executable supplied by release session")
        with tempfile.TemporaryDirectory() as empty_path:
            result = subprocess.run(
                [executable, "version"],
                cwd=empty_path,
                env={"PATH": empty_path, "HOME": os.environ.get("HOME", "")},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == application._release_version()
        assert result.stderr == ""
