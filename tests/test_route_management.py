#!/usr/bin/env python3
"""Contracts for route ownership, persistence, switching, and uninstall restoration."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import control  # noqa: E402
import install  # noqa: E402
import uninstall  # noqa: E402
from platform_adapters import common, route_state  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402


class TestConfigRewrite(unittest.TestCase):
    def test_rewrite_dmxapi_to_proxy(self):
        cfg = '[model_providers.DMX1]\nbase_url = "https://www.dmxapi.cn/v1"\nwire_api = "responses"\n'
        new, n = route_state.rewrite_base_url(cfg, "dmxapi", route_state.proxy_base_url(8791))
        self.assertEqual(n, 1)
        self.assertIn('base_url = "http://127.0.0.1:8791/v1"', new)
        self.assertIn('wire_api = "responses"', new)  # untouched

    def test_rewrite_tolerates_single_quotes_and_spaces(self):
        cfg = "base_url   =   'https://www.dmxapi.cn/v1'\n"
        new, n = route_state.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertEqual(n, 1)
        self.assertIn("http://127.0.0.1:8791/v1", new)

    def test_idempotent_when_already_proxy(self):
        cfg = 'base_url = "http://127.0.0.1:8791/v1"\n'
        new, n = route_state.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertEqual(n, 0)
        self.assertEqual(new, cfg)

    def test_read_base_urls_multiple(self):
        cfg = 'base_url = "https://a/v1"\nx=1\nbase_url = "https://b/v1"\n'
        self.assertEqual(route_state.read_base_urls(cfg), ["https://a/v1", "https://b/v1"])

    def test_preserves_trailing_newline(self):
        cfg = 'base_url = "https://www.dmxapi.cn/v1"\n'
        new, _ = route_state.rewrite_base_url(cfg, "dmxapi", "http://127.0.0.1:8791/v1")
        self.assertTrue(new.endswith("\n"))


class TestManagedRouteState(unittest.TestCase):
    def test_switches_only_recorded_route_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = (
                'base_url = "https://www.dmxapi.cn/v1"\n'
                "feature = true\n"
                'api_key = "do-not-copy-into-state"\n'
            )
            enabled = (
                'base_url = "http://127.0.0.1:8791/v1"\n'
                "feature = true\n"
                'api_key = "do-not-copy-into-state"\n'
            )
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")

            state = route_state.make_install_state(
                ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled
            )
            route_state.write_install_state(ctx, state)
            serialized_state = Path(route_state.install_state_path(ctx)).read_text(encoding="utf-8")
            self.assertNotIn("do-not-copy-into-state", serialized_state)
            self.assertNotIn("feature = true", serialized_state)

            loaded = route_state.load_install_state(ctx)
            self.assertEqual(route_state.route_status(ctx, loaded), "enabled")
            route_state.set_proxy_route(ctx, loaded, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            self.assertEqual(route_state.route_status(ctx, loaded), "disabled")
            route_state.set_proxy_route(ctx, loaded, enabled=True)
            self.assertEqual(config.read_text(encoding="utf-8"), enabled)

            config.write_text(enabled + "user_change = true\n", encoding="utf-8")
            self.assertEqual(route_state.route_status(ctx, loaded), "drifted")
            with self.assertRaises(common.InstallError):
                route_state.set_proxy_route(ctx, loaded, enabled=False)

    def test_aigw_owned_proxy_route_is_never_rewritten_or_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = install_context(Path(tmp))
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            owned = (
                'model = "gpt-5.6-terra" # managed by AIGW\n'
                'model_provider = "aigw" # managed by AIGW\n\n'
                "# >>> AIGW managed provider >>>\n"
                "[model_providers.aigw]\n"
                'name = "AIGW: GPT-5.6 Terra"\n'
                'base_url = "http://127.0.0.1:8791/v1"\n'
                'wire_api = "responses"\n'
                "requires_openai_auth = true\n"
                "# <<< AIGW managed provider <<<\n"
            )
            config.write_text(owned, encoding="utf-8")

            self.assertEqual(route_state.route_authority(ctx), "aigw")
            self.assertTrue(install.wire_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), owned)
            self.assertIsNone(route_state.load_install_state(ctx))
            with self.assertRaises(common.InstallError):
                route_state.set_proxy_route(ctx, None, enabled=False)

    def test_build_context_honors_codex_home(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CODEX_HOME": str(Path(tmp) / "codex-home")}, clear=False),
        ):
            ctx = install.build_context(8791, "https://www.dmxapi.cn")
            self.assertEqual(ctx.codex_config, str(Path(tmp) / "codex-home" / "config.toml"))
            self.assertEqual(ctx.install_dir, str(Path(tmp) / "codex-home" / "dmx-proxy"))

    def test_adopts_existing_proxy_route_only_when_backup_reconstructs_exactly(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CODEX_HOME": str(Path(tmp) / "codex-home")}, clear=False),
        ):
            ctx = install.build_context(8791, "https://www.dmxapi.cn")
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            Path(f"{ctx.codex_config}.bak-1").write_text(direct, encoding="utf-8")

            self.assertTrue(install.wire_config(ctx))
            self.assertEqual(
                route_state.route_status(ctx, route_state.load_install_state(ctx)), "enabled"
            )

            route_state.remove_install_state(ctx)
            config.write_text(enabled + "unmanaged = true\n", encoding="utf-8")
            self.assertFalse(install.wire_config(ctx))
            self.assertIsNone(route_state.load_install_state(ctx))

    def test_route_round_trip_preserves_comments_and_each_direct_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
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
            state = route_state.make_install_state(
                ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled
            )
            route_state.write_install_state(ctx, state)
            route_state.set_proxy_route(ctx, state, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)

    def test_loads_v1_direct_route_state_for_in_place_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")
            legacy = route_state.make_install_state(
                ctx,
                backup_path=str(backup),
                direct_text=direct,
                enabled_text=enabled,
            )
            legacy["schema_version"] = 1
            legacy.pop("route_mode")
            Path(route_state.install_state_path(ctx)).parent.mkdir(parents=True, exist_ok=True)
            Path(route_state.install_state_path(ctx)).write_text(
                json.dumps(legacy), encoding="utf-8"
            )

            state = route_state.load_install_state(ctx)
            self.assertIsNotNone(state)
            route_state.set_proxy_route(ctx, state, enabled=False)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)


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
            f"[accounts.dmx.endpoints]\nopenai_responses = {endpoint!r}\n",
            encoding="utf-8",
        )
        return path

    def test_adopt_then_switches_aigw_managed_endpoint_via_aigw_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._context(root)
            config_path = self._aigw_config(root, route_state.proxy_base_url(ctx.port))

            with mock.patch.object(control, "_aigw_config_path", return_value=str(config_path)):
                state = control.adopt_aigw_route(
                    ctx,
                    account="dmx",
                    direct_url="https://www.dmxapi.cn/v1",
                )
            self.assertEqual(route_state.aigw_route_status(ctx, state, str(config_path)), "enabled")

            calls = []

            def update_endpoint(account, endpoint):
                calls.append((account, endpoint))
                config_path.write_text(
                    f"[accounts.dmx.endpoints]\nopenai_responses = {endpoint!r}\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(control, "_aigw_config_path", return_value=str(config_path)),
                mock.patch.object(
                    control, "_set_aigw_account_endpoint", side_effect=update_endpoint
                ),
            ):
                control.set_aigw_route(ctx, state, enabled=False)
                control.set_aigw_route(ctx, state, enabled=True)

            self.assertEqual(
                calls,
                [
                    ("dmx", "https://www.dmxapi.cn/v1"),
                    ("dmx", route_state.proxy_base_url(ctx.port)),
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
            state = route_state.make_aigw_install_state(
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
        return install_context(root)

    def test_restore_config_only_when_managed_route_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True, exist_ok=True)
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            config.write_text(enabled, encoding="utf-8")
            backup = Path(f"{ctx.codex_config}.bak-1")
            backup.write_text(direct, encoding="utf-8")
            state = route_state.make_install_state(
                ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled
            )
            route_state.write_install_state(ctx, state)

            self.assertTrue(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            self.assertIsNone(route_state.load_install_state(ctx))

            config.write_text('base_url = "https://custom.example/v1"\n', encoding="utf-8")
            route_state.write_install_state(ctx, state)
            self.assertFalse(uninstall.restore_config(ctx))
            self.assertEqual(
                config.read_text(encoding="utf-8"), 'base_url = "https://custom.example/v1"\n'
            )
            self.assertIsNotNone(route_state.load_install_state(ctx))

    def test_restore_aigw_route_before_uninstalling_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            aigw_config = root / "aigw.toml"
            aigw_config.write_text(
                "[accounts.dmx.endpoints]\n"
                f"openai_responses = {route_state.proxy_base_url(ctx.port)!r}\n",
                encoding="utf-8",
            )
            state = route_state.make_aigw_install_state(
                ctx,
                aigw_config_path=str(aigw_config),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            route_state.write_install_state(ctx, state)

            def disable_aigw(_ctx, _state, *, enabled):
                self.assertFalse(enabled)
                aigw_config.write_text(
                    "[accounts.dmx.endpoints]\nopenai_responses = 'https://www.dmxapi.cn/v1'\n",
                    encoding="utf-8",
                )

            with mock.patch.object(control, "set_aigw_route", side_effect=disable_aigw):
                self.assertTrue(uninstall.restore_config(ctx))
            self.assertIsNone(route_state.load_install_state(ctx))
            self.assertEqual(
                route_state.aigw_route_status(ctx, state, str(aigw_config)), "disabled"
            )

    def test_stop_proxy_terminates_only_verified_listener(self):
        with (
            mock.patch.object(uninstall.common, "listener_pids", return_value=[100, 101]),
            mock.patch.object(
                uninstall.common,
                "process_command",
                side_effect=["python unrelated.py", "python dmx_responses_proxy.py"],
            ),
            mock.patch.object(uninstall.common, "terminate_pid") as terminate,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
