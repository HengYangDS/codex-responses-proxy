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


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.handoff import ScriptedUpstream
from tests.support.handoff import free_port
from tests.support.handoff import handoff_module
from tests.support.handoff import http_json
from tests.support.handoff import installed_expected_metadata
from tests.support.handoff import pid_alive
from tests.support.handoff import start_real_proxy
from tests.support.handoff import terminate_pid_best_effort
from tests.support.handoff import terminate_process
from tests.support.handoff import wait_until
from tests.support.handoff import write_installed_payload
from tests.support.handoff import common


class TestRealSubprocessHandoffIntegration(unittest.TestCase):
    """Owns and reliably terminates every subprocess/server it starts.

    Cleanups are appended in the order: temp-payload-directory removal FIRST,
    then everything else. ``tearDown`` runs them in reverse (LIFO), so the
    directory is always the *last* thing removed -- every owned child/old
    process must already be confirmed exited (and, on Windows, its open log
    file handle released) before the temporary payload it depended on is torn
    down.
    """

    def setUp(self):
        self._handoff_cleanups = []

    def tearDown(self):
        for cleanup in reversed(self._handoff_cleanups):
            try:
                cleanup()
            except Exception:
                pass

    def _addCleanupNow(self, fn):
        self._handoff_cleanups.append(fn)

    def _new_temp_root(self) -> Path:
        tmp_ctx = tempfile.TemporaryDirectory()
        # Registered first on purpose: reversed teardown order runs this last,
        # i.e. only after every process cleanup registered below has run.
        self._addCleanupNow(tmp_ctx.cleanup)
        return Path(tmp_ctx.name)

    def _child_takes_over_with_matching_health(self, port, expected, *, exclude_pid):
        try:
            _, health = http_json(port, "/healthz", timeout=1)
        except (OSError, urllib.error.URLError, ValueError):
            return None
        if (
            isinstance(health.get("pid"), int)
            and health.get("pid") != exclude_pid
            and health.get("handoff_protocol_version") == handoff_module.HANDOFF_PROTOCOL_VERSION
            and health.get("handoff_transaction_id") == expected["transaction_id"]
            and health.get("release") == expected["release"]
            and health.get("serving_payload_sha256") == expected["serving_payload_sha256"]
            and health.get("release_receipt_sha256") == expected["release_receipt_sha256"]
            and health.get("payload_manifest_sha256") == expected["manifest_sha256"]
            and health.get("accepting") is True
        ):
            return health["pid"]
        return None

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
        self._addCleanupNow(upstream.close)
        upstream.push((200, b'{"id":"ok"}'))

        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: terminate_process(old))

        status_code, before = http_json(port, "/healthz")
        self.assertEqual(status_code, 200)
        self.assertEqual(before.get("pid"), old.pid)

        expected = installed_expected_metadata(ctx, "txn-real-1")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)
        self.assertEqual(ready.get("transaction_id"), expected["transaction_id"])
        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self._addCleanupNow(lambda: terminate_pid_best_effort(child_pid["value"]))
        self.assertTrue(
            wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit after finalize",
        )

    def test_finalized_child_can_drive_a_second_real_handoff(self):
        upstream = ScriptedUpstream()
        self._addCleanupNow(upstream.close)
        root = self._new_temp_root()
        port = free_port()
        ctx = write_installed_payload(root, release="1.0.25", port=port)
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self._addCleanupNow(lambda: terminate_process(old))

        first = installed_expected_metadata(ctx, "txn-repeat-1")
        status_code, _ready = http_json(
            port, "/control/handoff", method="POST", body=first, timeout=15
        )
        self.assertEqual(status_code, 202)
        child_one = {"value": None}

        def observe_first():
            child_one["value"] = self._child_takes_over_with_matching_health(
                port,
                first,
                exclude_pid=old.pid,
            )
            return child_one["value"] is not None

        self.assertTrue(wait_until(observe_first, timeout=10))
        self._addCleanupNow(lambda: terminate_pid_best_effort(child_one["value"]))
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
        child_two = {"value": None}

        def observe_second():
            child_two["value"] = self._child_takes_over_with_matching_health(
                port,
                second,
                exclude_pid=child_one["value"],
            )
            return child_two["value"] is not None

        self.assertTrue(wait_until(observe_second, timeout=10))
        self._addCleanupNow(lambda: terminate_pid_best_effort(child_two["value"]))
        retired = wait_until(lambda: not pid_alive(child_one["value"]), timeout=10)
        child_one_pid = child_one["value"]
        detail = (
            common.process_command(child_one_pid)
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
        self._addCleanupNow(upstream.close)
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
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: terminate_process(old))

        held = {}

        def run_holder():
            held["body"] = self._post_responses(port)

        holder = threading.Thread(target=run_holder)
        holder.start()
        self._addCleanupNow(lambda: release.set())
        self.assertTrue(
            started.wait(timeout=10), "long upstream call did not start on the old process in time"
        )

        expected = installed_expected_metadata(ctx, "txn-real-2")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)

        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self._addCleanupNow(lambda: terminate_pid_best_effort(child_pid["value"]))

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
        self._addCleanupNow(upstream.close)
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
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._addCleanupNow(lambda: terminate_process(old))

        def hold_stream():
            try:
                self._post_responses(port, timeout=8)
            except Exception:
                pass

        holder = threading.Thread(target=hold_stream, daemon=True)
        holder.start()
        self._addCleanupNow(never_release.set)
        self.assertTrue(
            started.wait(timeout=10), "held stream did not start on the old process in time"
        )

        expected = installed_expected_metadata(ctx, "txn-real-3")
        expected["lease_seconds"] = 1
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=15
        )
        self.assertEqual(status_code, 202)

        child_pid = {"value": None}

        def observe():
            found = self._child_takes_over_with_matching_health(port, expected, exclude_pid=old.pid)
            if found is not None:
                child_pid["value"] = found
                return True
            return False

        self.assertTrue(
            wait_until(observe, timeout=10), "child did not take over serving with matching health"
        )
        self._addCleanupNow(lambda: terminate_pid_best_effort(child_pid["value"]))

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
