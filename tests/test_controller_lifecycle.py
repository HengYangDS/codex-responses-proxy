#!/usr/bin/env python3
"""Contracts for installed status, route control, reload, and legacy bootstrap."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import control  # noqa: E402
from platform_adapters import common, payload, route_state  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402
from tests.test_payload_transactions import released_fixture  # noqa: E402


class TestControllerLifecycle(unittest.TestCase):
    def test_control_status_enable_disable_uses_installed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = payload.begin_transaction(ctx, released_fixture())
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
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

            control = Path(ctx.install_dir) / "control.py"
            env = dict(os.environ, CODEX_HOME=str(root / ".codex"))
            status = subprocess.run(
                [sys.executable, str(control), "status"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("route: enabled", status.stdout)
            disabled = subprocess.run(
                [sys.executable, str(control), "disable"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), direct)
            reenabled = subprocess.run(
                [sys.executable, str(control), "enable"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(reenabled.returncode, 0, reenabled.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), enabled)

    def test_control_status_includes_secret_free_runtime_metrics_when_listener_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = payload.begin_transaction(ctx, released_fixture())
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
            runtime = {
                "uptime_seconds": 12,
                "active_responses": 0,
                "counters": {},
                "upstream_classifications": {},
                "last_failure": None,
            }
            with mock.patch.object(control, "_runtime_metrics", return_value=runtime):
                evidence = control.status(ctx)
            self.assertEqual(evidence["runtime"], runtime)
            self.assertNotIn("authorization", json.dumps(evidence).lower())

    def test_control_status_json_reports_recovery_without_private_transaction_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            initial = payload.begin_transaction(ctx, released_fixture("1.2.2"))
            initial.commit_projection()
            initial.finalize({"pid": 1})
            transaction = payload.begin_transaction(ctx, released_fixture("1.2.3"))
            transaction.commit_projection()
            transaction.preserve_for_recovery("handoff outcome unknown")
            journal_path = Path(payload.transaction_journal_path(ctx))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            journal.update(
                {
                    "authorization": "Bearer secret-token",
                    "request_body": {"input": "private request"},
                    "stage_path": "/private/release-stage",
                    "reason": (
                        "handoff unknown; Authorization=Bearer secret-token; "
                        "body=private request; stage=/private/release-stage"
                    ),
                }
            )
            journal_path.write_bytes(payload._canonical_json(journal))
            before = journal_path.read_bytes()
            installed_control = Path(ctx.install_dir) / "control.py"
            env = dict(os.environ, CODEX_HOME=str(root / ".codex"))

            result = subprocess.run(
                [sys.executable, str(installed_control), "status", "--json"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(result.stdout)
            self.assertEqual(evidence["payload_transaction"]["state"], "recovery_required")
            self.assertNotIn("reason", evidence["payload_transaction"])
            for forbidden in ("secret-token", "private request", "/private/release-stage"):
                self.assertNotIn(forbidden, result.stdout)
            self.assertEqual(journal_path.read_bytes(), before)

    def test_installed_governance_reports_only_control_status_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = payload.begin_transaction(ctx, released_fixture())
            transaction.commit_projection()
            transaction.finalize({"pid": 1})
            governance = Path(ctx.install_dir) / "governance.py"
            installed_control = Path(ctx.install_dir) / "control.py"
            original = installed_control.read_text(encoding="utf-8")
            installed_control.write_text(
                original
                + "\n\ndef status(ctx):\n"
                + '    return {"release": "fixture", "runtime": {"serving_payload_sha256": "a" * 64}}\n',
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
                {"release": "fixture", "runtime": {"serving_payload_sha256": "a" * 64}},
            )

    def test_installed_governance_reports_recovery_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            initial = payload.begin_transaction(ctx, released_fixture("1.2.2"))
            initial.commit_projection()
            initial.finalize({"pid": 1})
            transaction = payload.begin_transaction(ctx, released_fixture("1.2.3"))
            transaction.commit_projection()
            transaction.preserve_for_recovery("handoff outcome unknown")
            journal_path = Path(payload.transaction_journal_path(ctx))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            journal.update(
                {
                    "authorization": "Bearer secret-token",
                    "request_body": {"input": "private request"},
                    "stage_path": "/private/release-stage",
                    "reason": (
                        "handoff unknown; Authorization=Bearer secret-token; "
                        "body=private request; stage=/private/release-stage"
                    ),
                }
            )
            journal_path.write_bytes(payload._canonical_json(journal))
            before = journal_path.read_bytes()
            governance = Path(ctx.install_dir) / "governance.py"
            env = dict(os.environ, CODEX_HOME=str(root / ".codex"))

            result = subprocess.run(
                [sys.executable, str(governance), "--json"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(result.stdout)
            self.assertEqual(evidence["payload_transaction"]["state"], "recovery_required")
            self.assertNotIn("reason", evidence["payload_transaction"])
            for forbidden in ("secret-token", "private request", "/private/release-stage"):
                self.assertNotIn(forbidden, result.stdout)
            self.assertEqual(journal_path.read_bytes(), before)

    def test_reload_refuses_when_the_listener_cannot_acknowledge_drain(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=None),
            mock.patch.object(
                control,
                "_wait_for_quiescent_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": False, "active_responses": 0},
                },
            ),
            mock.patch.object(
                control,
                "_set_listener_drain",
                side_effect=common.InstallError("listener drain control is unavailable"),
            ),
            mock.patch.object(
                control,
                "_legacy_drain_listener",
                side_effect=common.InstallError("legacy listener did not remain idle"),
            ),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            with self.assertRaisesRegex(
                common.InstallError, "operator-approved maintenance window"
            ):
                control.reload(ctx)
        terminate.assert_not_called()

    def test_reload_drains_before_terminating_the_verified_listener(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=None),
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(
                control,
                "_drain_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": True, "active_responses": 0},
                },
            ),
            mock.patch.object(common, "verified_proxy_listener_pids", side_effect=[[54321]]),
            mock.patch.object(common, "terminate_pid") as terminate,
        ):
            result = control.reload(ctx, timeout_seconds=0.1)
        self.assertEqual(result, {"old_pid": 12345, "new_pid": 54321})
        terminate.assert_called_once_with(12345)

    def test_reload_reopens_admission_when_watchdog_replacement_times_out(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=None),
            mock.patch.object(
                control,
                "_drain_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": True, "active_responses": 0},
                },
            ),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(common, "terminate_pid"),
            mock.patch.object(control, "_set_listener_drain") as reopen,
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "service restored to admission"):
                control.reload(ctx, timeout_seconds=0.1)
        reopen.assert_called_once_with(ctx, enabled=False)

    def test_drain_listener_waits_for_zero_after_admission_is_closed(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_wait_for_quiescent_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": False, "active_responses": 0},
                },
            ),
            mock.patch.object(
                control,
                "_set_listener_drain",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": True, "active_responses": 0},
                },
            ),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(
                control, "_runtime_metrics", return_value={"draining": True, "active_responses": 0}
            ),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 0.1]),
            mock.patch.object(control.time, "sleep"),
        ):
            drained = control._drain_listener(ctx, 1.0)
        self.assertEqual(drained["listener"], 12345)
        self.assertEqual(drained["runtime"]["active_responses"], 0)

    def test_drain_listener_reopens_admission_after_timeout(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_wait_for_quiescent_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": False, "active_responses": 0},
                },
            ),
            mock.patch.object(
                control,
                "_set_listener_drain",
                side_effect=[
                    {"listener": 12345, "runtime": {"draining": True, "active_responses": 1}},
                    {"listener": 12345, "runtime": {"draining": False, "active_responses": 1}},
                ],
            ) as set_drain,
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(
                control, "_runtime_metrics", return_value={"draining": True, "active_responses": 1}
            ),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "service restored to admission"):
                control._drain_listener(ctx, 0.5)
        self.assertEqual(set_drain.call_args_list[-1], mock.call(ctx, enabled=False))

    def test_quiescence_preflight_keeps_admission_open_until_idle_window_is_proven(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(
                control,
                "_runtime_metrics",
                return_value={"draining": False, "active_responses": 0},
            ),
            mock.patch.object(
                control.time,
                "monotonic",
                side_effect=[
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    1.0,
                    2.0,
                    2.0,
                    3.0,
                    3.0,
                    4.0,
                    4.0,
                    5.0,
                    5.0,
                ],
            ),
            mock.patch.object(control.time, "sleep"),
        ):
            result = control._wait_for_quiescent_listener(ctx, 10.0, quiet_seconds=5.0)
        self.assertEqual(result["listener"], 12345)
        self.assertEqual(result["runtime"]["active_responses"], 0)

    def test_quiescence_preflight_refuses_without_closing_admission_when_busy(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(
                control, "_runtime_metrics", return_value={"draining": False, "active_responses": 1}
            ),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "no drain was started"):
                control._wait_for_quiescent_listener(ctx, 0.5)

    def test_drain_refuses_if_listener_changes_between_quiescence_and_admission_close(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_wait_for_quiescent_listener",
                return_value={
                    "listener": 12345,
                    "runtime": {"draining": False, "active_responses": 0},
                },
            ),
            mock.patch.object(
                control,
                "_set_listener_drain",
                side_effect=[
                    {"listener": 54321, "runtime": {"draining": True, "active_responses": 0}},
                    {"listener": 54321, "runtime": {"draining": False, "active_responses": 0}},
                ],
            ) as set_drain,
        ):
            with self.assertRaisesRegex(common.InstallError, "changed while admission was closing"):
                control._drain_listener(ctx, 1.0)
        self.assertEqual(set_drain.call_args_list[-1], mock.call(ctx, enabled=False))

    def test_legacy_bootstrap_requires_two_idle_samples_before_payload_mutation(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        snapshots = [
            {"active_responses": 0},
            {"active_responses": 1},
            {"active_responses": 0},
            {"active_responses": 0},
        ]
        with (
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", side_effect=snapshots),
            mock.patch.object(
                control.time, "monotonic", side_effect=[0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 1.2, 1.2]
            ),
            mock.patch.object(control.time, "sleep"),
        ):
            drained = control._legacy_drain_listener(ctx, 2.0, required_idle_seconds=1.0)
        self.assertTrue(drained["legacy"])
        self.assertEqual(drained["listener"], 12345)
        self.assertEqual(drained["runtime"]["active_responses"], 0)

    def test_legacy_bootstrap_refuses_when_idle_window_does_not_hold(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
            mock.patch.object(common, "verified_proxy_listener_pids", return_value=[12345]),
            mock.patch.object(control, "_runtime_metrics", return_value={"active_responses": 1}),
            mock.patch.object(control.time, "monotonic", side_effect=[0.0, 1.0]),
        ):
            with self.assertRaisesRegex(common.InstallError, "payload was not changed"):
                control._legacy_drain_listener(ctx, 0.5)

    def test_bootstrap_uses_legacy_path_only_when_atomic_control_is_unavailable(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_drain_listener",
                side_effect=common.InstallError("listener drain control is unavailable"),
            ),
            mock.patch.object(
                control, "_legacy_drain_listener", return_value={"listener": 12345, "legacy": True}
            ) as legacy,
        ):
            result = control._drain_listener_with_legacy_bootstrap(
                ctx, 1.0, allow_legacy_bootstrap=True
            )
        self.assertTrue(result["legacy"])
        legacy.assert_called_once_with(ctx, 1.0, required_idle_seconds=5.0)

    def test_bootstrap_requires_explicit_operator_approval_for_a_legacy_listener(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_drain_listener",
                side_effect=common.InstallError("listener drain control is unavailable"),
            ),
            mock.patch.object(control, "_legacy_drain_listener") as legacy,
        ):
            with self.assertRaisesRegex(
                common.InstallError, "operator-approved maintenance window"
            ):
                control._drain_listener_with_legacy_bootstrap(ctx, 1.0)
        legacy.assert_not_called()

    def test_forced_legacy_bootstrap_requires_approval_and_a_verified_listener(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_drain_listener",
                side_effect=common.InstallError("listener drain control is unavailable"),
            ),
            mock.patch.object(payload, "verify_payload_manifest", return_value=(True, "ok")),
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
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_drain_listener",
                side_effect=common.InstallError("listener drain control is unavailable"),
            ),
            mock.patch.object(
                payload, "verify_payload_manifest", return_value=(False, "hash mismatch")
            ),
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
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(
                control,
                "_drain_listener",
                side_effect=common.InstallError("listener did not drain active Responses"),
            ),
            mock.patch.object(control, "_legacy_drain_listener") as legacy,
        ):
            with self.assertRaisesRegex(common.InstallError, "did not drain"):
                control._drain_listener_with_legacy_bootstrap(ctx, 1.0)
        legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
