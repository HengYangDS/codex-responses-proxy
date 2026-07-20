#!/usr/bin/env python3
"""Structured tests for codex-dmx-proxy — no real service registration.

Covers the parts that must be correct on all three OSes without needing to run the
platform service managers: config rewrite, python resolution, and the exact content
of each platform's generated service definition (plist / systemd unit / task XML).

Run: python3 tests/test_package.py
"""

import hashlib
import os
import sys
import tempfile
import threading
import unittest
import json
import subprocess
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            self.assertTrue((Path(ctx.install_dir) / "governance.py").is_file())
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

    def test_copy_payload_removes_only_superseded_launchd_debug_sinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            log_dir = Path(ctx.log_dir)
            log_dir.mkdir(parents=True)
            for filename in ("dmx-watchdog.out.log", "dmx-watchdog.err.log"):
                (log_dir / filename).write_text("legacy raw output", encoding="utf-8")
            retained = log_dir / "dmx-watchdog.log"
            retained.write_text("structured retained log", encoding="utf-8")

            install.copy_payload(ctx)

            self.assertFalse((log_dir / "dmx-watchdog.out.log").exists())
            self.assertFalse((log_dir / "dmx-watchdog.err.log").exists())
            self.assertEqual(retained.read_text(encoding="utf-8"), "structured retained log")

    def test_staged_payload_commit_preserves_aigw_route_state_and_swaps_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._managed_context(Path(tmp))
            install.copy_payload(ctx)
            state = common.make_aigw_install_state(
                ctx,
                aigw_config_path=str(Path(tmp) / "aigw.toml"),
                account="dmx",
                direct_url="https://www.dmxapi.cn/v1",
            )
            common.write_install_state(ctx, state)
            before_state = Path(common.install_state_path(ctx)).read_text(encoding="utf-8")
            before_manifest = Path(common.payload_manifest_path(ctx)).read_text(encoding="utf-8")

            stage = common.stage_payload_transaction(ctx, ROOT)
            Path(stage, "VERSION").write_text("9.9.9\n", encoding="utf-8")
            common.write_payload_manifest(
                common.InstallContext(
                    home=ctx.home,
                    install_dir=stage,
                    proxy_script=str(Path(stage) / "proxy" / "dmx_responses_proxy.py"),
                    watchdog_script=str(Path(stage) / "watchdog" / "watchdog.py"),
                    python=ctx.python,
                    codex_config=ctx.codex_config,
                    log_dir=ctx.log_dir,
                )
            )

            common.commit_payload_transaction(ctx, stage)

            self.assertEqual(Path(ctx.install_dir, "VERSION").read_text(encoding="utf-8"), "9.9.9\n")
            self.assertEqual(Path(common.install_state_path(ctx)).read_text(encoding="utf-8"), before_state)
            self.assertNotEqual(Path(common.payload_manifest_path(ctx)).read_text(encoding="utf-8"), before_manifest)
            ok, detail = common.verify_payload_manifest(ctx)
            self.assertTrue(ok, detail)
            common.restore_payload_transaction(ctx)
            self.assertEqual(Path(ctx.install_dir, "VERSION").read_text(encoding="utf-8"), Path(ROOT, "VERSION").read_text(encoding="utf-8"))
            common.finalize_payload_transaction(ctx)
            self.assertFalse(Path(common.payload_transaction_dir(ctx)).exists())

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

    def test_control_status_includes_secret_free_runtime_metrics_when_listener_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            install.copy_payload(ctx)
            runtime = {"uptime_seconds": 12, "active_responses": 0, "counters": {},
                       "upstream_classifications": {}, "last_failure": None}
            with mock.patch.object(control, "_runtime_metrics", return_value=runtime):
                evidence = control.status(ctx)
            self.assertEqual(evidence["runtime"], runtime)
            self.assertNotIn("authorization", json.dumps(evidence).lower())

    def test_installed_governance_reports_only_control_status_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._managed_context(root)
            install.copy_payload(ctx)
            governance = Path(ctx.install_dir) / "governance.py"
            installed_control = Path(ctx.install_dir) / "control.py"
            original = installed_control.read_text(encoding="utf-8")
            installed_control.write_text(
                original
                + "\n\ndef status(ctx):\n"
                + "    return {\"release\": \"fixture\", \"runtime\": {\"source_sha256\": \"a\" * 64}}\n",
                encoding="utf-8",
            )
            env = dict(os.environ, CODEX_HOME=str(root / ".codex"))
            result = subprocess.run(
                [sys.executable, str(governance), "--json"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {"release": "fixture", "runtime": {"source_sha256": "a" * 64}},
            )

    def test_reload_refuses_when_the_listener_cannot_acknowledge_drain(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_set_listener_drain", side_effect=common.InstallError("listener drain control is unavailable")),
            mock.patch.object(control, "_legacy_drain_listener", side_effect=common.InstallError("legacy listener did not remain idle")),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            with self.assertRaisesRegex(common.InstallError, "operator-approved maintenance window"):
                control.reload(ctx)
        terminate.assert_not_called()

    def test_reload_drains_before_terminating_the_verified_listener(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_drain_listener", return_value={"listener": 12345, "runtime": {"draining": True, "active_responses": 0}}),
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[54321]]),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=0.1)
        self.assertEqual(result, {"old_pid": 12345, "new_pid": 54321})
        terminate.assert_called_once_with(12345)

    def test_reload_reopens_admission_when_watchdog_replacement_times_out(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", return_value={"listener": 12345, "runtime": {"draining": True, "active_responses": 0}}),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(common, "terminate_pid"),
            mock.patch.object(control, "_set_listener_drain") as reopen,
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "service restored to admission"):
                control.reload(ctx, timeout_seconds=0.1)
        reopen.assert_called_once_with(ctx, enabled=False)

    def test_upgrade_refuses_before_payload_commit_when_drain_does_not_complete(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener did not drain active Responses")),
            mock.patch.object(common, "commit_payload_transaction") as commit,
        ):
            with self.assertRaisesRegex(common.InstallError, "did not drain"):
                control.upgrade_from_stage(ctx, str(stage))
        commit.assert_not_called()

    def test_upgrade_rolls_back_when_watchdog_does_not_replace_listener(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        stage = Path(tempfile.mkdtemp())
        (stage / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_drain_listener", return_value={"listener": 12345, "runtime": {"draining": True, "active_responses": 0}}),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", return_value={"release": "old"}),
            mock.patch.object(common, "commit_payload_transaction") as commit,
            mock.patch.object(common, "restore_payload_transaction") as restore,
            mock.patch.object(common, "finalize_payload_transaction") as finalize,
            mock.patch.object(control, "_set_listener_drain"),
            mock.patch.object(common, "terminate_pid"),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "payload restored"):
                control.upgrade_from_stage(ctx, str(stage), timeout_seconds=0.1)
        commit.assert_called_once_with(ctx, str(stage))
        restore.assert_called_once_with(ctx)
        finalize.assert_called_once_with(ctx)

    def test_drain_listener_waits_for_zero_after_admission_is_closed(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        states = [
            {"draining": True, "active_responses": 1},
            {"draining": True, "active_responses": 0},
        ]
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_set_listener_drain", return_value={"listener": 12345, "runtime": states[0]}),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", side_effect=states),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 0.0, 0.1]),
            mock.patch.object(control.time, "sleep"),
        ):
            drained = control._drain_listener(ctx, 1.0)
        self.assertEqual(drained["listener"], 12345)
        self.assertEqual(drained["runtime"]["active_responses"], 0)

    def test_drain_listener_reopens_admission_after_timeout(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(control, "_set_listener_drain", side_effect=[
                {"listener": 12345, "runtime": {"draining": True, "active_responses": 1}},
                {"listener": 12345, "runtime": {"draining": False, "active_responses": 1}},
            ]) as set_drain,
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", return_value={"draining": True, "active_responses": 1}),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "service restored to admission"):
                control._drain_listener(ctx, 0.5)
        self.assertEqual(set_drain.call_args_list[-1], mock.call(ctx, enabled=False))

    def test_legacy_bootstrap_requires_two_idle_samples_before_payload_mutation(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        snapshots = [
            {"active_responses": 0},
            {"active_responses": 1},
            {"active_responses": 0},
            {"active_responses": 0},
        ]
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", side_effect=snapshots),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 1.2, 1.2]),
            mock.patch.object(control.time, "sleep"),
        ):
            drained = control._legacy_drain_listener(ctx, 2.0, required_idle_seconds=1.0)
        self.assertTrue(drained["legacy"])
        self.assertEqual(drained["listener"], 12345)
        self.assertEqual(drained["runtime"]["active_responses"], 0)

    def test_legacy_bootstrap_refuses_when_idle_window_does_not_hold(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", return_value={"active_responses": 1}),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "payload was not changed"):
                control._legacy_drain_listener(ctx, 0.5)

    def test_bootstrap_uses_legacy_path_only_when_atomic_control_is_unavailable(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener drain control is unavailable")),
            mock.patch.object(control, "_legacy_drain_listener", return_value={"listener": 12345, "legacy": True}) as legacy,
        ):
            result = control._drain_listener_with_legacy_bootstrap(ctx, 1.0, allow_legacy_bootstrap=True)
        self.assertTrue(result["legacy"])
        legacy.assert_called_once_with(ctx, 1.0, required_idle_seconds=5.0)

    def test_bootstrap_requires_explicit_operator_approval_for_a_legacy_listener(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener drain control is unavailable")),
            mock.patch.object(control, "_legacy_drain_listener") as legacy,
        ):
            with self.assertRaisesRegex(common.InstallError, "operator-approved maintenance window"):
                control._drain_listener_with_legacy_bootstrap(ctx, 1.0)
        legacy.assert_not_called()

    def test_forced_legacy_bootstrap_requires_approval_and_a_verified_listener(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener drain control is unavailable")),
            mock.patch.object(common, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_legacy_drain_listener") as legacy,
        ):
            result = control._drain_listener_with_legacy_bootstrap(
                ctx,
                1.0,
                allow_legacy_bootstrap=True,
                force_legacy_bootstrap=True,
            )
        self.assertEqual(result, {"listener": 12345, "legacy": True, "forced": True})
        legacy.assert_not_called()

    def test_forced_legacy_bootstrap_still_refuses_payload_integrity_failure(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener drain control is unavailable")),
            mock.patch.object(common, "verify_payload_manifest", return_value=(False, "hash mismatch")),
            mock.patch.object(common, "verified_proxy_listener_pids") as listeners,
        ):
            with self.assertRaisesRegex(common.InstallError, "payload integrity check failed"):
                control._drain_listener_with_legacy_bootstrap(
                    ctx,
                    1.0,
                    allow_legacy_bootstrap=True,
                    force_legacy_bootstrap=True,
                )
        listeners.assert_not_called()

    def test_bootstrap_does_not_downgrade_an_atomic_drain_failure(self):
        ctx = self._managed_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_drain_listener", side_effect=common.InstallError("listener did not drain active Responses")),
            mock.patch.object(control, "_legacy_drain_listener") as legacy,
        ):
            with self.assertRaisesRegex(common.InstallError, "did not drain"):
                control._drain_listener_with_legacy_bootstrap(ctx, 1.0)
        legacy.assert_not_called()

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
        self.assertIn("DMX_PROXY_LOG_MAX_BYTES", xml)
        self.assertIn(str(common.DEFAULT_PROXY_LOG_MAX_BYTES), xml)
        self.assertIn("DMX_WATCHDOG_LOG_BACKUP_COUNT", xml)
        self.assertIn("<string>/dev/null</string>", xml)
        self.assertNotIn("dmx-watchdog.out.log", xml)
        self.assertNotIn("dmx-watchdog.err.log", xml)

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
        self.assertIn(
            f"Environment=DMX_PROXY_LOG_MAX_BYTES={common.DEFAULT_PROXY_LOG_MAX_BYTES}",
            unit,
        )
        self.assertIn(
            f"Environment=DMX_WATCHDOG_LOG_BACKUP_COUNT={common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}",
            unit,
        )

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
        self.assertIn(
            f'set "DMX_PROXY_LOG_MAX_BYTES={common.DEFAULT_PROXY_LOG_MAX_BYTES}"',
            launcher,
        )
        self.assertIn(
            f'set "DMX_WATCHDOG_LOG_BACKUP_COUNT={common.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT}"',
            launcher,
        )


class TestWatchdogLogging(unittest.TestCase):
    def _watchdog_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "dmx_watchdog_for_test",
            Path(ROOT, "watchdog", "watchdog.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_watchdog_log_is_bounded_and_redacts_secret_shaped_values(self):
        watchdog = self._watchdog_module()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "watchdog.log"
            old_path = watchdog.LOG_PATH
            old_max = watchdog.LOG_MAX_BYTES
            old_backups = watchdog.LOG_BACKUP_COUNT
            watchdog.LOG_PATH = str(log_path)
            watchdog.LOG_MAX_BYTES = 4096
            watchdog.LOG_BACKUP_COUNT = 0
            try:
                watchdog._log("authorization: Bearer super-secret-token encrypted=gAAAA_replay_secret")
                log_path.write_bytes(b"x" * 8192)
                watchdog._log("event=rotation_probe")
            finally:
                watchdog.LOG_PATH = old_path
                watchdog.LOG_MAX_BYTES = old_max
                watchdog.LOG_BACKUP_COUNT = old_backups

            text = log_path.read_text(encoding="utf-8")
            size = log_path.stat().st_size
            mode = log_path.stat().st_mode & 0o777
        self.assertNotIn("super-secret-token", text)
        self.assertNotIn("gAAAA_replay_secret", text)
        self.assertIn("log_retention_discarded_oversized_bytes=8192", text)
        self.assertLessEqual(size, 4096)
        self.assertEqual(mode, 0o600)


class TestProxySanitize(unittest.TestCase):
    """Verify the packaged proxy's core stripping logic still works."""
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "proxy"))
        import dmx_responses_proxy as p
        self.p = p
        self.p._reset_runtime_metrics_for_test()

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

    def test_retries_gateway_524_as_transient_upstream_failure(self):
        self.assertEqual(self.p._is_transient_upstream(524, b"gateway timeout"), "full")

    def test_retries_dmx_empty_response_477_as_transient_upstream_failure(self):
        error = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        self.assertEqual(self.p._is_transient_upstream(477, error), "full")

    def test_does_not_retry_unrelated_477(self):
        self.assertEqual(self.p._is_transient_upstream(477, b'{"error":"unprocessable"}'), "")
        self.assertEqual(
            self.p._is_transient_upstream(
                477,
                b'{"error":{"type":"other_gateway","code":"empty_response"}}',
            ),
            "",
        )

    def test_retries_upstream_response_failed_400_once(self):
        error = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        self.assertEqual(self.p._is_transient_upstream(400, error), "full")

    def test_response_failed_compaction_keeps_complete_tool_pairs_and_latest_user(self):
        """Fallback removes only an old prefix; no retained output is orphaned."""
        body = json.dumps({
            "prompt_cache_key": "cache-key-must-not-reach-the-fallback",
            "input": [
                {"type": "message", "role": "user", "content": "old" + "x" * 300_000},
                {
                    "type": "custom_tool_call",
                    "call_id": "custom-1",
                    "name": "exec",
                    "input": "{}",
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": "custom-1",
                    "output": "y" * 300_000,
                },
                {
                    "type": "function_call",
                    "call_id": "function-1",
                    "name": "wait",
                    "arguments": "{}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "function-1",
                    "output": "done",
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "latest user context must survive",
                },
            ],
        }).encode()

        compact, detail = self.p._compact_response_failed_request(body)

        self.assertIsNotNone(compact)
        self.assertIsNotNone(detail)
        self.assertGreaterEqual(detail["removed_inputs"], 1)
        self.assertLessEqual(len(compact), self.p.RESPONSE_FAILED_COMPACTION_BUDGET)
        obj = json.loads(compact)
        self.assertNotIn("prompt_cache_key", obj)
        self.assertEqual(obj["input"][-1]["content"], "latest user context must survive")
        calls = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call", "function_call")
        }
        outputs = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call_output", "function_call_output")
        }
        self.assertTrue(outputs.issubset(calls))
        self.assertIn("function-1", calls)

    def test_response_failed_compaction_never_starts_at_an_orphaned_tool_output(self):
        body = json.dumps({
            "input": [
                {"type": "message", "role": "user", "content": "old" + "x" * 10_000},
                {
                    "type": "custom_tool_call",
                    "call_id": "custom-oversize",
                    "name": "exec",
                    "input": "{}",
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": "custom-oversize",
                    "output": "y" * 600_000,
                },
                {"type": "message", "role": "user", "content": "newest user context"},
            ],
        }).encode()

        compact, detail = self.p._compact_response_failed_request(body)

        self.assertIsNotNone(compact)
        self.assertEqual(detail["removed_inputs"], 3)
        obj = json.loads(compact)
        self.assertEqual(obj["input"], [
            {"type": "message", "role": "user", "content": "newest user context"},
        ])

    def test_response_failed_compaction_keeps_latest_user_when_tool_work_follows_it(self):
        body = json.dumps({
            "input": [
                {"type": "message", "role": "user", "content": "old" + "x" * 300_000},
                {"type": "message", "role": "user", "content": "latest user context"},
                {
                    "type": "custom_tool_call",
                    "call_id": "latest-call",
                    "name": "exec",
                    "input": "{}",
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": "latest-call",
                    "output": "y" * 300_000,
                },
            ],
        }).encode()

        compact, detail = self.p._compact_response_failed_request(body)

        self.assertIsNotNone(compact)
        self.assertEqual(detail["removed_inputs"], 1)
        obj = json.loads(compact)
        self.assertEqual(obj["input"][0]["content"], "latest user context")

    def test_response_failed_compaction_reduces_an_already_sub_budget_failure(self):
        body = json.dumps({
            "prompt_cache_key": "stale-full-history-key",
            "input": [
                {"type": "message", "role": "user", "content": "old" + "x" * 280_000},
                {"type": "message", "role": "user", "content": "latest user context"},
                {
                    "type": "custom_tool_call",
                    "call_id": "latest-call",
                    "name": "exec",
                    "input": "{}",
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": "latest-call",
                    "output": "y" * 180_000,
                },
            ],
        }).encode()
        self.assertLess(len(body), self.p.RESPONSE_FAILED_COMPACTION_BUDGET)

        compact, detail = self.p._compact_response_failed_request(body)

        self.assertIsNotNone(compact)
        self.assertLessEqual(len(compact), len(body) // 2)
        self.assertEqual(detail["removed_inputs"], 1)
        self.assertNotIn("prompt_cache_key", json.loads(compact))

    def test_response_failed_compaction_uses_smallest_safe_suffix_when_budget_is_impossible(self):
        body = json.dumps({
            "input": [
                {"type": "message", "role": "user", "content": "old context"},
                {"type": "message", "role": "user", "content": "latest user context"},
                {
                    "type": "custom_tool_call",
                    "call_id": "latest-call",
                    "name": "exec",
                    "input": "{}",
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": "latest-call",
                    "output": "y" * 220_000,
                },
            ],
        }).encode()

        compact, detail = self.p._compact_response_failed_request(body, budget=20_000)

        self.assertIsNotNone(compact)
        self.assertFalse(detail["budget_met"])
        self.assertLess(len(compact), len(body))
        obj = json.loads(compact)
        self.assertEqual(obj["input"][0]["content"], "latest user context")
        self.assertTrue(self.p._tool_pair_boundary_is_safe(obj["input"], 0))

    def test_response_failed_compaction_is_a_noop_when_no_safe_suffix_fits(self):
        body = json.dumps({
            "tools": [{"type": "function", "name": "huge", "parameters": "x" * 600_000}],
            "prompt_cache_key": "must-remain-on-original-request",
            "input": [
                {"type": "message", "role": "user", "content": "newest user context"},
            ],
        }).encode()

        compact, detail = self.p._compact_response_failed_request(body)

        self.assertIsNone(compact)
        self.assertIsNone(detail)
        self.assertEqual(json.loads(body)["prompt_cache_key"], "must-remain-on-original-request")

    def test_response_failed_dialogue_recovery_keeps_latest_context_without_tool_replay(self):
        body = json.dumps({
            "prompt_cache_key": "stale-full-history-key",
            "input": [
                {"type": "message", "role": "developer", "content": "old policy"},
                {"type": "message", "role": "user", "content": "old request"},
                {"type": "custom_tool_call", "call_id": "old", "name": "tool", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "old", "output": "old result"},
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "intermediate request"},
                {"type": "message", "role": "user", "content": "latest user request"},
                {"type": "custom_tool_call", "call_id": "new", "name": "tool", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "new", "output": "large" + "x" * 100_000},
            ],
        }, separators=(",", ":")).encode()

        recovery, detail = self.p._recover_response_failed_dialogue(body)

        self.assertIsNotNone(recovery)
        self.assertIsNotNone(detail)
        recovered = json.loads(recovery)
        self.assertNotIn("prompt_cache_key", recovered)
        self.assertEqual(
            recovered["input"],
            [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user request"},
            ],
        )
        self.assertEqual(detail["dropped_input_items"], 7)
        self.assertLess(len(recovery), len(body))

    def test_response_failed_dialogue_recovery_allows_current_user_without_instruction(self):
        body = json.dumps({
            "input": [
                {"type": "message", "role": "user", "content": "old request"},
                {"type": "message", "role": "assistant", "content": "old response"},
                {"type": "message", "role": "user", "content": "latest user request"},
                {"type": "custom_tool_call", "call_id": "new", "name": "tool", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "new", "output": "large" + "x" * 100_000},
            ],
        }, separators=(",", ":")).encode()

        recovery, detail = self.p._recover_response_failed_dialogue(body)

        self.assertIsNotNone(recovery)
        self.assertIsNotNone(detail)
        self.assertEqual(
            json.loads(recovery)["input"],
            [{"type": "message", "role": "user", "content": "latest user request"}],
        )
        self.assertEqual(detail["retained_messages"], 1)

    def test_does_not_retry_unrelated_400(self):
        self.assertEqual(self.p._is_transient_upstream(400, b'{"error":"bad request"}'), "")

    def test_runtime_server_version_uses_version_file(self):
        self.assertEqual(self.p.release_version(), Path(ROOT, "VERSION").read_text(encoding="utf-8").strip())

    def test_runtime_status_reports_loaded_source_sha256(self):
        source = Path(ROOT, "proxy", "dmx_responses_proxy.py")
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(self.p.runtime_status()["source_sha256"], expected)

    def test_log_redacts_secrets_limits_line_length_and_removes_query_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            old_log_path = self.p.LOG_PATH
            self.p.LOG_PATH = str(log_path)
            try:
                self.p._log(
                    "authorization: Bearer super-secret-token "
                    "encrypted=gAAAA_replay_secret "
                    "x" * 2048
                )
                self.p._log(f"path={self.p._safe_request_path('/v1/responses?prompt=private')}")
            finally:
                self.p.LOG_PATH = old_log_path

            text = log_path.read_text(encoding="utf-8")
            mode = log_path.stat().st_mode & 0o777
        self.assertNotIn("super-secret-token", text)
        self.assertNotIn("gAAAA_replay_secret", text)
        self.assertNotIn("prompt=private", text)
        self.assertIn("[redacted]", text)
        self.assertIn("path=/v1/responses", text)
        self.assertEqual(mode, 0o600)
        self.assertLessEqual(max(len(line.encode("utf-8")) for line in text.splitlines()), self.p._LOG_LINE_MAX_BYTES + 96)

    def test_log_rotation_discards_an_oversized_legacy_segment_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            log_path.write_bytes(b"x" * 8192)
            old_log_path = self.p.LOG_PATH
            old_max = self.p.LOG_MAX_BYTES
            old_backups = self.p.LOG_BACKUP_COUNT
            self.p.LOG_PATH = str(log_path)
            self.p.LOG_MAX_BYTES = 4096
            self.p.LOG_BACKUP_COUNT = 1
            try:
                self.p._log("event=rotation_probe")
            finally:
                self.p.LOG_PATH = old_log_path
                self.p.LOG_MAX_BYTES = old_max
                self.p.LOG_BACKUP_COUNT = old_backups

            self.assertTrue(log_path.exists())
            self.assertLessEqual(log_path.stat().st_size, 4096)
            self.assertFalse((Path(tmp) / "proxy.log.1").exists())
            self.assertIn("log_retention_discarded_oversized_bytes=8192", log_path.read_text(encoding="utf-8"))

    def test_fail_open_on_non_json(self):
        raw = b"not json at all"
        out, note = self.p.sanitize_responses_body(raw)
        self.assertEqual(out, raw)                                # unchanged
        self.assertIn("passthrough", note)

    def test_clean_body_untouched(self):
        body = json.dumps({"input": [{"type": "message", "content": "hi"}]}).encode()
        out, note = self.p.sanitize_responses_body(body)
        self.assertIn("clean", note)


