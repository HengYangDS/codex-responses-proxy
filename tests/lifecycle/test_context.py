"""Contracts for the portable deployed-runtime context."""

from __future__ import annotations

import ntpath
import os
from pathlib import Path

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context
from codex_responses_proxy.relay import config
from codex_responses_proxy.service import runtime
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestRuntimeContext:
    def test_current_executable_prefers_frozen_then_installed_then_invocation(
        self, *, mocker
    ) -> None:
        frozen = mocker.patch.object(runtime.sys, "frozen", True, create=True)
        mocker.patch.object(runtime.sys, "executable", "/bundle/proxy")
        assert runtime.current_executable() == os.path.abspath("/bundle/proxy")
        mocker.stop(frozen)

        mocker.patch.object(runtime.shutil, "which", return_value="/installed/proxy")
        assert runtime.current_executable() == os.path.abspath("/installed/proxy")
        mocker.patch.object(runtime.shutil, "which", return_value=None)
        mocker.patch.object(runtime.sys, "argv", ["relative-proxy"])
        assert runtime.current_executable() == os.path.abspath("relative-proxy")

    def test_default_port_is_8792_and_explicit_override_remains_configurable(self):
        assert config.DEFAULT_PORT == 8792
        assert config.listener_port({}) == 8792
        assert config.listener_port({config.PROXY_PORT_ENV: "8808"}) == 8808

        projected = context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            executable="/opt/proxy/bin/codex-responses-proxy",
            log_dir="/var/state/proxy",
            port=8808,
        )
        assert projected.service_environment()[config.PROXY_PORT_ENV] == "8808"

    def test_context_is_the_single_deployed_runtime_projection(self, *, mocker):
        mocker.patch.object(config, "home_dir", return_value="/portable/home")
        mocker.patch.object(config, "data_dir", return_value="/portable/payload")
        mocker.patch.object(config, "state_dir", return_value="/portable/state")
        projected = context.create(executable="/portable/bin/codex-responses-proxy", port=8808)

        assert projected.home == "/portable/home"
        assert projected.install_dir == "/portable/payload"
        assert projected.executable == "/portable/bin/codex-responses-proxy"
        assert projected.log_dir == "/portable/state"
        assert projected.port == 8808

    def test_service_environment_derives_from_the_runtime_contract(self):
        projected = context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            executable="/opt/proxy/bin/codex-responses-proxy",
            log_dir="/var/state/proxy",
            port=8808,
            upstream_timeout=45.0,
        )

        environment = projected.service_environment()

        assert environment[config.PROXY_PORT_ENV] == "8808"
        assert "CODEX_RESPONSES_PROXY_EXECUTABLE" not in environment
        assert environment[config.PROXY_LOG_ENV] == "/var/state/proxy/proxy.log"
        assert environment[config.UPSTREAM_TIMEOUT_ENV] == "45.0"

    def test_posix_projection_is_not_reinterpreted_by_a_windows_host(self, *, mocker):
        projected = context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            executable="/opt/proxy/bin/codex-responses-proxy",
            log_dir="/var/state/proxy",
        )
        mocker.patch.object(config.os, "path", ntpath)
        mocker.patch.object(config, "home_dir", return_value="/portable/home")
        mocker.patch.object(config, "data_dir", return_value="/portable/payload")
        mocker.patch.object(config, "state_dir", return_value="/portable/state")
        environment = projected.service_environment()
        created = context.create(executable="/portable/bin/codex-responses-proxy")
        assert environment[config.PROXY_LOG_ENV] == "/var/state/proxy/proxy.log"
        assert created.executable == "/portable/bin/codex-responses-proxy"

    def test_path_projection_preserves_windows_roots_and_absolutizes_relative_overrides(
        self,
    ) -> None:
        assert config.path_join(r"C:\portable\proxy", "state") == r"C:\portable\proxy\state"
        relative = config._absolute_override({config.HOME_ENV: "payload"}, config.HOME_ENV)
        assert relative == str((Path.cwd() / "payload").resolve())

    def test_native_runtime_projects_only_the_installed_executable(self, *, mocker):
        mocker.patch.object(config, "home_dir", return_value="/portable/home")
        mocker.patch.object(config, "data_dir", return_value="/portable/payload")
        mocker.patch.object(config, "state_dir", return_value="/portable/state")
        projected = context.create(executable="/portable/bin/codex-responses-proxy", port=8808)

        assert projected.executable == "/portable/bin/codex-responses-proxy"
        assert "python" not in projected.__dataclass_fields__
        assert "proxy_script" not in projected.__dataclass_fields__
        assert "watchdog_script" not in projected.__dataclass_fields__
        environment = projected.service_environment()
        assert "CODEX_RESPONSES_PROXY_PROXY_PYTHON" not in environment
        assert "CODEX_RESPONSES_PROXY_PROXY_SCRIPT" not in environment

    def test_context_rejects_invalid_cli_overrides(self, subtests, *, mocker):
        invalid = (
            {"port": 0},
            {"port": 65536},
            {"proxy_log_max_bytes": 4095},
            {"proxy_log_backup_count": -1},
            {"watchdog_log_max_bytes": 64 * 1024 * 1024 + 1},
            {"watchdog_log_backup_count": 11},
        )
        mocker.patch.object(config, "home_dir", return_value=os.sep)
        mocker.patch.object(config, "data_dir", return_value="/payload")
        mocker.patch.object(config, "state_dir", return_value="/state")
        for values in invalid:
            with subtests.test(values=values), pytest.raises(errors.InstallError):
                context.create(executable="/portable/bin/codex-responses-proxy", **values)
