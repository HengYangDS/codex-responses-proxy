#!/usr/bin/env python3
"""Contracts for installed status, route control, and protocol-v2 reload."""

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
from codex_dmx_proxy import errors
from codex_dmx_proxy import process  # noqa: E402
from codex_dmx_proxy.release import transaction as payload_transaction  # noqa: E402
from codex_dmx_proxy.route import management as route_state  # noqa: E402
from tests.support.repository_fixtures import install_context  # noqa: E402
from tests.test_payload_transactions import begin_transaction, released_fixture  # noqa: E402


class TestControllerLifecycle(unittest.TestCase):
    def test_control_status_enable_disable_uses_installed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = install_context(root)
            transaction = begin_transaction(ctx, released_fixture())
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
            transaction = begin_transaction(ctx, released_fixture())
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
            initial = begin_transaction(ctx, released_fixture("1.2.2"))
            initial.commit_projection()
            initial.finalize({"pid": 1})
            transaction = begin_transaction(ctx, released_fixture("1.2.3"))
            transaction.commit_projection()
            transaction.preserve_for_recovery("handoff outcome unknown")
            journal_path = Path(payload_transaction.transaction_journal_path(ctx))
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
            journal_path.write_bytes(payload_transaction.digest.canonical_json(journal))
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
            transaction = begin_transaction(ctx, released_fixture())
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

    def test_reload_refuses_legacy_listener_without_mutation(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        with (
            mock.patch.object(control, "_runtime_metrics", return_value={"pid": 12345}),
            mock.patch.object(process, "terminate_pid") as terminate,
        ):
            with self.assertRaisesRegex(errors.InstallError, "source-side installer"):
                control.reload(ctx)
        terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
