#!/usr/bin/env python3
"""Structured tests for codex-dmx-proxy — no real service registration.

Covers the parts that must be correct on all three OSes without needing to run the
platform service managers: config rewrite, python resolution, and the exact content
of each platform's generated service definition (plist / systemd unit / task XML).

Run: python3 tests/test_package.py
"""

import os
import sys
import tempfile
import unittest
import json
import subprocess
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from platform_adapters import common, macos, linux, windows  # noqa: E402
import install  # noqa: E402
import uninstall  # noqa: E402


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


class TestManagedRouteState(unittest.TestCase):
    def _managed_context(self, root: Path):
        install_dir = root / ".codex" / "dmx-proxy"
        config = root / ".codex" / "config.toml"
        return common.InstallContext(
            home=str(root),
            install_dir=str(install_dir),
            proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
            watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
            python=sys.executable,
            codex_config=str(config),
            log_dir=str(root / ".codex" / "log"),
            port=8791,
            upstream="https://www.dmxapi.cn",
        )

    def test_switches_only_recorded_route_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = (
                'base_url = "https://www.dmxapi.cn/v1"\n'
                'feature = true\n'
                'api_key = "do-not-copy-into-state"\n'
            )
            enabled = (
                'base_url = "http://127.0.0.1:8791/v1"\n'
                'feature = true\n'
                'api_key = "do-not-copy-into-state"\n'
            )
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")

            state = common.make_install_state(
                ctx, backup_path=str(backup), direct_urls=["https://www.dmxapi.cn/v1"],
                direct_text=direct, enabled_text=enabled,
            )
            common.write_install_state(ctx, state)
            serialized_state = Path(common.install_state_path(ctx)).read_text(encoding="utf-8")
            self.assertNotIn("do-not-copy-into-state", serialized_state)
            self.assertNotIn("feature = true", serialized_state)

            loaded = common.load_install_state(ctx)
            self.assertEqual(common.route_status(ctx, loaded), "enabled")
            common.set_proxy_route(ctx, loaded, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            self.assertEqual(common.route_status(ctx, loaded), "disabled")
            common.set_proxy_route(ctx, loaded, enabled=True)
            self.assertEqual(config.read_text(encoding="utf-8"), enabled)

            config.write_text(enabled + "user_change = true\n", encoding="utf-8")
            self.assertEqual(common.route_status(ctx, loaded), "drifted")
            with self.assertRaises(common.InstallError):
                common.set_proxy_route(ctx, loaded, enabled=False)

    def test_copy_payload_includes_control_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            install.copy_payload(ctx)
            self.assertTrue((Path(ctx.install_dir) / "control.py").is_file())
            self.assertTrue((Path(ctx.install_dir) / "platform_adapters" / "common.py").is_file())

    def test_control_status_enable_disable_uses_installed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            install.copy_payload(ctx)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")
            state = common.make_install_state(
                ctx, backup_path=str(backup), direct_urls=["https://www.dmxapi.cn/v1"],
                direct_text=direct, enabled_text=enabled,
            )
            common.write_install_state(ctx, state)

            control = Path(ctx.install_dir) / "control.py"
            env = dict(os.environ, CODEX_HOME=str(root / ".codex"))
            status = subprocess.run(
                [sys.executable, str(control), "status"], capture_output=True, text=True, env=env,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("route: enabled", status.stdout)
            disabled = subprocess.run(
                [sys.executable, str(control), "disable"], capture_output=True, text=True, env=env,
            )
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            reenabled = subprocess.run(
                [sys.executable, str(control), "enable"], capture_output=True, text=True, env=env,
            )
            self.assertEqual(reenabled.returncode, 0, reenabled.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), enabled)


class TestUninstallSafety(unittest.TestCase):
    def _managed_context(self, root: Path):
        return TestManagedRouteState()._managed_context(root)

    def test_restore_config_only_when_managed_route_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")
            state = common.make_install_state(
                ctx, backup_path=str(backup), direct_urls=["https://www.dmxapi.cn/v1"],
                direct_text=direct, enabled_text=enabled,
            )
            common.write_install_state(ctx, state)

            self.assertTrue(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            self.assertIsNone(common.load_install_state(ctx))

            config.write_text('base_url = "https://custom.example/v1"\n', encoding="utf-8")
            common.write_install_state(ctx, state)
            self.assertFalse(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), 'base_url = "https://custom.example/v1"\n')
            self.assertIsNotNone(common.load_install_state(ctx))

    def test_stop_proxy_terminates_only_verified_listener(self):
        with (
            mock.patch.object(uninstall, "_listener_pids", return_value=[100, 101]),
            mock.patch.object(
                uninstall,
                "_process_command",
                side_effect=["python unrelated.py", "python dmx_responses_proxy.py"],
            ),
            mock.patch.object(uninstall, "_terminate_pid") as terminate,
        ):
            self.assertEqual(uninstall._stop_proxy(8791), 1)
        terminate.assert_called_once_with(101)


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

    def test_task_references_generated_launcher(self):
        self.assertIn("run-watchdog.cmd", windows.render_task_xml(_ctx()))

    def test_task_runs_generated_launcher_with_proxy_environment(self):
        ctx = _ctx(port=8801, upstream="https://alternate.example")
        xml = windows.render_task_xml(ctx)
        launcher = windows.render_launcher(ctx)
        self.assertIn("run-watchdog.cmd", xml)
        self.assertNotIn('Arguments>"/home/tester/.codex/dmx-proxy/watchdog/watchdog.py"', xml)
        self.assertIn('set "DMX_PROXY_PORT=8801"', launcher)
        self.assertIn('set "DMX_UPSTREAM=https://alternate.example"', launcher)
        self.assertIn('set "DMX_PROXY_PYTHON=/usr/bin/python3.12"', launcher)
        self.assertIn('set "DMX_PROXY_SCRIPT=/home/tester/.codex/dmx-proxy/proxy/dmx_responses_proxy.py"', launcher)


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

    def test_drops_malformed_http_like_image_urls(self):
        import json
        bad_urls = [
            "https://",
            "https://bad host/example.png",
            "http:///missing-host",
            "https://example.test:not-a-port/image.png",
            "https://example.test/has space.png",
        ]
        body = json.dumps({
            "input": [{
                "type": "custom_tool_call_output",
                "output": [
                    {"type": "input_image", "image_url": url}
                    for url in bad_urls
                ] + [
                    {"type": "input_image", "image_url": "https://example.test/valid.png"},
                ],
            }],
        }).encode()

        out, note = self.p.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertIn(f"local_image_items={len(bad_urls)}", note)
        self.assertEqual(
            obj["input"][0]["output"],
            [{"type": "input_image", "image_url": "https://example.test/valid.png"}],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
