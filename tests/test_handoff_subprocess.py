#!/usr/bin/env python3
"""Real loopback subprocess integration for rolling handoff."""

from __future__ import annotations

import sys
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.handoff import ScriptedUpstream
from tests.support.handoff import child_pid_observer
from tests.support.handoff import free_port
from tests.support.handoff import http_json
from tests.support.handoff import installed_expected_metadata
from tests.support.handoff import pid_alive
from tests.support.handoff import start_real_proxy
from tests.support.handoff import terminate_owned_proxy
from tests.support.handoff import terminate_process
from tests.support.handoff import wait_until
from tests.support.handoff import write_installed_payload
from codex_dmx_proxy import installation
from codex_dmx_proxy import process


class TestRealSubprocessHandoffIntegration(unittest.TestCase):
    """Exercise the complete rolling handoff against owned loopback processes."""

    def _new_temp_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def _track_owned_proxy_children(self, ctx: installation.InstallContext) -> None:
        proxy_script = ctx.proxy_script
        initial = set(process.pids_naming_path(proxy_script))

        def assert_no_orphans() -> None:
            remaining = set(process.pids_naming_path(proxy_script)) - initial
            self.assertFalse(remaining, f"orphaned proxy children for {proxy_script}: {remaining}")

        self.addCleanup(assert_no_orphans)

    def test_owned_child_cleanup_is_bound_to_its_temporary_proxy_path(self) -> None:
        proxy_script = "/tmp/owned/.codex/dmx-proxy/proxy.py"
        with (
            mock.patch.object(process, "process_command", return_value=f"python {proxy_script}"),
            mock.patch.object(process, "terminate_pid", return_value=True) as terminate,
        ):
            terminate_owned_proxy(123, proxy_script)

        terminate.assert_called_once_with(123, expected_path=proxy_script)

    def test_owned_child_cleanup_reports_an_unconfirmed_exit(self) -> None:
        proxy_script = "/tmp/owned/.codex/dmx-proxy/proxy.py"
        command = f"python {proxy_script} --handoff-child"
        with (
            mock.patch.object(process, "process_command", return_value=command),
            mock.patch.object(process, "terminate_pid", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "owned proxy child 123 did not terminate"):
                terminate_owned_proxy(123, proxy_script)

    def _post_responses(self, port, *, timeout=15):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=b'{"stream": false, "input": []}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            return response.read()

    def test_old_pid_serves_before_handoff_and_child_pid_serves_after(self):
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)
        upstream.push((200, b'{"id":"ok"}'))

        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        self._track_owned_proxy_children(ctx)
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))

        status_code, before = http_json(port, "/healthz")
        self.assertEqual(status_code, 200)
        self.assertEqual(before.get("pid"), old.pid)

        expected = installed_expected_metadata(ctx, "txn-real-1")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)
        self.assertEqual(ready.get("transaction_id"), expected["transaction_id"])
        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self.addCleanup(lambda: terminate_owned_proxy(child_pid["value"], ctx.proxy_script))
        self.assertTrue(
            wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit after finalize",
        )

    def test_finalized_child_can_drive_a_second_real_handoff(self):
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)
        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        self._track_owned_proxy_children(ctx)
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self.addCleanup(lambda: terminate_process(old))

        first = installed_expected_metadata(ctx, "txn-repeat-1")
        status_code, _ready = http_json(
            port, "/control/handoff", method="POST", body=first, timeout=15
        )
        self.assertEqual(status_code, 202)
        child_one, observe_first = child_pid_observer(port, first, exclude_pid=old.pid)

        self.assertTrue(wait_until(observe_first, timeout=10))
        self.addCleanup(lambda: terminate_owned_proxy(child_one["value"], ctx.proxy_script))
        self.assertTrue(wait_until(lambda: old.poll() is not None, timeout=10))

        second = installed_expected_metadata(ctx, "txn-repeat-2")
        second_request = {**second, "lease_seconds": 1, "timeout_seconds": 3}
        status_code, _ready = http_json(
            port,
            "/control/handoff",
            method="POST",
            body=second_request,
            timeout=15,
        )
        self.assertEqual(status_code, 202)
        child_two, observe_second = child_pid_observer(port, second, exclude_pid=child_one["value"])

        self.assertTrue(wait_until(observe_second, timeout=10))
        self.addCleanup(lambda: terminate_owned_proxy(child_two["value"], ctx.proxy_script))
        retired = wait_until(lambda: not pid_alive(child_one["value"]), timeout=10)
        child_one_pid = child_one["value"]
        detail = (
            process.process_command(child_one_pid)
            if not retired and isinstance(child_one_pid, int)
            else None
        )
        self.assertTrue(
            retired,
            f"first finalized child did not retire after the second handoff: {detail!r}",
        )

    def test_long_upstream_response_completes_during_handoff_while_child_serves_and_old_exits_after(
        self,
    ):
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)
        started = threading.Event()
        release = threading.Event()

        def long_response(handler):
            started.set()
            release.wait(timeout=10)
            payload = b'{"id":"finished-late"}'
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        upstream.push(long_response)

        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        self._track_owned_proxy_children(ctx)
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))

        held = {}

        def run_holder():
            held["body"] = self._post_responses(port)

        holder = threading.Thread(target=run_holder)
        holder.start()
        self.addCleanup(lambda: release.set())
        self.assertTrue(
            started.wait(timeout=10), "long upstream call did not start on the old process in time"
        )

        expected = installed_expected_metadata(ctx, "txn-real-2")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)

        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self.addCleanup(lambda: terminate_owned_proxy(child_pid["value"], ctx.proxy_script))

        # The queue is now empty (the held request already popped its own
        # behavior before blocking on ``release``), so pushing exactly one new
        # behavior now deterministically belongs to the next request only.
        upstream.push((200, b'{"id":"new-via-child"}'))
        new_body = json.loads(self._post_responses(port, timeout=10))
        self.assertEqual(new_body.get("id"), "new-via-child")

        release.set()
        holder.join(timeout=15)
        self.assertEqual(held.get("body"), b'{"id":"finished-late"}')
        self.assertTrue(
            wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit after the held response completed",
        )

    def test_bounded_lease_forces_old_to_exit_even_if_a_held_stream_never_finishes(self):
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)
        started = threading.Event()
        never_release = threading.Event()

        def never_finishes(handler):
            started.set()
            never_release.wait(timeout=6)  # bounded so the test itself cannot hang
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"{}")

        upstream.push(never_finishes)

        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        self._track_owned_proxy_children(ctx)
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))

        def hold_stream():
            try:
                self._post_responses(port, timeout=8)
            except Exception:
                pass

        holder = threading.Thread(target=hold_stream, daemon=True)
        holder.start()
        self.addCleanup(never_release.set)
        self.assertTrue(
            started.wait(timeout=10), "held stream did not start on the old process in time"
        )

        expected = installed_expected_metadata(ctx, "txn-real-3")
        expected["lease_seconds"] = 1
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)

        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self.addCleanup(lambda: terminate_owned_proxy(child_pid["value"], ctx.proxy_script))

        # Deterministic: the held request's behavior was already popped before
        # it blocked, so this new push belongs solely to the queued request below.
        upstream.push((200, b'{"id":"via-child-while-old-held"}'))
        queued_body = json.loads(self._post_responses(port, timeout=10))
        self.assertEqual(queued_body.get("id"), "via-child-while-old-held")

        self.assertTrue(
            wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit despite the lease expiring on a held stream",
        )
        status_code, still_healthy = http_json(port, "/healthz", timeout=3)
        self.assertEqual(status_code, 200)
        self.assertEqual(still_healthy.get("pid"), child_pid["value"])
        self.assertIs(still_healthy.get("accepting"), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
