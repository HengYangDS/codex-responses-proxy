"""Real loopback subprocess integration for rolling handoff."""

from __future__ import annotations

from contextlib import ExitStack

import json
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle.supervision import process
from tests.service.handoff import fixtures as handoff_fixtures
from tests.service.handoff.fixtures import (
    ScriptedUpstream,
    child_pid_observer,
    free_port,
    http_json,
    installed_expected_metadata,
    pid_alive,
    start_real_proxy,
    terminate_owned_proxy,
    terminate_process,
    wait_until,
    write_installed_payload,
)
import pytest

ROOT = Path(__file__).resolve().parents[3]

SUCCESSOR_TIMEOUT = 20

pytestmark = pytest.mark.native_distribution


class TestRealSubprocessHandoffIntegration:
    """Exercise the complete rolling handoff against owned loopback processes."""

    def setup_method(self) -> None:
        self._cleanups = ExitStack()

    def teardown_method(self) -> None:
        self._cleanups.close()

    def test_scripted_upstream_starts_only_after_the_proxy_child_is_spawned(self) -> None:
        upstream = ScriptedUpstream()
        self._cleanups.callback(upstream.close)

        assert not upstream.thread.is_alive()
        upstream.start()
        assert upstream.thread.is_alive()

    def test_initial_proxy_spawn_avoids_multithreaded_posix_fork(self, *, mocker) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ctx = write_installed_payload(
                root,
                release="1.0.25",
                port=free_port(),
                upstream_url="http://127.0.0.1:43123",
            )
            child = mocker.Mock()
            child.poll.return_value = None
            popen = mocker.patch.object(handoff_fixtures.subprocess, "Popen", return_value=child)
            mocker.patch.object(handoff_fixtures, "proxy_is_up", return_value=True)
            started = start_real_proxy(
                ctx,
                upstream_url="http://127.0.0.1:43123",
                log_path=root / "proxy.log",
            )

        assert started is child
        assert popen.call_args.kwargs.get("close_fds", True) is True
        assert popen.call_args.kwargs["env"]["CODEX_RESPONSES_PROXY_HOME"] == ctx.install_dir
        assert popen.call_args.kwargs["env"]["CODEX_RESPONSES_PROXY_STATE_HOME"] == str(
            root / "state"
        )

    def _installed_fixture(
        self, *, release: str, port: int, upstream_url: str
    ) -> tuple[Path, runtime_context.RuntimeContext]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        ctx = write_installed_payload(root, release=release, port=port, upstream_url=upstream_url)
        initial = set(process.pids_naming_executable(ctx.executable))
        self._cleanups.callback(self._cleanup_installed_fixture, temporary, ctx.executable, initial)
        return root, ctx

    def _cleanup_installed_fixture(
        self, temporary: tempfile.TemporaryDirectory, proxy_script: str, initial: set[int]
    ) -> None:
        try:
            for pid in set(process.pids_naming_executable(proxy_script)) - initial:
                terminate_owned_proxy(pid, proxy_script)
            remaining = set(process.pids_naming_executable(proxy_script)) - initial
            assert not remaining, f"orphaned proxy children for {proxy_script}: {remaining}"
        finally:
            temporary.cleanup()

    def test_fixture_cleanup_terminates_before_removing_temporary_payload(self, *, mocker) -> None:
        events = []
        temporary = tempfile.TemporaryDirectory()
        cleanup = temporary.cleanup

        def inventory(_proxy_script):
            events.append("inventory")
            return [123] if events.count("inventory") == 1 else []

        try:
            mocker.patch.object(process, "pids_naming_executable", side_effect=inventory)
            mocker.patch.object(
                process,
                "pid_names_executable",
                side_effect=lambda *_args, **_kwargs: events.append("identity") or True,
            )
            mocker.patch.object(
                process,
                "terminate_executable",
                side_effect=lambda *_args, **_kwargs: events.append("terminate") or True,
            )
            mocker.patch.object(temporary, "cleanup", side_effect=lambda: events.append("cleanup"))
            self._cleanup_installed_fixture(temporary, "/tmp/owned/proxy.py", set())
        finally:
            cleanup()

        assert events == ["inventory", "identity", "terminate", "inventory", "cleanup"]

    def test_owned_child_cleanup_is_bound_to_its_temporary_proxy_path(self, *, mocker) -> None:
        proxy_script = "/tmp/owned/.codex/responses-proxy/proxy.py"
        owns_pid = mocker.patch.object(process, "pid_names_executable", return_value=True)
        terminate = mocker.patch.object(process, "terminate_executable", return_value=True)
        terminate_owned_proxy(123, proxy_script)

        owns_pid.assert_called_once()
        terminate.assert_called_once()

    def test_owned_child_cleanup_reports_an_unconfirmed_exit(self, *, mocker) -> None:
        proxy_script = "/tmp/owned/.codex/responses-proxy/proxy.py"
        command = f"python {proxy_script} --handoff-child"
        mocker.patch.object(process, "pid_names_executable", return_value=True)
        mocker.patch.object(process, "process_command", return_value=command)
        mocker.patch.object(process, "terminate_executable", return_value=False)
        with pytest.raises(RuntimeError, match="owned proxy child 123 did not terminate"):
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
        self._cleanups.callback(upstream.close)
        upstream.push((200, b'{"id":"ok","status":"completed"}'))

        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._cleanups.callback(lambda: terminate_process(old))
        upstream.start()

        status_code, before = http_json(port, "/healthz")
        assert status_code == 200
        old_runtime_pid = before.get("pid")
        assert type(old_runtime_pid) is int
        assert process.verified_proxy_listener_pids(ctx) == [old_runtime_pid]

        expected = installed_expected_metadata(ctx, "txn-real-1")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=35
        )
        assert status_code == 202
        assert ready.get("transaction_id") == expected["transaction_id"]
        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old_runtime_pid)

        assert wait_until(observe, timeout=SUCCESSOR_TIMEOUT), (
            "child did not take over serving with matching health"
        )
        assert wait_until(lambda: old.poll() is not None, timeout=10), (
            "old process did not exit after finalize"
        )

    def test_finalized_child_can_drive_a_second_real_handoff(self):
        upstream = ScriptedUpstream()
        self._cleanups.callback(upstream.close)
        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self._cleanups.callback(lambda: terminate_process(old))
        upstream.start()

        first = installed_expected_metadata(ctx, "txn-repeat-1")
        status_code, _ready = http_json(
            port, "/control/handoff", method="POST", body=first, timeout=35
        )
        assert status_code == 202
        child_one, observe_first = child_pid_observer(port, first, exclude_pid=old.pid)

        assert wait_until(observe_first, timeout=SUCCESSOR_TIMEOUT)
        assert wait_until(lambda: old.poll() is not None, timeout=10)

        second = installed_expected_metadata(ctx, "txn-repeat-2")
        second_request = {**second, "lease_seconds": 1, "timeout_seconds": 30}
        status_code, _ready = http_json(
            port,
            "/control/handoff",
            method="POST",
            body=second_request,
            timeout=35,
        )
        assert status_code == 202
        child_two, observe_second = child_pid_observer(port, second, exclude_pid=child_one["value"])

        assert wait_until(observe_second, timeout=SUCCESSOR_TIMEOUT)
        retired = wait_until(lambda: not pid_alive(child_one["value"]), timeout=10)
        child_one_pid = child_one["value"]
        detail = (
            process.process_command(child_one_pid)
            if not retired and isinstance(child_one_pid, int)
            else None
        )
        assert retired, f"first finalized child did not retire after the second handoff: {detail!r}"

    def test_long_upstream_response_completes_during_handoff_while_child_serves_and_old_exits_after(
        self,
    ):
        upstream = ScriptedUpstream()
        self._cleanups.callback(upstream.close)
        started = threading.Event()
        release = threading.Event()

        def long_response(handler):
            started.set()
            release.wait(timeout=10)
            payload = b'{"id":"finished-late","status":"completed"}'
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
        self._cleanups.callback(lambda: terminate_process(old))
        upstream.start()

        held = {}

        def run_holder():
            held["body"] = self._post_responses(port)

        holder = threading.Thread(target=run_holder)
        holder.start()
        self._cleanups.callback(lambda: release.set())
        assert started.wait(timeout=10), (
            "long upstream call did not start on the old process in time"
        )

        expected = installed_expected_metadata(ctx, "txn-real-2")
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=35
        )
        assert status_code == 202

        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)

        assert wait_until(observe, timeout=SUCCESSOR_TIMEOUT), (
            "child did not take over serving with matching health"
        )

        # The queue is now empty (the held request already popped its own
        # behavior before blocking on ``release``), so pushing exactly one new
        # behavior now deterministically belongs to the next request only.
        upstream.push((200, b'{"id":"new-via-child","status":"completed"}'))
        new_body = json.loads(self._post_responses(port, timeout=10))
        assert new_body.get("id") == "new-via-child"

        release.set()
        holder.join(timeout=15)
        assert held.get("body") == b'{"id":"finished-late","status":"completed"}'
        assert wait_until(lambda: old.poll() is not None, timeout=10), (
            "old process did not exit after the held response completed"
        )

    def test_bounded_lease_forces_old_to_exit_even_if_a_held_stream_never_finishes(self):
        upstream = ScriptedUpstream()
        self._cleanups.callback(upstream.close)
        started = threading.Event()
        never_release = threading.Event()

        def never_finishes(handler):
            started.set()
            never_release.wait(timeout=6)  # bounded so the test itself cannot hang
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            payload = b'{"status":"completed"}'
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        upstream.push(never_finishes)

        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        log_path = root / "proxy.log"
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=log_path)
        self._cleanups.callback(lambda: terminate_process(old))
        upstream.start()

        def hold_stream():
            try:
                self._post_responses(port, timeout=8)
            except Exception:
                pass

        holder = threading.Thread(target=hold_stream, daemon=True)
        holder.start()
        self._cleanups.callback(never_release.set)
        assert started.wait(timeout=10), "held stream did not start on the old process in time"

        expected = installed_expected_metadata(ctx, "txn-real-3")
        expected["lease_seconds"] = 1
        status_code, ready = http_json(
            port, "/control/handoff", method="POST", body=expected, timeout=35
        )
        assert status_code == 202

        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)

        assert wait_until(observe, timeout=SUCCESSOR_TIMEOUT), (
            "child did not take over serving with matching health"
        )

        # Deterministic: the held request's behavior was already popped before
        # it blocked, so this new push belongs solely to the queued request below.
        upstream.push((200, b'{"id":"via-child-while-old-held","status":"completed"}'))
        queued_body = json.loads(self._post_responses(port, timeout=10))
        assert queued_body.get("id") == "via-child-while-old-held"

        assert wait_until(lambda: old.poll() is not None, timeout=10), (
            "old process did not exit despite the lease expiring on a held stream"
        )
        status_code, still_healthy = http_json(port, "/healthz", timeout=3)
        assert status_code == 200
        assert still_healthy.get("pid") == child_pid["value"]
        assert still_healthy.get("accepting") is True

    def test_handoff_completes_after_requesting_controller_disconnects(self):
        upstream = ScriptedUpstream()
        self._cleanups.callback(upstream.close)
        port = free_port()
        root, ctx = self._installed_fixture(
            release="1.0.25", port=port, upstream_url=upstream.base_url()
        )
        old = start_real_proxy(ctx, upstream_url=upstream.base_url(), log_path=root / "proxy.log")
        self._cleanups.callback(lambda: terminate_process(old))
        upstream.start()

        expected = installed_expected_metadata(ctx, "txn-controller-disconnect")
        raw = json.dumps(expected).encode()
        request = (
            f"POST /control/handoff HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode() + raw
        with socket.create_connection(("127.0.0.1", port), timeout=3) as controller:
            controller.sendall(request)
            controller.shutdown(socket.SHUT_RDWR)

        child_pid, observe = child_pid_observer(port, expected, exclude_pid=old.pid)
        assert wait_until(observe, timeout=SUCCESSOR_TIMEOUT), (
            "listener-owned transaction did not survive controller disconnect"
        )
        assert wait_until(lambda: old.poll() is not None, timeout=10)
        status_code, health = http_json(port, "/healthz", timeout=3)
        assert status_code == 200
        assert health.get("pid") == child_pid["value"]
        assert health.get("accepting") is True
