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
from codex_dmx_proxy import errors  # noqa: E402
from codex_dmx_proxy.route import management as route_state  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402


class RouteTestCase(unittest.TestCase):
    def route(self, root: Path, direct: str, enabled: str):
        ctx = install_context(root)
        config = Path(ctx.codex_config)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(enabled, encoding="utf-8")
        backup = Path(f"{ctx.codex_config}.bak-1")
        backup.write_text(direct, encoding="utf-8")
        state = route_state.make_install_state(
            ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled
        )
        return ctx, config, state


class TestConfigRewrite(unittest.TestCase):
    def test_rewrites_and_reads_routes_without_touching_other_lines(self):
        config = (
            '[model_providers.DMX1]\nbase_url = "https://www.dmxapi.cn/v1"\n'
            'wire_api = "responses"\n'
        )
        rewritten, changed = route_state.rewrite_base_url(
            config, "dmxapi", route_state.proxy_base_url(8791)
        )
        self.assertEqual(changed, 1)
        self.assertIn('base_url = "http://127.0.0.1:8791/v1"', rewritten)
        self.assertIn('wire_api = "responses"', rewritten)
        self.assertTrue(rewritten.endswith("\n"))
        self.assertEqual(
            route_state.read_base_urls(
                'base_url = "https://a/v1"\nx=1\nbase_url = "https://b/v1"\n'
            ),
            ["https://a/v1", "https://b/v1"],
        )
        enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
        self.assertEqual(
            route_state.rewrite_base_url(enabled, "dmxapi", route_state.proxy_base_url(8791)),
            (enabled, 0),
        )