class TestProxyTransport(unittest.TestCase):
    """Exercise retry behavior through real local HTTP hops."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "proxy"))
        import dmx_responses_proxy as p
        self.p = p
        self.p._reset_runtime_metrics_for_test()

    def _serve_proxy(self, responses, log_dir):
        """Start a scripted upstream and the proxy, returning cleanup state."""
        received = []

        class UpstreamHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received.append(self.rfile.read(length))
                response = responses.pop(0)
                if isinstance(response, dict):
                    status = response.get("status", 200)
                    chunks = response.get("chunks", [])
                    started = response.get("started_event")
                    if started is not None:
                        started.set()
                    release = response.get("release_event")
                    if release is not None:
                        release.wait(timeout=5)
                    self.send_response(status)
                    self.send_header("Content-Type", response.get("content_type", "text/event-stream"))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for chunk in chunks:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    self.close_connection = True
                    return
                status, payload = response
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()

        old_upstream = self.p.UPSTREAM
        old_log_path = self.p.LOG_PATH
        self.p.UPSTREAM = f"http://127.0.0.1:{upstream.server_address[1]}"
        self.p.LOG_PATH = str(Path(log_dir) / "proxy.log")
        proxy = self.p._ResilientProxyServer(("127.0.0.1", 0), self.p.Handler)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()

        def cleanup():
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=2)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)
            self.p.UPSTREAM = old_upstream
            self.p.LOG_PATH = old_log_path

        return proxy.server_address[1], received, cleanup

    @staticmethod
    def _request(proxy_port, body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{proxy_port}/v1/responses",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)

    def test_recovers_response_failed_with_pair_safe_compact_request(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps({
            "model": "gpt-5.6-terra",
            "stream": False,
            "prompt_cache_key": "full-history-cache-key",
            "input": [
                {"type": "message", "role": "user", "content": "old" + "x" * 100_000},
                {"type": "function_call", "call_id": "call_old", "name": "tool", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "call_old", "output": "old result"},
                {"type": "message", "role": "user", "content": "latest user context"},
            ],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(400, response_failed), (200, success)], tmp,
            )
            try:
                response = self._request(port, body)
                with response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), success)
            finally:
                cleanup()

        self.assertEqual(received[0], body)
        self.assertEqual(len(received), 2)
        compact = json.loads(received[1])
        self.assertLess(len(received[1]), len(body))
        self.assertNotIn("prompt_cache_key", compact)
        self.assertEqual(compact["input"][-1]["content"], "latest user context")
        calls = {item["call_id"] for item in compact["input"] if item.get("type") in self.p._TOOL_CALL_TYPES}
        outputs = {item["call_id"] for item in compact["input"] if item.get("type") in self.p._TOOL_OUTPUT_TYPES}
        self.assertTrue(outputs.issubset(calls))

    def test_recovers_response_failed_with_dialogue_only_last_resort(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps({
            "model": "gpt-5.6-terra",
            "stream": False,
            "prompt_cache_key": "full-history-cache-key",
            "input": [
                {"type": "message", "role": "developer", "content": "old" + "x" * 100_000},
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user context"},
                {"type": "custom_tool_call", "call_id": "call_new", "name": "tool", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "call_new", "output": "tool result"},
            ],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(400, response_failed), (400, response_failed), (200, success)], tmp,
            )
            try:
                with (
                    mock.patch.object(self.p, "RESPONSE_FAILED_MAX_STAGES", 1),
                    mock.patch.object(self.p, "_log") as log,
                ):
                    response = self._request(port, body)
                    with response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), success)
                logs = "\n".join(call.args[0] for call in log.call_args_list)
            finally:
                cleanup()

        self.assertEqual(received[0], body)
        self.assertEqual(len(received), 3)
        recovery = json.loads(received[2])
        self.assertNotIn("prompt_cache_key", recovery)
        self.assertEqual(
            recovery["input"],
            [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user context"},
            ],
        )
        self.assertIn("event=response_failed_dialogue_recovery_accepted", logs)
        self.assertNotIn("event=response_failed_compact_recovery_accepted", logs)

    def test_normalizes_exhausted_response_failed_recovery_to_retryable_503(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        body = json.dumps({
            "model": "gpt-5.6-terra",
            "stream": False,
            "input": [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user context"},
                {"type": "custom_tool_call", "call_id": "call_new", "name": "tool", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "call_new", "output": "tool result"},
            ],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(400, response_failed), (400, response_failed)], tmp,
            )
            try:
                with mock.patch.object(self.p, "RESPONSE_FAILED_MAX_STAGES", 0):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        self._request(port, body)
                error = raised.exception
                with error:
                    self.assertEqual(error.code, 503)
                    self.assertEqual(error.headers["Retry-After"], "3")
                    payload = json.loads(error.read())
            finally:
                cleanup()

        self.assertEqual(len(received), 1)
        self.assertEqual(payload["error"]["code"], "response_failed_recovery_exhausted")

    def test_retries_classified_empty_response_with_byte_identical_request(self):
        empty_response = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps({
            "model": "gpt-5.6-terra",
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, empty_response), (200, success)], tmp,
            )
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    response = self._request(port, body)
                    with response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), success)
            finally:
                cleanup()

        self.assertEqual(received, [body, body])

    def test_runtime_metrics_classify_recovery_without_retaining_request_content(self):
        response_failed = b'{"error":{"code":"response_failed"}}'
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps({
            "stream": False,
            "input": [
                {"type": "reasoning", "encrypted_content": "secret-replay"},
                {"type": "message", "role": "user", "content": "old context"},
                {"type": "message", "role": "user", "content": "x" * 100_000},
                {"type": "message", "role": "user", "content": "private prompt"},
            ],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, _received, cleanup = self._serve_proxy(
                [(400, response_failed), (200, success)], tmp,
            )
            try:
                response = self._request(port, body)
                with response:
                    self.assertEqual(response.read(), success)
            finally:
                cleanup()

        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["responses_received"], 1)
        self.assertEqual(status["counters"]["encrypted_replayed_reasoning_items_stripped"], 1)
        self.assertEqual(status["counters"]["response_failed_compaction_attempts"], 1)
        self.assertEqual(status["counters"]["response_failed_compaction_accepted"], 1)
        self.assertEqual(status["upstream_classifications"]["response_failed"], 1)
        self.assertNotIn("private prompt", json.dumps(status))
        self.assertNotIn("secret-replay", json.dumps(status))

    def test_loopback_healthz_returns_machine_readable_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            port, _received, cleanup = self._serve_proxy([], tmp)
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                    f"http://127.0.0.1:{port}/healthz",
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Content-Type"], "application/json")
                    status = json.loads(response.read())
            finally:
                cleanup()

        self.assertIn("counters", status)
        self.assertIn("upstream_classifications", status)
        self.assertIsNone(status["last_failure"])

    def test_loopback_drain_rejects_new_responses_and_can_be_reopened(self):
        success = b'{"id":"resp_served","status":"completed"}'
        body = json.dumps({"stream": False, "input": []}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(200, success)], tmp)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                drain = urllib.request.Request(
                    f"http://127.0.0.1:{port}/control/drain", method="POST",
                )
                with opener.open(drain) as response:
                    snapshot = json.loads(response.read())
                self.assertTrue(snapshot["draining"])
                self.assertEqual(snapshot["active_responses"], 0)

                with self.assertRaises(urllib.error.HTTPError) as raised:
                    self._request(port, body)
                with raised.exception:
                    self.assertEqual(raised.exception.code, 503)
                    self.assertEqual(raised.exception.headers["Retry-After"], "1")
                    payload = json.loads(raised.exception.read())
                self.assertEqual(payload["error"]["code"], "proxy_draining")
                self.assertEqual(received, [])

                reopen = urllib.request.Request(
                    f"http://127.0.0.1:{port}/control/drain", method="DELETE",
                )
                with opener.open(reopen) as response:
                    self.assertFalse(json.loads(response.read())["draining"])
                response = self._request(port, body)
                with response:
                    self.assertEqual(response.read(), success)
            finally:
                cleanup()

        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["responses_rejected_while_draining"], 1)
        self.assertFalse(status["draining"])

    def test_drain_lease_expires_without_a_controller_rollback_request(self):
        self.p._reset_runtime_metrics_for_test()
        with mock.patch.object(self.p.time, "monotonic", side_effect=[10.0, 10.0, 12.1, 12.1, 12.1]):
            started = self.p._set_draining(True, lease_seconds=2)
            expired = self.p.runtime_status()
        self.assertTrue(started["draining"])
        self.assertFalse(expired["draining"])
        self.assertIsNone(expired["drain_lease_remaining_seconds"])
        self.assertEqual(expired["counters"]["drain_leases_expired"], 1)

    def test_drain_closes_admission_while_an_existing_response_finishes(self):
        success = b'{"id":"resp_served","status":"completed"}'
        body = json.dumps({"stream": False, "input": []}).encode()
        started = threading.Event()
        release = threading.Event()
        worker_result = {}

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([
                {
                    "status": 200,
                    "content_type": "application/json",
                    "chunks": [success],
                    "started_event": started,
                    "release_event": release,
                },
            ], tmp)
            try:
                def request_in_flight():
                    try:
                        with self._request(port, body) as response:
                            worker_result["body"] = response.read()
                    except BaseException as exc:  # asserted below; never hide a worker failure
                        worker_result["error"] = exc

                worker = threading.Thread(target=request_in_flight)
                worker.start()
                self.assertTrue(started.wait(timeout=2), "upstream never received the first Responses request")

                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                drain = urllib.request.Request(
                    f"http://127.0.0.1:{port}/control/drain", method="POST",
                )
                with opener.open(drain) as response:
                    snapshot = json.loads(response.read())
                self.assertTrue(snapshot["draining"])
                self.assertEqual(snapshot["active_responses"], 1)

                with self.assertRaises(urllib.error.HTTPError) as raised:
                    self._request(port, body)
                with raised.exception:
                    self.assertEqual(raised.exception.code, 503)
                    self.assertEqual(json.loads(raised.exception.read())["error"]["code"], "proxy_draining")
                self.assertEqual(received, [body])

                release.set()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive(), "in-flight request did not complete after drain")
                self.assertNotIn("error", worker_result)
                self.assertEqual(worker_result["body"], success)

                with opener.open(f"http://127.0.0.1:{port}/healthz") as response:
                    drained = json.loads(response.read())
                self.assertTrue(drained["draining"])
                self.assertEqual(drained["active_responses"], 0)
            finally:
                release.set()
                cleanup()

    def test_reconnects_a_pre_content_response_failed_stream(self):
        failed = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.failed"}\n\n',
            ],
        }
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"recovered"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([failed, recovered], tmp)
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    response = self._request(port, body)
                    with response:
                        payload = response.read()
            finally:
                cleanup()

        self.assertEqual(len(received), 2)
        self.assertIn(b"recovered", payload)
        self.assertEqual(payload.count(b'response.created'), 1)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["streams_pre_content_reconnect_attempts"], 1)
        self.assertEqual(status["counters"]["streams_completed"], 1)

    def test_normalizes_exhausted_pre_content_sse_failures_to_retryable_503(self):
        premature_eof = {"chunks": [b'data: {"type":"response.created"}\n\n']}
        body = json.dumps({"stream": True, "input": []}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([premature_eof] * 6, tmp)
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        self._request(port, body)
                error = raised.exception
                with error:
                    self.assertEqual(error.code, 503)
                    self.assertEqual(error.headers["Retry-After"], "3")
                    payload = json.loads(error.read())
            finally:
                cleanup()

        self.assertEqual(received, [body] * 6)
        self.assertEqual(payload["error"]["type"], "upstream_unavailable")
        self.assertEqual(payload["error"]["code"], "stream_pre_content_exhausted")
        self.assertEqual(payload["error"]["attempts"], 6)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["streams_pre_content_reconnect_attempts"], 5)
        self.assertEqual(status["counters"]["streams_pre_content_exhausted"], 1)
        self.assertEqual(status["counters"]["streams_failed"], 1)
        self.assertEqual(status["last_failure"]["classification"], "stream_pre_content_exhausted")

    def test_reconnects_a_pre_content_premature_eof(self):
        premature_eof = {"chunks": [b'data: {"type":"response.created"}\n\n']}
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([premature_eof, recovered], tmp)
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    response = self._request(port, body)
                    with response:
                        payload = response.read()
            finally:
                cleanup()

        self.assertEqual(len(received), 2)
        self.assertIn(b'"delta":"ok"', payload)
        self.assertEqual(self.p.runtime_status()["counters"]["streams_pre_content_reconnect_attempts"], 1)

    def test_does_not_reconnect_after_downstream_stream_bytes_are_committed(self):
        partial = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
            ],
        }
        unexpected_retry = {
            "chunks": [b'data: {"type":"response.completed"}\n\n'],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([partial, unexpected_retry], tmp)
            try:
                response = self._request(port, body)
                with response:
                    payload = response.read()
            finally:
                cleanup()

        self.assertEqual(len(received), 1)
        self.assertIn(b"partial", payload)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["streams_pre_content_reconnect_attempts"], 0)
        self.assertEqual(status["counters"]["streams_failed"], 1)

    def test_normalizes_exhausted_classified_empty_response_to_retryable_503(self):
        empty_response = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        body = json.dumps({
            "model": "gpt-5.6-terra",
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        }, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, empty_response)] * 4, tmp,
            )
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        self._request(port, body)
                error = raised.exception
                with error:
                    self.assertEqual(error.code, 503)
                    self.assertEqual(error.headers["Retry-After"], "3")
                    payload = json.loads(error.read())
            finally:
                cleanup()

        self.assertEqual(received, [body] * 4)
        self.assertEqual(payload["error"]["type"], "upstream_unavailable")
        self.assertEqual(payload["error"]["code"], "dmx_empty_response_exhausted")
        self.assertEqual(payload["error"]["attempts"], 4)

    def test_streaming_empty_response_exhaustion_emits_terminal_sse_error(self):
        empty_response = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        body = json.dumps({"stream": True, "input": []}, separators=(",", ":")).encode()

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(477, empty_response)] * 4, tmp)
            try:
                with mock.patch.object(self.p.time, "sleep", return_value=None):
                    response = self._request(port, body)
                    with response:
                        payload = response.read()
            finally:
                cleanup()

        self.assertEqual(received, [body] * 4)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        self.assertNotIn("Retry-After", response.headers)
        self.assertIn(b"event: error", payload)
        self.assertIn(b'"code":"dmx_empty_response_exhausted"', payload)

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


class TestGovernanceMetadata(unittest.TestCase):
    def test_lifecycle_scripts_do_not_prescribe_client_restart_or_new_thread(self):
        text = "\n".join(
            Path(ROOT, relative).read_text(encoding="utf-8").lower()
            for relative in ("install.py", "uninstall.py")
        )
        self.assertNotIn("fully " + "quit & reopen", text)
        self.assertNotIn("start a " + "new codex thread", text)
        self.assertIn("existing conversations remain unchanged", text)


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
        for forbidden in ("AIGW", "ChatGPT", "JetBrains", "subprocess", "write_text", "unlink", "sys.path.insert"):
            self.assertNotIn(forbidden, source)
        self.assertIn("control.status", source)

    def test_proxy_has_no_payload_or_header_dump_escape_hatch(self):
        source = Path(ROOT, "proxy", "dmx_responses_proxy.py").read_text(encoding="utf-8")
        for forbidden in ("DMX_DUMP_BODIES", "DMX_DUMP_HEADERS", "reject-"):
            self.assertNotIn(forbidden, source)

    def test_proxy_declares_bounded_secret_safe_log_contract(self):
        proxy_source = Path(ROOT, "proxy", "dmx_responses_proxy.py").read_text(encoding="utf-8")
        watchdog_source = Path(ROOT, "watchdog", "watchdog.py").read_text(encoding="utf-8")
        for required in (
            "DMX_PROXY_LOG_MAX_BYTES",
            "DMX_PROXY_LOG_BACKUP_COUNT",
            "_redact_log_message",
            "_safe_request_path",
            "streams_pre_content_exhausted",
            "stream_pre_content_exhausted",
        ):
            self.assertIn(required, proxy_source)
        for required in ("DMX_WATCHDOG_LOG_MAX_BYTES", "DMX_WATCHDOG_LOG_BACKUP_COUNT", "_redact_log_message"):
            self.assertIn(required, watchdog_source)

    def test_mit_license_is_present(self):
        license_text = Path(ROOT, "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
