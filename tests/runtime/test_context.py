#!/usr/bin/env python3
"""Contracts for the portable deployed-runtime context."""

from __future__ import annotations

import ntpath
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy import errors  # noqa: E402
from codex_responses_proxy.runtime import context  # noqa: E402
from codex_responses_proxy.runtime import config  # noqa: E402


class TestRuntimeContext(unittest.TestCase):
    def test_context_is_the_single_deployed_runtime_projection(self):
        with (
            mock.patch.object(config, "home_dir", return_value="/portable/home"),
            mock.patch.object(config, "data_dir", return_value="/portable/payload"),
            mock.patch.object(config, "state_dir", return_value="/portable/state"),
        ):
            projected = context.create(python="/portable/python", port=8808)

        self.assertEqual(projected.home, "/portable/home")
        self.assertEqual(projected.install_dir, "/portable/payload")
        self.assertEqual(
            projected.proxy_script,
            "/portable/payload/codex_responses_proxy/listener/entrypoint.py",
        )
        self.assertEqual(
            projected.watchdog_script,
            "/portable/payload/codex_responses_proxy/supervision/watchdog.py",
        )
        self.assertEqual(projected.python, "/portable/python")
        self.assertEqual(projected.log_dir, "/portable/state")
        self.assertEqual(projected.port, 8808)

    def test_service_environment_derives_from_the_runtime_contract(self):
        projected = context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            proxy_script="/opt/proxy/listener.py",
            watchdog_script="/opt/proxy/watchdog.py",
            python="/opt/python",
            log_dir="/var/state/proxy",
            port=8808,
            responses_max_concurrency=19,
            upstream_timeout=45.0,
        )

        environment = projected.service_environment()

        self.assertEqual(environment[config.PROXY_PORT_ENV], "8808")
        self.assertEqual(environment[config.PROXY_SCRIPT_ENV], "/opt/proxy/listener.py")
        self.assertEqual(environment[config.PROXY_PYTHON_ENV], "/opt/python")
        self.assertEqual(environment[config.PROXY_LOG_ENV], "/var/state/proxy/proxy.log")
        self.assertEqual(environment[config.RESPONSES_MAX_CONCURRENCY_ENV], "19")
        self.assertEqual(environment[config.UPSTREAM_TIMEOUT_ENV], "45.0")

    def test_posix_projection_is_not_reinterpreted_by_a_windows_host(self):
        projected = context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            proxy_script="/opt/proxy/listener.py",
            watchdog_script="/opt/proxy/watchdog.py",
            python="/opt/python",
            log_dir="/var/state/proxy",
        )
        with (
            mock.patch.object(config.os, "path", ntpath),
            mock.patch.object(config, "home_dir", return_value="/portable/home"),
            mock.patch.object(config, "data_dir", return_value="/portable/payload"),
            mock.patch.object(config, "state_dir", return_value="/portable/state"),
        ):
            environment = projected.service_environment()
            created = context.create(python="/portable/python")
        self.assertEqual(environment[config.PROXY_LOG_ENV], "/var/state/proxy/proxy.log")
        self.assertEqual(
            created.proxy_script,
            "/portable/payload/codex_responses_proxy/listener/entrypoint.py",
        )

    def test_context_rejects_invalid_cli_overrides(self):
        invalid = (
            {"port": 0},
            {"port": 65536},
            {"proxy_log_max_bytes": 4095},
            {"proxy_log_backup_count": -1},
            {"watchdog_log_max_bytes": 64 * 1024 * 1024 + 1},
            {"watchdog_log_backup_count": 11},
        )
        with (
            mock.patch.object(config, "home_dir", return_value=os.sep),
            mock.patch.object(config, "data_dir", return_value="/payload"),
            mock.patch.object(config, "state_dir", return_value="/state"),
        ):
            for values in invalid:
                with self.subTest(values=values), self.assertRaises(errors.InstallError):
                    context.create(python="/python", **values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