class TestRouteStateFailures(unittest.TestCase):
    def test_rejects_unsafe_upstream_urls(self):
        invalid = (
            "",
            "https://exa mple.test/v1",
            "https://example.test/\x01",
            "https://example.test/v1;command",
            "ftp://example.test/v1",
            "https://user:secret@example.test/v1",
            "https://example.test/v1?query=yes",
            "https://example.test/v1#fragment",
            "https://example.test:0/v1",
            "https://example.test:not-a-port/v1",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(errors.InstallError):
                route_state.normalize_upstream_url(value)
        self.assertEqual(
            route_state.normalize_upstream_url("https://example.test/v1/"),
            "https://example.test/v1",
        )

    def test_rejects_invalid_state_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = install_context(Path(tmp))
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = f'base_url = "{route_state.proxy_base_url(ctx.port)}"\n'
            codex = route_state.make_install_state(
                ctx,
                backup_path=f"{ctx.codex_config}.bak-1",
                direct_text=direct,
                enabled_text=enabled,
            )
            aigw = route_state.make_aigw_install_state(
                ctx,
                aigw_config_path=str(Path(tmp) / "aigw.toml"),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            mutations = {
                "schema_version": (codex, 99),
                "route_mode": (codex, "unknown"),
                "config_path": (codex, "/wrong/config.toml"),
                "proxy_url": (codex, "http://127.0.0.1:1/v1"),
                "backup_path": (codex, "/wrong/config.toml.bak-1"),
                "source_host_substr": (codex, ""),
                "direct_sha256": (codex, None, "short"),
                "enabled_sha256": (codex, None, "short"),
                "aigw_config_path": (aigw, "relative.toml"),
                "aigw_account": (aigw, None, ""),
                "direct_url": (aigw, None, "file:///tmp/upstream"),
            }
            for field, (template, *values) in mutations.items():
                for value in values:
                    with (
                        self.subTest(field=field, value=value),
                        self.assertRaises(errors.InstallError),
                    ):
                        route_state.write_install_state(ctx, template | {field: value})

            with self.assertRaises(errors.InstallError):
                route_state.make_aigw_install_state(
                    ctx,
                    aigw_config_path=str(Path(tmp) / "aigw.toml"),
                    account="",
                    direct_url="https://www.dmxapi.cn/v1",
                )

    def test_missing_or_untrusted_state_is_not_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            config = Path(ctx.codex_config)
            state_path = Path(route_state.install_state_path(ctx))
            self.assertEqual(route_state.route_status(ctx, None), "unmanaged")
            self.assertEqual(route_state.route_authority(ctx), "unmanaged")

            state_path.parent.mkdir(parents=True)
            for payload in ("{", "[]"):
                state_path.write_text(payload, encoding="utf-8")
                self.assertIsNone(route_state.load_install_state(ctx))

            state = route_state.make_install_state(
                ctx,
                backup_path=f"{ctx.codex_config}.bak-1",
                direct_text="direct",
                enabled_text="enabled",
            )
            self.assertEqual(route_state.route_status(ctx, state), "drifted")
            route_state.write_install_state(ctx, state)
            config.parent.mkdir(parents=True, exist_ok=True)
            for projection in (
                "plain config\n",
                f"{route_state.AIGW_PROVIDER_BEGIN}\n{route_state.AIGW_PROVIDER_END}\n",
                f"{route_state.AIGW_PROVIDER_BEGIN}\n[model_providers.aigw]\n"
                f"{route_state.AIGW_PROVIDER_END}\n",
            ):
                config.write_text(projection, encoding="utf-8")
                self.assertEqual(route_state.route_authority(ctx), "proxy")

            route_state.remove_install_state(ctx)
            route_state.remove_install_state(ctx)
            self.assertEqual(route_state.route_authority(ctx), "unmanaged")

    def test_rejects_missing_or_tampered_transition_sources(self):
        for backup_text in (None, "tampered"):
            with self.subTest(backup_text=backup_text), tempfile.TemporaryDirectory() as tmp:
                ctx = install_context(Path(tmp))
                config = Path(ctx.codex_config)
                config.parent.mkdir(parents=True)
                direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
                enabled = f'base_url = "{route_state.proxy_base_url(ctx.port)}"\n'
                config.write_text(enabled, encoding="utf-8")
                backup = Path(f"{ctx.codex_config}.bak-1")
                if backup_text is not None:
                    backup.write_text(backup_text, encoding="utf-8")
                state = route_state.make_install_state(
                    ctx, backup_path=str(backup), direct_text=direct, enabled_text=enabled
                )
                with self.assertRaises(errors.InstallError):
                    route_state.set_proxy_route(ctx, state, enabled=False)

    def test_aigw_status_rejects_missing_or_unrecognized_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            config = root / "aigw.toml"
            state = route_state.make_aigw_install_state(
                ctx,
                aigw_config_path=str(config),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            self.assertEqual(route_state.aigw_route_status(ctx, state, str(config)), "drifted")
            for text in (
                "openai_responses = 'https://www.dmxapi.cn/v1'\n",
                "[accounts.other.endpoints]\nopenai_responses = 'https://www.dmxapi.cn/v1'\n",
                "[accounts.dmx.endpoints]\nopenai_responses = invalid\n",
                "[accounts.dmx.endpoints]\nopenai_responses = 'https://other.example/v1'\n",
            ):
                config.write_text(text, encoding="utf-8")
                self.assertEqual(route_state.aigw_route_status(ctx, state, str(config)), "drifted")

    def test_rejects_unreconstructable_and_foreign_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = install_context(Path(tmp))
            config = Path(ctx.codex_config)
            config.parent.mkdir(parents=True)
            proxy_url = route_state.proxy_base_url(ctx.port)
            for direct, enabled_sha256 in (
                ('base_url = "https://other.example/v1"\n', None),
                ('base_url = "https://www.dmxapi.cn/v1"\n', "0" * 64),
            ):
                config.write_text(direct, encoding="utf-8")
                state = route_state.make_install_state(
                    ctx,
                    backup_path=f"{ctx.codex_config}.bak-1",
                    direct_text=direct,
                    enabled_text=f'base_url = "{proxy_url}"\n',
                )
                if enabled_sha256:
                    state["enabled_sha256"] = enabled_sha256
                with self.assertRaises(errors.InstallError):
                    route_state.set_proxy_route(ctx, state, enabled=True)

            aigw = route_state.make_aigw_install_state(
                ctx,
                aigw_config_path=str(Path(tmp) / "aigw.toml"),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            with self.assertRaises(errors.InstallError):
                route_state.set_proxy_route(ctx, aigw, enabled=True)


class TestManagedRouteState(RouteTestCase):
    def test_switches_only_recorded_route_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            direct = (
                'base_url = "https://www.dmxapi.cn/v1"\n'
                "feature = true\n"
                'api_key = "do-not-copy-into-state"\n'
            )
            enabled = direct.replace("https://www.dmxapi.cn/v1", route_state.proxy_base_url(8791))
            ctx, config, route = self.route(Path(tmp), direct, enabled)
            route_state.write_install_state(ctx, route)
            persisted = Path(route_state.install_state_path(ctx)).read_text(encoding="utf-8")
            self.assertNotIn("do-not-copy-into-state", persisted)
            self.assertNotIn("feature = true", persisted)
            loaded = route_state.load_install_state(ctx)
            self.assertEqual(route_state.route_status(ctx, loaded), "enabled")
            route_state.set_proxy_route(ctx, loaded, enabled=False)
            self.assertEqual(
                (config.read_text(), route_state.route_status(ctx, loaded)), (direct, "disabled")
            )
            route_state.set_proxy_route(ctx, loaded, enabled=True)
            self.assertEqual(config.read_text(), enabled)
            config.write_text(enabled + "user_change = true\n", encoding="utf-8")
            self.assertEqual(route_state.route_status(ctx, loaded), "drifted")
            with self.assertRaises(errors.InstallError):
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
            with self.assertRaises(errors.InstallError):
                route_state.set_proxy_route(ctx, None, enabled=False)

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
            direct = (
                'base_url = "https://one.dmxapi.example/v1" # first\n'
                'base_url = "https://two.dmxapi.example/v1" # second\n'
            )
            enabled = (
                'base_url = "http://127.0.0.1:8791/v1" # first\n'
                'base_url = "http://127.0.0.1:8791/v1" # second\n'
            )
            ctx, config, route = self.route(Path(tmp), direct, enabled)
            route_state.write_install_state(ctx, route)
            route_state.set_proxy_route(ctx, route, enabled=False)
            self.assertEqual(config.read_text(), direct)

    def test_loads_v1_direct_route_state_for_in_place_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            ctx, config, legacy = self.route(Path(tmp), direct, enabled)
            legacy["schema_version"] = 1
            legacy.pop("route_mode")
            state_path = Path(route_state.install_state_path(ctx))
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(legacy), encoding="utf-8")
            loaded = route_state.load_install_state(ctx)
            self.assertIsNotNone(loaded)
            route_state.set_proxy_route(ctx, loaded, enabled=False)
            self.assertEqual(config.read_text(), direct)


class TestAIGWRouteControl(unittest.TestCase):
    def _context(self, root: Path):
        return install_context(root)

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
                with self.assertRaises(errors.InstallError):
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
                with self.assertRaises(errors.InstallError):
                    control.set_aigw_route(ctx, state, enabled=True)


class TestUninstallSafety(RouteTestCase):
    def test_restore_config_only_when_managed_route_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            direct = 'base_url = "https://www.dmxapi.cn/v1"\n'
            enabled = 'base_url = "http://127.0.0.1:8791/v1"\n'
            ctx, config, route = self.route(Path(tmp), direct, enabled)
            route_state.write_install_state(ctx, route)
            self.assertTrue(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(), direct)
            self.assertIsNone(route_state.load_install_state(ctx))
            custom = 'base_url = "https://custom.example/v1"\n'
            config.write_text(custom, encoding="utf-8")
            route_state.write_install_state(ctx, route)
            self.assertFalse(uninstall.restore_config(ctx))
            self.assertEqual(config.read_text(), custom)
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
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                uninstall.process,
                "verified_proxy_listener_pids",
                side_effect=[[101], []],
            ),
            mock.patch.object(
                uninstall.process,
                "terminate_pid",
                return_value=True,
            ) as terminate,
        ):
            self.assertEqual(uninstall._stop_proxy(ctx), 1)
        terminate.assert_called_once_with(101, expected_path=ctx.proxy_script)

    def test_purge_stops_after_unproven_service_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            install_dir = codex_home / "dmx-proxy"
            install_dir.mkdir(parents=True)
            marker = install_dir / "marker"
            marker.write_text("unknown", encoding="utf-8")
            adapter = mock.Mock()
            adapter.uninstall.side_effect = errors.InstallError("service remains")
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(uninstall, "adapter", return_value=adapter),
                mock.patch.object(uninstall, "_stop_proxy") as stop,
                mock.patch.object(sys, "argv", ["uninstall.py", "--purge", "--keep-config"]),
                self.assertRaisesRegex(SystemExit, "service remains"),
            ):
                uninstall.main()
            self.assertTrue(marker.exists())
            stop.assert_not_called()

    def test_purge_preserves_unknown_install_content_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            install_dir = codex_home / "dmx-proxy"
            unknown = install_dir / "operator-note.txt"
            unknown.parent.mkdir(parents=True)
            unknown.write_text("keep\n", encoding="utf-8")
            adapter = mock.Mock(status=mock.Mock(return_value="absent"))
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(uninstall, "adapter", return_value=adapter),
                mock.patch.object(uninstall, "_stop_proxy", return_value=0),
                mock.patch.object(
                    uninstall.process, "verified_proxy_listener_pids", return_value=[]
                ),
                mock.patch.object(
                    uninstall.projection,
                    "purge_installed_projection",
                    return_value=("operator-note.txt",),
                ),
                mock.patch.object(sys, "argv", ["uninstall.py", "--purge", "--keep-config"]),
                self.assertRaisesRegex(SystemExit, "unknown install content remains"),
            ):
                uninstall.main()
            self.assertEqual(unknown.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
