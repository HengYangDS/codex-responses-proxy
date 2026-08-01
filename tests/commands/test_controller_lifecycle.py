#!/usr/bin/env python3
"""Contracts for installed status and protocol-v2 reload."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.commands import control  # noqa: E402
from codex_responses_proxy.commands import install  # noqa: E402
from codex_responses_proxy.commands import uninstall  # noqa: E402
from codex_responses_proxy import errors
from codex_responses_proxy.supervision import process  # noqa: E402
from codex_responses_proxy.payload import transaction as payload_transaction  # noqa: E402
from tests.deployment.fixtures import install_context  # noqa: E402
from tests.payload.fixtures import begin_transaction, released_fixture  # noqa: E402


class TestControllerLifecycle(unittest.TestCase):
    def test_control_main_projects_status_and_reload_outputs(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        status = {
            "release": None,
            "payload_integrity": {"ok": False, "detail": "missing"},
            "service": "absent",
            "listener_pids": [],
            "runtime": None,
            "payload_transaction": None,
        }
        cases = (
            (["control", "status"], status, "runtime metrics: unavailable"),
            (["control", "status", "--json"], status, '"service": "absent"'),
            (
                ["control", "reload", "--timeout-seconds", "4"],
                {"old_pid": 1, "new_pid": 2},
                "verified proxy listener: 1 -> 2",
            ),
        )
        for argv, evidence, expected in cases:
            with (
                self.subTest(argv=argv),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(control, "_context", return_value=ctx),
                mock.patch.object(
                    control,
                    "status" if argv[1] == "status" else "reload",
                    return_value=evidence,
                ),
                mock.patch("builtins.print") as printed,
            ):
                control.main()
            self.assertIn(expected, "\n".join(str(call.args[0]) for call in printed.call_args_list))

    def test_control_reads_bounded_runtime_and_recovers_finalized_reload(self):
        ctx = install_context(Path(tempfile.mkdtemp()))

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"pid": 7}'

        with mock.patch.object(control.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = Response()
            self.assertEqual(control._runtime_metrics(ctx), {"pid": 7})
        with mock.patch.object(control.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = OSError("offline")
            self.assertIsNone(control._runtime_metrics(ctx))
        with mock.patch.object(control.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = Response()
            build.return_value.open.return_value.status = 503
            self.assertIsNone(control._runtime_metrics(ctx))

        runtime = {"pid": 7}
        expected = {"transaction_id": "tx"}
        with (
            mock.patch.object(control, "_runtime_metrics", return_value=runtime),
            mock.patch.object(control.handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                control.projection, "verify_payload_manifest", return_value=(True, "ok")
            ),
            mock.patch.object(control.handoff, "expected_metadata", return_value=expected),
            mock.patch.object(control.handoff, "request", side_effect=OSError("lost response")),
            mock.patch.object(
                control.handoff,
                "resolve_after_controller_failure",
                return_value=("finalized", {"pid": 8}),
            ),
        ):
            self.assertEqual(
                control.reload(ctx),
                {
                    "old_pid": 7,
                    "new_pid": 8,
                    "transaction_id": "tx",
                    "recovered_after_controller_failure": True,
                },
            )

        with (
            mock.patch.object(control, "_runtime_metrics", return_value=runtime),
            mock.patch.object(control.handoff, "runtime_supports_handoff", return_value=True),
            mock.patch.object(
                control.projection,
                "verify_payload_manifest",
                return_value=(False, "tampered"),
            ),
            self.assertRaisesRegex(errors.InstallError, "tampered"),
        ):
            control.reload(ctx)

        for resolution, expected_error in (
            ("unknown", errors.InstallError),
            ("rolled_back", OSError),
        ):
            with (
                self.subTest(resolution=resolution),
                mock.patch.object(control, "_runtime_metrics", return_value=runtime),
                mock.patch.object(control.handoff, "runtime_supports_handoff", return_value=True),
                mock.patch.object(
                    control.projection,
                    "verify_payload_manifest",
                    return_value=(True, "ok"),
                ),
                mock.patch.object(control.handoff, "expected_metadata", return_value=expected),
                mock.patch.object(control.handoff, "request", side_effect=OSError("lost response")),
                mock.patch.object(
                    control.handoff,
                    "resolve_after_controller_failure",
                    return_value=(resolution, None),
                ),
                self.assertRaises(expected_error),
            ):
                control.reload(ctx)

    def test_command_helpers_cover_local_files_tools_and_process_failures(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        version = Path(ctx.install_dir) / "VERSION"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("2.0.0\n", encoding="utf-8")
        self.assertEqual(control._installed_release(ctx), "2.0.0")
        version.unlink()
        self.assertIsNone(control._installed_release(ctx))

        with mock.patch.object(install.shutil, "which", return_value=None):
            with self.assertRaisesRegex(errors.InstallError, "git and ssh-keygen"):
                install.admit_released_payload(trust_anchor=Path("/portable/anchor"))
            with self.assertRaisesRegex(errors.InstallError, "git is required"):
                install.install_release(
                    ctx,
                    trust_anchor=Path("/portable/anchor"),
                    adapter=mock.Mock(),
                )

        with (
            mock.patch.object(
                uninstall.process,
                "verified_proxy_listener_pids",
                side_effect=[[7], []],
            ),
            mock.patch.object(uninstall.process, "terminate_pid", return_value=False),
            self.assertRaisesRegex(errors.InstallError, "did not exit"),
        ):
            uninstall._stop_proxy(ctx)
        with (
            mock.patch.object(
                uninstall.process,
                "verified_proxy_listener_pids",
                side_effect=[[], [8]],
            ),
            self.assertRaisesRegex(errors.InstallError, "listeners remain"),
        ):
            uninstall._stop_proxy(ctx)

    def test_install_and_uninstall_main_cover_success_and_fail_closed_boundaries(self):
        ctx = install_context(Path(tempfile.mkdtemp()))
        anchor = Path("/portable/anchor")
        with (
            mock.patch.object(sys, "argv", ["install", "--trust-anchor", str(anchor)]),
            mock.patch.object(install, "adapter", return_value=mock.Mock()),
            mock.patch.object(install, "build_context", return_value=ctx),
            mock.patch.object(install, "install_release", return_value={"mode": "fresh"}),
            mock.patch("builtins.print") as printed,
        ):
            install.main()
        self.assertIn(
            "Existing conversations remain unchanged.",
            [str(call.args[0]) for call in printed.call_args_list],
        )

        service = mock.Mock()
        service.status.return_value = "absent"
        with (
            mock.patch.object(sys, "argv", ["uninstall", "--purge"]),
            mock.patch.object(uninstall, "_context", return_value=ctx),
            mock.patch.object(uninstall, "adapter", return_value=service),
            mock.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[]),
            mock.patch.object(uninstall.projection, "purge_installed_projection", return_value=[]),
        ):
            uninstall.main()
        service.uninstall.assert_called_once_with(ctx)

        service.status.return_value = "loaded"
        with self.assertRaisesRegex(errors.InstallError, "remains loaded"):
            uninstall._remove_service(service, ctx)

        stderr = io.StringIO()
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "install",
                    "--trust-anchor",
                    str(anchor),
                    "--force-legacy-bootstrap",
                ],
            ),
            mock.patch.object(install, "adapter", return_value=mock.Mock()),
            mock.patch.object(install, "build_context", return_value=ctx),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit),
        ):
            install.main()
        self.assertEqual(
            stderr.getvalue().strip(),
            "ERROR: --force-legacy-bootstrap requires --allow-legacy-bootstrap",
        )

        service.status.return_value = "absent"
        with (
            mock.patch.object(sys, "argv", ["uninstall"]),
            mock.patch.object(uninstall, "_context", return_value=ctx),
            mock.patch.object(uninstall, "adapter", return_value=service),
            mock.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[]),
            mock.patch("builtins.print") as printed,
        ):
            uninstall.main()
        self.assertTrue(
            any("leaving install dir" in str(call.args[0]) for call in printed.call_args_list)
        )

        with (
            mock.patch.object(sys, "argv", ["uninstall", "--purge"]),
            mock.patch.object(uninstall, "_context", return_value=ctx),
            mock.patch.object(uninstall, "adapter", return_value=service),
            mock.patch.object(uninstall.process, "verified_proxy_listener_pids", return_value=[]),
            mock.patch.object(
                uninstall.projection,
                "purge_installed_projection",
                return_value=["unknown.txt"],
            ),
            self.assertRaisesRegex(SystemExit, "unknown install content remains"),
        ):
            uninstall.main()

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
            installed_control = Path(ctx.install_dir) / "codex_responses_proxy/commands/control.py"
            env = dict(
                os.environ,
                CODEX_RESPONSES_PROXY_HOME=ctx.install_dir,
                CODEX_RESPONSES_PROXY_STATE_HOME=ctx.log_dir,
            )

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
