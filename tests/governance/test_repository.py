#!/usr/bin/env python3
"""Repository governance, release-metadata, and privacy-surface contracts."""

from __future__ import annotations

import ntpath
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.commands import install  # noqa: E402
from codex_responses_proxy.runtime import context as runtime_context  # noqa: E402
from codex_responses_proxy import errors  # noqa: E402
from codex_responses_proxy.runtime import config as runtime_config  # noqa: E402


class TestInstallationInputValidation(unittest.TestCase):
    def test_home_dir_expands_the_runtime_user_home(self):
        with mock.patch.object(runtime_config.os.path, "expanduser", return_value="/portable/home"):
            self.assertEqual(runtime_config.home_dir(), "/portable/home")

    def test_product_roots_are_portable_and_explicitly_overridable(self):
        cases = (
            (
                {"CODEX_RESPONSES_PROXY_HOME": "~/payload"},
                {"os.name": "posix", "sys.platform": "linux"},
                ("payload", ".local/state/codex-responses-proxy"),
            ),
            (
                {"CODEX_RESPONSES_PROXY_STATE_HOME": "~/state"},
                {"os.name": "posix", "sys.platform": "darwin"},
                ("Library/Application Support/codex-responses-proxy", "state"),
            ),
            (
                {"LOCALAPPDATA": "/portable/local"},
                {"os.name": "nt", "sys.platform": "win32"},
                (
                    "/portable/local/codex-responses-proxy",
                    "/portable/local/codex-responses-proxy/state",
                ),
            ),
            (
                {"XDG_DATA_HOME": "/portable/data", "XDG_STATE_HOME": "/portable/state"},
                {"os.name": "posix", "sys.platform": "linux"},
                ("/portable/data/codex-responses-proxy", "/portable/state/codex-responses-proxy"),
            ),
        )
        for environment, platform, expected in cases:
            with (
                self.subTest(platform=platform),
                mock.patch.dict(runtime_config.os.environ, environment, clear=True),
                mock.patch.object(runtime_config.os, "name", platform["os.name"]),
                mock.patch.object(runtime_config.sys, "platform", platform["sys.platform"]),
                mock.patch.object(runtime_config, "home_dir", return_value="/home/tester"),
            ):
                self.assertTrue(runtime_config.data_dir().endswith(expected[0]))
                self.assertTrue(runtime_config.state_dir().endswith(expected[1]))

    def test_runtime_configuration_is_loopback_only_and_rejects_invalid_ports(self):
        self.assertEqual(runtime_config.listener_host(), "127.0.0.1")
        for value in ("0", "65536", "not-a-port"):
            with (
                self.subTest(value=value),
                self.assertRaises(runtime_config.ConfigurationError),
            ):
                runtime_config.listener_port({runtime_config.PROXY_PORT_ENV: value})

    def test_runtime_log_defaults_share_the_portable_state_owner(self):
        with (
            mock.patch.dict(runtime_config.os.environ, {}, clear=True),
            mock.patch.object(runtime_config, "state_dir", return_value="/portable/state"),
        ):
            self.assertEqual(runtime_config.proxy_log_path(), "/portable/state/proxy.log")
            self.assertEqual(runtime_config.watchdog_log_path(), "/portable/state/watchdog.log")

    def test_runtime_path_overrides_expand_against_the_supplied_home(self):
        environment = {
            "HOME": "/portable/home",
            runtime_config.HOME_ENV: "~/payload",
            runtime_config.STATE_HOME_ENV: "~/state",
        }
        self.assertEqual(runtime_config.data_dir(environment), "/portable/home/payload")
        self.assertEqual(runtime_config.state_dir(environment), "/portable/home/state")

    def test_posix_overrides_are_not_reinterpreted_by_a_windows_host(self):
        environment = {
            "HOME": "/portable/home",
            runtime_config.HOME_ENV: "~/payload",
            runtime_config.STATE_HOME_ENV: "/portable/state",
        }
        with mock.patch.object(runtime_config.os, "path", ntpath):
            self.assertEqual(runtime_config.data_dir(environment), "/portable/home/payload")
            self.assertEqual(runtime_config.state_dir(environment), "/portable/state")

    def test_service_projection_is_derived_from_one_runtime_contract(self):
        context = runtime_context.RuntimeContext(
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
        environment = context.service_environment()
        self.assertEqual(
            set(environment),
            {
                runtime_config.PROXY_PORT_ENV,
                runtime_config.PROXY_PYTHON_ENV,
                runtime_config.PROXY_SCRIPT_ENV,
                runtime_config.PROXY_LOG_ENV,
                runtime_config.WATCHDOG_LOG_ENV,
                runtime_config.PROXY_LOG_MAX_BYTES_ENV,
                runtime_config.PROXY_LOG_BACKUP_COUNT_ENV,
                runtime_config.WATCHDOG_LOG_MAX_BYTES_ENV,
                runtime_config.WATCHDOG_LOG_BACKUP_COUNT_ENV,
                runtime_config.RESPONSES_MAX_CONCURRENCY_ENV,
                runtime_config.RESPONSES_QUEUE_TIMEOUT_ENV,
                runtime_config.UPSTREAM_TIMEOUT_ENV,
                runtime_config.UPSTREAM_READ_TIMEOUT_ENV,
                runtime_config.WATCHDOG_INTERVAL_ENV,
                runtime_config.WATCHDOG_MAX_BACKOFF_ENV,
            },
        )
        self.assertEqual(runtime_config.load(environment).listener, ("127.0.0.1", 8808))
        self.assertEqual(environment[runtime_config.RESPONSES_MAX_CONCURRENCY_ENV], "19")
        self.assertEqual(environment[runtime_config.UPSTREAM_TIMEOUT_ENV], "45.0")

    def test_runtime_settings_have_one_owner_and_strict_validation(self):
        environment = {
            runtime_config.PROXY_PORT_ENV: "8801",
            runtime_config.PROXY_LOG_MAX_BYTES_ENV: "8192",
            runtime_config.PROXY_LOG_BACKUP_COUNT_ENV: "4",
            runtime_config.WATCHDOG_LOG_MAX_BYTES_ENV: "12288",
            runtime_config.WATCHDOG_LOG_BACKUP_COUNT_ENV: "5",
            runtime_config.RESPONSES_MAX_CONCURRENCY_ENV: "17",
            runtime_config.RESPONSES_QUEUE_TIMEOUT_ENV: "2.5",
            runtime_config.UPSTREAM_TIMEOUT_ENV: "30",
            runtime_config.UPSTREAM_READ_TIMEOUT_ENV: "15.5",
            runtime_config.WATCHDOG_INTERVAL_ENV: "3",
            runtime_config.WATCHDOG_MAX_BACKOFF_ENV: "12",
        }
        settings = runtime_config.load(environment)
        self.assertEqual(settings.listener, ("127.0.0.1", 8801))
        self.assertEqual(settings.proxy_log.max_bytes, 8192)
        self.assertEqual(settings.proxy_log.backup_count, 4)
        self.assertEqual(settings.watchdog_log.max_bytes, 12288)
        self.assertEqual(settings.watchdog_log.backup_count, 5)
        self.assertEqual(settings.responses_max_concurrency, 17)
        self.assertEqual(settings.responses_queue_timeout, 2.5)
        self.assertEqual(settings.upstream_timeout, 30)
        self.assertEqual(settings.upstream_read_timeout, 15.5)
        self.assertEqual(settings.watchdog_interval, 3)
        self.assertEqual(settings.watchdog_max_backoff, 12)

        invalid = (
            (runtime_config.PROXY_PORT_ENV, True),
            (runtime_config.PROXY_LOG_MAX_BYTES_ENV, "4095"),
            (runtime_config.PROXY_LOG_BACKUP_COUNT_ENV, "11"),
            (runtime_config.RESPONSES_MAX_CONCURRENCY_ENV, "0"),
            (runtime_config.RESPONSES_QUEUE_TIMEOUT_ENV, "nan"),
            (runtime_config.UPSTREAM_TIMEOUT_ENV, "0"),
            (runtime_config.UPSTREAM_READ_TIMEOUT_ENV, "infinity"),
            (runtime_config.WATCHDOG_INTERVAL_ENV, "-1"),
            (runtime_config.WATCHDOG_MAX_BACKOFF_ENV, "not-a-number"),
            (runtime_config.WATCHDOG_MAX_BACKOFF_ENV, False),
        )
        for name, value in invalid:
            with (
                self.subTest(name=name, value=value),
                self.assertRaises(runtime_config.ConfigurationError),
            ):
                runtime_config.load(cast("Mapping[str, str]", {name: value}))

    def test_build_context_rejects_out_of_range_ports(self):
        for port in (0, -1, 65536):
            with self.subTest(port=port), self.assertRaises(errors.InstallError):
                install.build_context(port)

    def test_build_context_rejects_out_of_bounds_log_retention(self):
        invalid = (
            {"proxy_log_max_bytes": 4095},
            {"proxy_log_backup_count": -1},
            {"watchdog_log_max_bytes": 64 * 1024 * 1024 + 1},
            {"watchdog_log_backup_count": 11},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(errors.InstallError):
                install.build_context(8791, **kwargs)


class TestGovernanceMetadata(unittest.TestCase):
    def test_current_surfaces_use_the_single_replay_owner_and_package_commands(self):
        """Reject retired artifacts and stale descriptions of the current product."""
        for retired in ("config.example", "evolution/ledger.toml"):
            self.assertFalse((ROOT / retired).exists(), retired)

        current_surfaces = {
            "README.md": (
                "dedicated semantic-preserving fallback",
                "config.example",
                "tests scripts",
            ),
            "openspec/specs/provider-portable-responses/spec.md": (
                "Classified DMX fallback",
                "one bounded fallback",
            ),
            "docs/evidence/README.md": ("prefer the loopback `control.py",),
            "tools/reliability/observe.py": ("control.py status --json output",),
            "codex_responses_proxy/commands/install.py": ("inspect `control.py status --json`",),
        }
        for relative, stale_phrases in current_surfaces.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            for phrase in stale_phrases:
                with self.subTest(path=relative, phrase=phrase):
                    self.assertNotIn(phrase, source)

    def test_publication_actors_and_trust_anchors_are_execution_inputs(self):
        tracked = (
            ROOT / "packaging" / "release" / "publication-context.toml",
            ROOT / "packaging" / "release" / "publication-policy.toml",
            ROOT / "packaging" / "release" / "gitlab-allowed-signers",
            ROOT / "packaging" / "release" / "github-allowed-signers",
            ROOT / "packaging" / "release" / "commit-allowed-signers",
        )
        self.assertFalse([path for path in tracked if path.exists()])
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("packaging/release/publication-context.toml", ignored)
        self.assertIn("packaging/release/*-allowed-signers", ignored)
        self.assertIn("packaging/release/commit-allowed-signers", ignored)

    def test_forge_publication_has_no_implicit_actor_or_trust_source(self):
        context = ROOT / "tools" / "forge" / "context.sh"
        self.assertTrue(context.is_file())
        self.assertFalse((ROOT / "tools" / "forge" / "provider-context.sh").exists())
        sources = [
            context.read_text(encoding="utf-8"),
            (ROOT / "tools" / "forge" / "check-tag-signature.sh").read_text(encoding="utf-8"),
            (ROOT / "tools" / "release" / "tag-gitlab.sh").read_text(encoding="utf-8"),
            (ROOT / "tools" / "release" / "tag-github.sh").read_text(encoding="utf-8"),
        ]
        for source in sources:
            self.assertNotIn("$root/packaging/release", source)
            self.assertNotIn("/Users/", source)
            self.assertNotIn("$HOME/.ssh", source)
        self.assertIn("CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT", sources[0])
        self.assertIn("CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS", sources[1])

    def test_semantic_packages_replace_retired_flat_modules_without_facades(self):
        retired = ("platform_adapters", "proxy")
        self.assertFalse([path for path in retired if (ROOT / path).exists()])
        packages = (
            "commands deployment listener payload providers recovery release replay runtime supervision "
            "transport"
        ).split()
        for package in (f"codex_responses_proxy/{name}" for name in packages):
            source = (ROOT / package / "__init__.py").read_text(encoding="utf-8")
            self.assertNotIn("import ", source, package)

    def test_runtime_context_has_one_semantic_owner(self):
        self.assertTrue((ROOT / "codex_responses_proxy/runtime/context.py").is_file())
        self.assertFalse((ROOT / "codex_responses_proxy/runtime/layout.py").exists())

    def test_provider_specific_wire_policies_have_a_semantic_owner(self):
        self.assertFalse((ROOT / "codex_responses_proxy/providers/dmxapi.py").exists())
        self.assertTrue((ROOT / "codex_responses_proxy/providers/policies/dmxapi.py").is_file())
        source = (ROOT / "codex_responses_proxy/providers/registry.py").read_text(encoding="utf-8")
        self.assertNotIn("from codex_responses_proxy.providers import dmxapi", source)
        self.assertNotIn("_POLICIES", source)

    def test_publication_authority_has_no_scripts_module_loader(self):
        source = (ROOT / "codex_responses_proxy/release/publication/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("importlib", source)
        self.assertNotIn("sys.modules", source)
        self.assertFalse(tuple((ROOT / "tools" / "release").glob("publication_proof*.py")))

    def test_collaboration_has_one_append_only_projection_surface(self):
        self.assertFalse((ROOT / "tools" / "forge" / "rewrite-provider-history.py").exists())
        projector = ROOT / "tools" / "forge" / "project.sh"
        self.assertTrue(projector.is_file())
        self.assertFalse(tuple((ROOT / "tools" / "forge").glob("project-*.sh")))
        source = projector.read_text(encoding="utf-8")
        for destructive in ("filter-branch", "filter-repo", "push --force", "push -f"):
            with self.subTest(destructive=destructive):
                self.assertNotIn(destructive, source)
        self.assertIn("commit-tree -S", source)
        self.assertIn('git_transport -C "$repository" push', source)

    def test_lifecycle_scripts_do_not_prescribe_client_restart_or_new_thread(self):
        text = "\n".join(
            Path(ROOT, relative).read_text(encoding="utf-8").lower()
            for relative in (
                "codex_responses_proxy/commands/install.py",
                "codex_responses_proxy/commands/uninstall.py",
            )
        )
        self.assertNotIn("fully " + "quit & reopen", text)
        self.assertNotIn("start a " + "new codex thread", text)
        self.assertIn("existing conversations remain unchanged", text)

    def test_installed_control_has_no_payload_upgrade_or_controller_patch_plane(self):
        source = Path(ROOT, "codex_responses_proxy/commands/control.py").read_text(encoding="utf-8")
        for retired in (
            "apply-control-plane",
            "upgrade_from_stage",
            "commit_payload_transaction",
            "--stage",
        ):
            self.assertNotIn(retired, source)

    def test_payload_mutation_accepts_no_raw_source_or_stage_path(self):
        payload_source = Path(ROOT, "codex_responses_proxy", "payload", "transaction.py").read_text(
            encoding="utf-8"
        )
        install_source = Path(ROOT, "codex_responses_proxy/commands/install.py").read_text(
            encoding="utf-8"
        )
        for retired in (
            "stage_payload_transaction",
            "commit_payload_transaction",
            "restore_payload_transaction",
            "finalize_payload_transaction",
        ):
            self.assertNotIn(retired, payload_source)
        self.assertNotIn("--stage-only", install_source)


class TestReleaseMetadata(unittest.TestCase):
    def test_control_and_data_planes_keep_explicit_privacy_boundaries(self):
        cases = (
            (
                ("codex_responses_proxy/commands/control.py",),
                ("def status",),
                ("AIGW", "ChatGPT", "JetBrains"),
            ),
            (
                ("codex_responses_proxy/listener/entrypoint.py",),
                (),
                (
                    "CODEX_RESPONSES_PROXY_DUMP_BODIES",
                    "CODEX_RESPONSES_PROXY_DUMP_HEADERS",
                    "reject-",
                ),
            ),
            (
                ("codex_responses_proxy/runtime/config.py",),
                (
                    "CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES",
                    "CODEX_RESPONSES_PROXY_PROXY_LOG_BACKUP_COUNT",
                    "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_MAX_BYTES",
                    "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT",
                ),
                (),
            ),
        )
        for paths, required, forbidden in cases:
            source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
            with self.subTest(paths=paths):
                for value in required:
                    self.assertIn(value, source)
                for value in forbidden:
                    self.assertNotIn(value, source)

    def test_mit_license_is_present(self):
        license_text = Path(ROOT, "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
