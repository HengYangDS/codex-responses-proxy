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
from platform_adapters import common  # noqa: E402


class TestInstallationInputValidation(unittest.TestCase):
    def test_build_context_rejects_out_of_range_ports(self):
        for port in (0, -1, 65536):
            with self.subTest(port=port):
                with self.assertRaises(common.InstallError):
                    install.build_context(port, "https://www.dmxapi.cn")

    def test_build_context_rejects_unsafe_upstream_urls(self):
        for upstream in (
            "https://",
            "ftp://example.test",
            "https://bad host.example",
            "https://example.test:99999",
            "https://example.test:0",
            "https://example.test/has space",
            'https://example.test/" & whoami',
            "https://example.test/%25expanded",
            "https://example.test/(batch-group)",
            "https://example.test/v1?query=not-a-base-url",
            "https://example.test/v1;command",
        ):
            with self.subTest(upstream=upstream):
                with self.assertRaises(common.InstallError):
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
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(common.InstallError):
                    install.build_context(8791, "https://example.test", **kwargs)


class TestGovernanceMetadata(unittest.TestCase):
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
        payload_source = Path(ROOT, "platform_adapters", "payload.py").read_text(encoding="utf-8")
        install_source = Path(ROOT, "install.py").read_text(encoding="utf-8")
        for retired in (
            "stage_payload_transaction",
            "commit_payload_transaction",
            "restore_payload_transaction",
            "finalize_payload_transaction",
        ):
            self.assertNotIn(retired, payload_source)
        self.assertNotIn("--stage-only", install_source)
        self.assertIn("payload.begin_transaction", install_source)
        self.assertIn("deployment.install", install_source)


class TestReleaseMetadata(unittest.TestCase):
    def test_active_release_version_has_one_leading_unreleased_section(self):
        version = Path(ROOT, "VERSION").read_text(encoding="utf-8").strip()
        releases = Path(ROOT, "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = "## [Unreleased]"
        self.assertRegex(version, r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertEqual(releases.count(unreleased), 1)
        version_heading = f"## [{version}]"
        if version_heading in releases:
            self.assertLess(releases.index(unreleased), releases.index(version_heading))
        else:
            self.assertGreater(version, "0.0.0")

    def test_governance_surface_is_portable_and_read_only(self):
        source = Path(ROOT, "governance.py").read_text(encoding="utf-8")
        for forbidden in (
            "AIGW",
            "ChatGPT",
            "JetBrains",
            "subprocess",
            "write_text",
            "unlink",
            "sys.path.insert",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("control.status", source)

    def test_proxy_has_no_payload_or_header_dump_escape_hatch(self):
        source = Path(ROOT, "proxy", "dmx_responses_proxy.py").read_text(encoding="utf-8")
        for forbidden in ("DMX_DUMP_BODIES", "DMX_DUMP_HEADERS", "reject-"):
            self.assertNotIn(forbidden, source)

    def test_proxy_declares_bounded_secret_safe_log_contract(self):
        runtime_source = Path(ROOT, "proxy", "runtime_state.py").read_text(encoding="utf-8")
        transport_source = "\n".join(
            Path(ROOT, "proxy", name).read_text(encoding="utf-8")
            for name in ("responses_transport.py", "sse_transport.py")
        )
        watchdog_source = Path(ROOT, "watchdog", "watchdog.py").read_text(encoding="utf-8")
        for required in (
            "DMX_PROXY_LOG_MAX_BYTES",
            "DMX_PROXY_LOG_BACKUP_COUNT",
            "_redact_log_message",
            "safe_request_path",
        ):
            self.assertIn(required, runtime_source)
        for required in (
            "streams_pre_content_exhausted",
            "stream_pre_content_exhausted",
        ):
            self.assertIn(required, transport_source)
        for required in (
            "DMX_WATCHDOG_LOG_MAX_BYTES",
            "DMX_WATCHDOG_LOG_BACKUP_COUNT",
            "_redact_log_message",
        ):
            self.assertIn(required, watchdog_source)

    def test_mit_license_is_present(self):
        license_text = Path(ROOT, "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
