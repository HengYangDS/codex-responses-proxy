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

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.runtime.handoff.fixtures import ScriptedUpstream
from tests.runtime.handoff.fixtures import child_pid_observer
from tests.runtime.handoff.fixtures import free_port
from tests.runtime.handoff.fixtures import http_json
from tests.runtime.handoff.fixtures import installed_expected_metadata
from tests.runtime.handoff.fixtures import pid_alive
from tests.runtime.handoff.fixtures import start_real_proxy
from tests.runtime.handoff.fixtures import terminate_owned_proxy
from tests.runtime.handoff.fixtures import terminate_process
from tests.runtime.handoff.fixtures import wait_until
from tests.runtime.handoff.fixtures import write_installed_payload
from tests.runtime.handoff import fixtures as handoff_fixtures
from codex_responses_proxy.runtime import context as runtime_context
from codex_responses_proxy.supervision import process

SUCCESSOR_TIMEOUT = 20


class TestRealSubprocessHandoffIntegration(unittest.TestCase):
    """Exercise the complete rolling handoff against owned loopback processes."""

    def test_scripted_upstream_starts_only_after_the_proxy_child_is_spawned(self) -> None:
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)

        self.assertFalse(upstream.thread.is_alive())
        upstream.start()
        self.assertTrue(upstream.thread.is_alive())

    def test_initial_proxy_spawn_avoids_multithreaded_posix_fork(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ctx = write_installed_payload(
                root,
                release="1.0.25",
                port=free_port(),
                upstream_url="http://127.0.0.1:43123",
            )
            child = mock.Mock()
            child.poll.return_value = None
            with (
                mock.patch.object(
                    handoff_fixtures.subprocess, "Popen", return_value=child
                ) as popen,
                mock.patch.object(handoff_fixtures, "proxy_is_up", return_value=True),
            ):
                started = start_real_proxy(
                    ctx,
                    upstream_url="http://127.0.0.1:43123",
                    log_path=root / "proxy.log",
                )

        self.assertIs(started, child)
        self.assertIs(
            popen.call_args.kwargs.get("close_fds", True),
            True,
        )
        self.assertEqual(
            popen.call_args.kwargs["env"]["CODEX_RESPONSES_PROXY_HOME"],
            ctx.install_dir,
        )
        self.assertEqual(
            popen.call_args.kwargs["env"]["CODEX_RESPONSES_PROXY_STATE_HOME"],
            str(root / "state"),
        )

    def _installed_fixture(
        self, *, release: str, port: int, upstream_url: str
    ) -> tuple[Path, runtime_context.RuntimeContext]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        ctx = write_installed_payload(root, release=release, port=port, upstream_url=upstream_url)
        initial = set(process.pids_naming_path(ctx.proxy_script))
        self.addCleanup(self._cleanup_installed_fixture, temporary, ctx.proxy_script, initial)
        return root, ctx

    def _cleanup_installed_fixture(
        self, temporary: tempfile.TemporaryDirectory, proxy_script: str, initial: set[int]
    ) -> None:
        try:
            for pid in set(process.pids_naming_path(proxy_script)) - initial:
                terminate_owned_proxy(pid, proxy_script)
            remaining = set(process.pids_naming_path(proxy_script)) - initial
            self.assertFalse(remaining, f"orphaned proxy children for {proxy_script}: {remaining}")
        finally:
            temporary.cleanup()

    def test_fixture_cleanup_terminates_before_removing_temporary_payload(self) -> None:
        events = []
        temporary = tempfile.TemporaryDirectory()
        cleanup = temporary.cleanup

        def inventory(_proxy_script):
            events.append("inventory")
            return [123] if events.count("inventory") == 1 else []

        try:
            with (
                mock.patch.object(process, "pids_naming_path", side_effect=inventory),
                mock.patch.object(
                    process,
                    "pid_names_path",
                    side_effect=lambda *_args: events.append("identity") or True,
                ),
                mock.patch.object(
                    process,
                    "terminate_pid",
                    side_effect=lambda *_args, **_kwargs: events.append("terminate") or True,
                ),
                mock.patch.object(
                    temporary, "cleanup", side_effect=lambda: events.append("cleanup")
                ),
            ):
                self._cleanup_installed_fixture(temporary, "/tmp/owned/proxy.py", set())
        finally:
            cleanup()

        self.assertEqual(events, ["inventory", "identity", "terminate", "inventory", "cleanup"])

    def test_owned_child_cleanup_is_bound_to_its_temporary_proxy_path(self) -> None:
        proxy_script = "/tmp/owned/.codex/responses-proxy/proxy.py"
        with (
            mock.patch.object(process, "pid_names_path", return_value=True) as owns_pid,
            mock.patch.object(process, "terminate_pid", return_value=True) as terminate,
        ):
            terminate_owned_proxy(123, proxy_script)

        owns_pid.assert_called_once_with(123, proxy_script)
        terminate.assert_called_once_with(123, expected_path=proxy_script)

    def test_owned_child_cleanup_reports_an_unconfirmed_exit(self) -> None:
        proxy_script = "/tmp/owned/.codex/responses-proxy/proxy.py"
        command = f"python {proxy_script} --handoff-child"
        with (
            mock.patch.object(process, "pid_names_path", return_value=True),
            mock.patch.object(process, "process_command", return_value=command),
            mock.patch.object(process, "terminate_pid", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "owned proxy child 123 did not terminate"):
                terminate_owned_proxy(123, proxy_script)

    def _post_responses(self, port, *, timeout=15):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/dmxapi/v1/responses",
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

        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))
        upstream.start()

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
            wait_until(observe, timeout=SUCCESSOR_TIMEOUT),
            "child did not take over serving with matching health",
        )
        self.assertTrue(
            wait_until(lambda: old.poll() is not None, timeout=10),
            "old process did not exit after finalize",
        )

    def test_finalized_child_can_drive_a_second_real_handoff(self):
        upstream = ScriptedUpstream()
        self.addCleanup(upstream.close)
        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self.addCleanup(lambda: terminate_process(old))
        upstream.start()

        first = installed_expected_metadata(ctx, "txn-repeat-1")
        status_code, _ready = http_json(
            port, "/control/handoff", method="POST", body=first, timeout=15
        )
        self.assertEqual(status_code, 202)
        child_one, observe_first = child_pid_observer(port, first, exclude_pid=old.pid)

        self.assertTrue(wait_until(observe_first, timeout=SUCCESSOR_TIMEOUT))
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

        self.assertTrue(wait_until(observe_second, timeout=SUCCESSOR_TIMEOUT))
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

        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))
        upstream.start()

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
            wait_until(observe, timeout=SUCCESSOR_TIMEOUT),
            "child did not take over serving with matching health",
        )

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

        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self.addCleanup(lambda: terminate_process(old))
        upstream.start()

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
            wait_until(observe, timeout=SUCCESSOR_TIMEOUT),
            "child did not take over serving with matching health",
        )

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
