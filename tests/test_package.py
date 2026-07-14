#!/usr/bin/env python3
"""Structured tests for codex-dmx-proxy — no real service registration.

Covers the parts that must be correct on all three OSes without needing to run the
platform service managers: config rewrite, python resolution, and the exact content
of each platform's generated service definition (plist / systemd unit / task XML).

Run: python3 tests/test_package.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from platform_adapters import common, macos, linux, windows  # noqa: E402


def _ctx(port=8791, upstream="https://www.dmxapi.cn"):
    return common.InstallContext(
        home="/home/tester",
        install_dir="/home/tester/.codex/dmx-proxy",
        proxy_script="/home/tester/.codex/dmx-proxy/proxy/dmx_responses_proxy.py",
        watchdog_script="/home/tester/.codex/dmx-proxy/watchdog/watchdog.py",
        python="/usr/bin/python3.12",
        codex_config="/home/tester/.codex/config.toml",
        log_dir="/home/tester/.codex/log",
        port=port,
        upstream=upstream,
    )


class TestConfigRewrite(unittest.TestCase):
    def test_rewrite_dmxapi_to_proxy(self):
        cfg = '[model_providers.DMX1]\nbase_url = "https://www.dmxapi.cn/v1"\nwire_api = "responses"\n'
        new, n = common.rewrite_base_url(cfg, "dmxapi", common.proxy_base_url(8791))
        self.assertEqual(n, 1)
        self.assertIn('base_url = "http://127.0.0.1:8791/v1"', new)
        self.assertIn('wire_api = "responses"', new)  # untouched

    def test_rewrite_tolerates_single_quotes_and_spaces(self):
        cfg = "base_url   =   'https://www.dmxapi.cn/v1'\n"
        new, n = common.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertEqual(n, 1)
        self.assertIn("http://127.0.0.1:8791/v1", new)

    def test_idempotent_when_already_proxy(self):
        cfg = 'base_url = "http://127.0.0.1:8791/v1"\n'
        new, n = common.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertEqual(n, 0)
        self.assertEqual(new, cfg)

    def test_read_base_urls_multiple(self):
        cfg = 'base_url = "https://a/v1"\nx=1\nbase_url = "https://b/v1"\n'
        self.assertEqual(common.read_base_urls(cfg), ["https://a/v1", "https://b/v1"])

    def test_preserves_trailing_newline(self):
        cfg = 'base_url = "https://www.dmxapi.cn/v1"\n'
        new, _ = common.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertTrue(new.endswith("\n"))


class TestPythonResolution(unittest.TestCase):
    def test_resolves_absolute_existing(self):
        p = common.resolve_python()
        self.assertTrue(os.path.isabs(p))
        self.assertTrue(os.path.exists(p))

    def test_store_stub_detection_noop_off_windows(self):
        # Off Windows this is always False regardless of path.
        if os.name != "nt":
            self.assertFalse(common._is_windows_store_stub(r"C:\x\WindowsApps\python.exe"))


class TestMacosPlist(unittest.TestCase):
    def test_plist_has_keepalive_and_absolute_python(self):
        xml = macos.render_plist(_ctx())
        self.assertIn("<key>KeepAlive</key>", xml)
        self.assertIn("<true/>", xml)
        self.assertIn("/usr/bin/python3.12", xml)
        self.assertIn("com.user.codex-dmx-watchdog", xml)
        self.assertIn("DMX_PROXY_PORT", xml)
        self.assertIn("8791", xml)

    def test_plist_is_wellformed_xml(self):
        import xml.dom.minidom as minidom
        minidom.parseString(macos.render_plist(_ctx()))  # raises if malformed


class TestLinuxUnit(unittest.TestCase):
    def test_unit_restart_always_and_absolute_paths(self):
        unit = linux.render_unit(_ctx())
        self.assertIn("Restart=always", unit)
        self.assertIn("RestartSec=3", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn("ExecStart=/usr/bin/python3.12", unit)
        self.assertIn("Environment=DMX_PROXY_PORT=8791", unit)

    def test_unit_no_multiuser_target(self):
        # user units must target default.target, not multi-user.target
        self.assertNotIn("multi-user.target", linux.render_unit(_ctx()))

    def test_manual_start_required_is_nonfatal_type(self):
        # A minimal host (no systemd bus, no crontab) must degrade to a warning,
        # not abort the install — ManualStartRequired is caught as non-fatal.
        self.assertTrue(issubclass(common.ManualStartRequired, Exception))
        self.assertFalse(issubclass(common.ManualStartRequired, common.InstallError))


class TestWindowsTask(unittest.TestCase):
    def test_task_xml_wellformed_and_key_settings(self):
        import xml.dom.minidom as minidom
        xml = windows.render_task_xml(_ctx())
        minidom.parseString(xml)  # raises if malformed
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", xml)  # no 72h kill
        self.assertIn("<LogonTrigger>", xml)
        self.assertIn("<RestartOnFailure>", xml)
        self.assertIn("<LogonType>InteractiveToken</LogonType>", xml)   # no admin
        self.assertIn("<RunLevel>LeastPrivilege</RunLevel>", xml)

    def test_task_references_watchdog(self):
        self.assertIn("watchdog.py", windows.render_task_xml(_ctx()))


class TestProxySanitize(unittest.TestCase):
    """Verify the packaged proxy's core stripping logic still works."""
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "proxy"))
        import dmx_responses_proxy as p
        self.p = p

    def test_strips_reasoning_and_encrypted(self):
        import json
        body = json.dumps({
            "input": [
                {"type": "reasoning", "encrypted_content": "gAAAA_secret"},
                {"type": "message", "content": "hello"},
            ],
            "include": ["reasoning.encrypted_content", "other"],
        }).encode()
        out, note = self.p.sanitize_responses_body(body)
        obj = json.loads(out)
        self.assertEqual(len(obj["input"]), 1)                    # reasoning dropped
        self.assertEqual(obj["input"][0]["type"], "message")
        self.assertNotIn("reasoning.encrypted_content", obj["include"])
        self.assertNotIn("encrypted_content", json.dumps(obj))    # fully stripped

    def test_fail_open_on_non_json(self):
        raw = b"not json at all"
        out, note = self.p.sanitize_responses_body(raw)
        self.assertEqual(out, raw)                                # unchanged
        self.assertIn("passthrough", note)

    def test_clean_body_untouched(self):
        import json
        body = json.dumps({"input": [{"type": "message", "content": "hi"}]}).encode()
        out, note = self.p.sanitize_responses_body(body)
        self.assertIn("clean", note)

    def test_drops_unreplayable_images_and_keeps_text_and_https(self):
        import json
        body = json.dumps({
            "input": [
                {
                    "type": "custom_tool_call_output",
                    "output": [
                        {"type": "input_text", "text": "before"},
                        {"type": "input_image", "image_url": "/tmp/example.png"},
                        {"type": "input_text", "text": "after"},
                    ],
                },
                {
                    "type": "message",
                    "content": [
                        {"type": "input_image", "image_url": "https://example.test/valid.png"},
                        {"type": "input_image", "image_url": "data:image/png;base64,not-supported"},
                    ],
                },
            ]
        }).encode()

        out, note = self.p.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertIn("local_image_items=2", note)
        self.assertEqual(
            obj["input"][0]["output"],
            [
                {"type": "input_text", "text": "before"},
                {"type": "input_text", "text": "after"},
            ],
        )
        self.assertEqual(
            obj["input"][1]["content"],
            [{"type": "input_image", "image_url": "https://example.test/valid.png"}],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
