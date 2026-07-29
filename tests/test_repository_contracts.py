#!/usr/bin/env python3
"""Repository governance, release-metadata, and privacy-surface contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402
from codex_dmx_proxy import errors  # noqa: E402


class TestInstallationInputValidation(unittest.TestCase):
    def test_build_context_rejects_out_of_range_ports(self):
        for port in (0, -1, 65536):
            with self.subTest(port=port), self.assertRaises(errors.InstallError):
                install.build_context(port, "https://www.dmxapi.cn")

    def test_build_context_rejects_unsafe_upstream_urls(self):
        unsafe = """
https://
ftp://example.test
https://bad host.example
https://example.test:99999
https://example.test:0
https://example.test/has space
https://example.test/" & whoami
https://example.test/%25expanded
https://example.test/(batch-group)
https://example.test/v1?query=not-a-base-url
https://example.test/v1;command
""".splitlines()[1:]
        for upstream in unsafe:
            with self.subTest(upstream=upstream), self.assertRaises(errors.InstallError):
                install.build_context(8791, upstream)

    def test_build_context_normalizes_a_safe_upstream_url(self):
        ctx = install.build_context(8791, "https://example.test/v1/")
        self.assertEqual(ctx.upstream, "https://example.test/v1")

    def test_build_context_rejects_out_of_bounds_log_retention(self):
        invalid = (
            {"proxy_log_max_bytes": 4095},
            {"proxy_log_backup_count": -1},
            {"watchdog_log_max_bytes": 64 * 1024 * 1024 + 1},
            {"watchdog_log_backup_count": 11},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(errors.InstallError):
                install.build_context(8791, "https://example.test", **kwargs)


class TestGovernanceMetadata(unittest.TestCase):
    def test_semantic_packages_replace_retired_flat_modules_without_facades(self):
        retired = ("platform_adapters", "proxy")
        self.assertFalse([path for path in retired if (ROOT / path).exists()])
        packages = "compatibility deployment listener release route supervision".split()
        for package in (f"codex_dmx_proxy/{name}" for name in packages):
            source = (ROOT / package / "__init__.py").read_text(encoding="utf-8")
            self.assertNotIn("import ", source, package)

    def test_publication_authority_has_no_scripts_module_loader(self):
        source = (ROOT / "codex_dmx_proxy/release/publication/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("importlib", source)
        self.assertNotIn("sys.modules", source)
        self.assertFalse(tuple((ROOT / "scripts").glob("publication_proof*.py")))

    def test_lifecycle_scripts_do_not_prescribe_client_restart_or_new_thread(self):
        text = "\n".join(
            Path(ROOT, relative).read_text(encoding="utf-8").lower()
            for relative in ("install.py", "uninstall.py")
        )
        self.assertNotIn("fully " + "quit & reopen", text)
        self.assertNotIn("start a " + "new codex thread", text)
        self.assertIn("existing conversations remain unchanged", text)

    def test_installed_control_has_no_payload_upgrade_or_controller_patch_plane(self):
        source = Path(ROOT, "control.py").read_text(encoding="utf-8")
        for retired in (
            "apply-control-plane",
            "upgrade_from_stage",
            "commit_payload_transaction",
            "--stage",
        ):
            self.assertNotIn(retired, source)

    def test_payload_mutation_accepts_no_raw_source_or_stage_path(self):
        payload_source = Path(ROOT, "codex_dmx_proxy", "release", "transaction.py").read_text(
            encoding="utf-8"
        )
        install_source = Path(ROOT, "install.py").read_text(encoding="utf-8")
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
                ("governance.py",),
                ("control.status",),
                (
                    "AIGW",
                    "ChatGPT",
                    "JetBrains",
                    "subprocess",
                    "write_text",
                    "unlink",
                    "sys.path.insert",
                ),
            ),
            (
                ("codex_dmx_proxy/listener/entrypoint.py",),
                (),
                ("DMX_DUMP_BODIES", "DMX_DUMP_HEADERS", "reject-"),
            ),
            (
                ("codex_dmx_proxy/listener/state.py", "watchdog/watchdog.py"),
                (
                    "DMX_PROXY_LOG_MAX_BYTES",
                    "DMX_PROXY_LOG_BACKUP_COUNT",
                    "DMX_WATCHDOG_LOG_MAX_BYTES",
                    "DMX_WATCHDOG_LOG_BACKUP_COUNT",
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
