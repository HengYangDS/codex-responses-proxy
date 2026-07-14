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
import control  # noqa: E402


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

            state = common.make_install_state(ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled)
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

    def test_copied_payload_has_a_tamper_evident_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            install.copy_payload(ctx)

            ok, detail = common.verify_payload_manifest(ctx)
            self.assertTrue(ok, detail)

            with open(Path(ctx.install_dir) / "proxy" / "dmx_responses_proxy.py", "a", encoding="utf-8") as fh:
                fh.write("# tampered\n")
            ok, detail = common.verify_payload_manifest(ctx)
            self.assertFalse(ok)
            self.assertIn("hash mismatch", detail)

    def test_copy_payload_removes_known_legacy_artifacts_but_preserves_route_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            install_dir = Path(ctx.install_dir)
            legacy_tests = install_dir / "tests"
            legacy_tests.mkdir(parents=True)
            (legacy_tests / "test_encrypted_replay_blocks.py").write_text("legacy", encoding="utf-8")
            state_path = Path(common.install_state_path(ctx))
            state_path.write_text('{"legacy": true}\n', encoding="utf-8")

            install.copy_payload(ctx)

            self.assertFalse(legacy_tests.exists())
            self.assertEqual(state_path.read_text(encoding="utf-8"), '{"legacy": true}\n')
            manifest = json.loads(Path(common.payload_manifest_path(ctx)).read_text(encoding="utf-8"))
            self.assertEqual(sorted(manifest["files"]), sorted(common.RUNTIME_PAYLOAD_FILES))
            self.assertTrue(all(not relative.startswith("tests/") for relative in manifest["files"]))

    def test_aigw_owned_proxy_route_is_never_rewritten_or_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            owned = (
                'model = "gpt-5.6-terra" # managed by AIGW\n'
                'model_provider = "aigw" # managed by AIGW\n\n'
                '# >>> AIGW managed provider >>>\n'
                '[model_providers.aigw]\n'
                'name = "AIGW: GPT-5.6 Terra"\n'
                'base_url = "http://127.0.0.1:8791/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = true\n'
                '# <<< AIGW managed provider <<<\n'
            )
            config.write_text(owned, encoding="utf-8")

            self.assertEqual(common.route_authority(ctx), "aigw")
            self.assertTrue(install.wire_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), owned)
            self.assertIsNone(common.load_install_state(ctx))
            with self.assertRaises(common.InstallError):
                common.set_proxy_route(ctx, None, enabled=False)


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
            state = common.make_install_state(ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled)
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

    def test_build_context_honors_codex_home(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CODEX_HOME": str(Path(tmp) / "codex-home")}, clear=False):
            ctx = install.build_context(8791, "https://www.dmxapi.cn")
            self.assertEqual(ctx.codex_config, str(Path(tmp) / "codex-home" / "config.toml"))
            self.assertEqual(ctx.install_dir, str(Path(tmp) / "codex-home" / "dmx-proxy"))

    def test_adopts_existing_proxy_route_only_when_backup_reconstructs_exactly(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CODEX_HOME": str(Path(tmp) / "codex-home")}, clear=False):
            ctx = install.build_context(8791, "https://www.dmxapi.cn")
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            Path(f"{ctx.codex_config}.bak-1").write_text(direct, encoding="utf-8")

            self.assertTrue(install.wire_config(ctx))
            self.assertEqual(common.route_status(ctx, common.load_install_state(ctx)), "enabled")

            common.remove_install_state(ctx)
            config.write_text(enabled + "unmanaged = true\n", encoding="utf-8")
            self.assertFalse(install.wire_config(ctx))
            self.assertIsNone(common.load_install_state(ctx))

    def test_route_round_trip_preserves_comments_and_each_direct_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = (
                'base_url = "https://one.dmxapi.example/v1" # first\n'
                'base_url = "https://two.dmxapi.example/v1" # second\n'
            )
            enabled = (
                'base_url = "http://127.0.0.1:8791/v1" # first\n'
                'base_url = "http://127.0.0.1:8791/v1" # second\n'
            )
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")
            state = common.make_install_state(ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled)
            common.write_install_state(ctx, state)
            common.set_proxy_route(ctx, state, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)

    def test_loads_v1_direct_route_state_for_in_place_upgrade(self):
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
            legacy = common.make_install_state(
                ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled,
            )
            legacy["schema_version"] = 1
            legacy.pop("route_mode")
            Path(common.install_state_path(ctx)).parent.mkdir(parents=True, exist_ok=True)
            Path(common.install_state_path(ctx)).write_text(json.dumps(legacy), encoding="utf-8")

            state = common.load_install_state(ctx)
            self.assertIsNotNone(state)
            common.set_proxy_route(ctx, state, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)


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
            'https://example.test/\" & whoami',
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


class TestAIGWRouteControl(unittest.TestCase):
    def _context(self, root: Path):
        install_dir = root / ".codex" / "dmx-proxy"
        return common.InstallContext(
            home=str(root),
            install_dir=str(install_dir),
            proxy_script=str(install_dir / "proxy" / "dmx_responses_proxy.py"),
            watchdog_script=str(install_dir / "watchdog" / "watchdog.py"),
            python=sys.executable,
            codex_config=str(root / ".codex" / "config.toml"),
            log_dir=str(root / ".codex" / "log"),
            port=8791,
            upstream="https://www.dmxapi.cn",
        )

    def _aigw_config(self, root: Path, endpoint: str) -> Path:
        path = root / "aigw.toml"
        path.write_text(
            "[accounts.dmx.endpoints]\n"
            f"openai_responses = {endpoint!r}\n",
            encoding="utf-8",
        )
        return path

    def test_adopt_then_switches_aigw_managed_endpoint_via_aigw_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._context(root)
            config_path = self._aigw_config(root, common.proxy_base_url(ctx.port))

            with mock.patch.object(control, "_aigw_config_path", return_value=str(config_path)):
                state = control.adopt_aigw_route(
                    ctx,
                    account="dmx",
                    direct_url="https://www.dmxapi.cn/v1",
                )
            self.assertEqual(common.aigw_route_status(ctx, state, str(config_path)), "enabled")

            calls = []
            def update_endpoint(account, endpoint):
                calls.append((account, endpoint))
                config_path.write_text(
                    "[accounts.dmx.endpoints]\n"
                    f"openai_responses = {endpoint!r}\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(control, "_aigw_config_path", return_value=str(config_path)),
                mock.patch.object(control, "_set_aigw_account_endpoint", side_effect=update_endpoint),
            ):
                control.set_aigw_route(ctx, state, enabled=False)
                control.set_aigw_route(ctx, state, enabled=True)

            self.assertEqual(
                calls,
                [
                    ("dmx", "https://www.dmxapi.cn/v1"),
                    ("dmx", common.proxy_base_url(ctx.port)),
                ],
            )

    def test_adopt_refuses_an_unrelated_aigw_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._context(root)
            config_path = self._aigw_config(root, "https://other.example/v1")
            with mock.patch.object(control, "_aigw_config_path", return_value=str(config_path)):
                with self.assertRaises(common.InstallError):
                    control.adopt_aigw_route(
                        ctx,
                        account="dmx",
                        direct_url="https://www.dmxapi.cn/v1",
                    )

    def test_aigw_route_rejects_a_successful_command_without_canonical_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._context(root)
            config_path = self._aigw_config(root, "https://www.dmxapi.cn/v1")
            state = common.make_aigw_install_state(
                ctx,
                aigw_config_path=str(config_path),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            with mock.patch.object(control, "_set_aigw_account_endpoint"):
                with self.assertRaises(common.InstallError):
                    control.set_aigw_route(ctx, state, enabled=True)


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
            state = common.make_install_state(ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled)
            common.write_install_state(ctx, state)

            self.assertTrue(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            self.assertIsNone(common.load_install_state(ctx))

            config.write_text('base_url = "https://custom.example/v1"\n', encoding="utf-8")
            common.write_install_state(ctx, state)
            self.assertFalse(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), 'base_url = "https://custom.example/v1"\n')
            self.assertIsNotNone(common.load_install_state(ctx))

    def test_restore_aigw_route_before_uninstalling_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            aigw_config = root / "aigw.toml"
            aigw_config.write_text(
                "[accounts.dmx.endpoints]\n"
                f"openai_responses = {common.proxy_base_url(ctx.port)!r}\n",
                encoding="utf-8",
            )
            state = common.make_aigw_install_state(
                ctx,
                aigw_config_path=str(aigw_config),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            common.write_install_state(ctx, state)

            def disable_aigw(_ctx, _state, *, enabled):
                self.assertFalse(enabled)
                aigw_config.write_text(
                    "[accounts.dmx.endpoints]\n"
                    "openai_responses = 'https://www.dmxapi.cn/v1'\n",
                    encoding="utf-8",
                )

            with mock.patch.object(control, "set_aigw_route", side_effect=disable_aigw):
                self.assertTrue(uninstall.restore_config(ctx))
            self.assertIsNone(common.load_install_state(ctx))
            self.assertEqual(common.aigw_route_status(ctx, state, str(aigw_config)), "disabled")

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

    def test_purge_removes_only_the_proxy_install_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            install_dir = codex_home / "dmx-proxy"
            install_dir.mkdir(parents=True)
            (install_dir / "marker").write_text("owned payload", encoding="utf-8")
            adapter = mock.Mock()
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(uninstall, "pick_adapter", return_value=adapter),
                mock.patch.object(uninstall, "_stop_proxy", return_value=0),
                mock.patch.object(sys, "argv", ["uninstall.py", "--purge", "--keep-config"]),
            ):
                uninstall.main()
            self.assertFalse(install_dir.exists())


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
        self.assertEqual(obj["input"], [{"type": "message", "content": "hello"}])

    def test_preserves_required_agent_message_encrypted_content(self):
        body = json.dumps({
            "input": [
                {
                    "type": "reasoning",
                    "encrypted_content": "gAAAA_replay_only",
                },
                {
                    "type": "agent_message",
                    "author": "agent",
                    "recipient": "user",
                    "content": [
                        {"type": "input_text", "text": "reply"},
                        {
                            "type": "encrypted_content",
                            "encrypted_content": "required_agent_message_payload",
                        },
                    ],
                },
            ],
            "include": ["reasoning.encrypted_content", "other"],
        }).encode()

        out, note = self.p.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertEqual(len(obj["input"]), 1)  # replayed reasoning still dropped
        encrypted = obj["input"][0]["content"][1]
        self.assertEqual(encrypted["type"], "encrypted_content")
        self.assertEqual(
            encrypted["encrypted_content"], "required_agent_message_payload",
        )
        self.assertIn("agent_message_encrypted=1", note)
        self.assertIn("malformed_encrypted_blocks=0", note)
        self.assertNotIn("reasoning.encrypted_content", obj["include"])

    def test_drops_only_legacy_encrypted_content_blocks_missing_payload(self):
        body = json.dumps({
            "input": [{
                "type": "agent_message",
                "content": [
                    {"type": "input_text", "text": "before"},
                    {"type": "encrypted_content"},
                    {
                        "type": "encrypted_content",
                        "encrypted_content": "valid_required_payload",
                    },
                    {"type": "input_text", "text": "after"},
                ],
            }],
        }).encode()

        out, note = self.p.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertIn("malformed_encrypted_blocks=1", note)
        self.assertEqual(
            obj["input"][0]["content"],
            [
                {"type": "input_text", "text": "before"},
                {
                    "type": "encrypted_content",
                    "encrypted_content": "valid_required_payload",
                },
                {"type": "input_text", "text": "after"},
            ],
        )

    def test_keeps_unrelated_encrypted_content_shape_outside_legacy_content_lists(self):
        body = json.dumps({
            "input": [{
                "type": "custom_tool_call",
                "payload": {"type": "encrypted_content"},
            }],
        }).encode()

        out, note = self.p.sanitize_responses_body(body)

        self.assertEqual(out, body)
        self.assertIn("clean", note)

    def test_sanitize_sse_event_strips_reasoning_but_keeps_agent_message_payload(self):
        raw = (
            b"event: response.completed\n"
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"replay","id":"r"},'
            b'{"type":"agent_message","content":[{"type":"encrypted_content",'
            b'"encrypted_content":"required"}]}'
            b']}}\n\n'
        )
        out, removed = self.p.sanitize_sse_event(raw)
        event = json.loads(out.split(b"data: ", 1)[1])
        output = event["response"]["output"]
        self.assertEqual(removed, 1)
        self.assertNotIn("encrypted_content", output[0])
        self.assertEqual(output[1]["content"][0]["encrypted_content"], "required")

    def test_runtime_server_version_uses_version_file(self):
        self.assertEqual(self.p.release_version(), Path(ROOT, "VERSION").read_text(encoding="utf-8").strip())

    def test_fail_open_on_non_json(self):
        raw = b"not json at all"
        out, note = self.p.sanitize_responses_body(raw)
        self.assertEqual(out, raw)                                # unchanged
        self.assertIn("passthrough", note)

    def test_clean_body_untouched(self):
        body = json.dumps({"input": [{"type": "message", "content": "hi"}]}).encode()
        out, note = self.p.sanitize_responses_body(body)
        self.assertIn("clean", note)

    def test_drops_unreplayable_images_and_keeps_text_and_https(self):
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


class TestReleaseMetadata(unittest.TestCase):
    def test_release_version_matches_changelog(self):
        version = Path(ROOT, "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"## [{version}]", Path(ROOT, "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
