#!/usr/bin/env python3
"""HTTP dispatch, cooldown, retry, SSE, and disconnect contracts for empty responses."""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import cast
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import entrypoint as proxy
from codex_dmx_proxy.compatibility import empty_response as policy
from codex_dmx_proxy.listener import rewrite
from codex_dmx_proxy.listener import state
from tests.support.empty_response import EMPTY_RESPONSE
from tests.support.empty_response import SUCCESS
from tests.support.empty_response import UNKNOWN_477
from tests.support.empty_response import body
from tests.support.empty_response import semantic_body
from tests.support.proxy_http import request
from tests.support.proxy_http import serve_proxy


class EmptyResponseTransportTests(unittest.TestCase):
    """Exercise one-shot recovery through real loopback HTTP boundaries."""

    def setUp(self) -> None:
        state.reset_for_test()

    _body = staticmethod(body)
    _request = staticmethod(request)

    @staticmethod
    def _remember_failure(key, *, now=None):
        state.remember_empty_response_failure(
            key,
            capacity=policy.COOLDOWN_CAPACITY,
            cooldown_seconds=policy.COOLDOWN_SECONDS,
            now=now,
        )

    @staticmethod
    def _cooldown_remaining(key, *, now=None):
        return state.empty_response_cooldown_remaining(
            key,
            cooldown_seconds=policy.COOLDOWN_SECONDS,
            now=now,
        )

    def _read_http_error(self, port, request_body):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._request(port, request_body)
        error = raised.exception
        with error:
            payload = error.read()
            headers = error.headers
            code = error.code
        return code, headers, payload

    def test_classified_477_dispatches_policy_fallback_once(self):
        body = semantic_body()
        sanitized, _ = rewrite.sanitize_responses_body(body)
        fallback, _ = policy.build_fallback(cast("bytes", sanitized))

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(received, [sanitized, fallback])

    def test_unsafe_projection_returns_local_400_without_an_upstream_call(self):
        body = self._body({"stream": False, "input": [{"type": "future_item"}]})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
            try:
                code, headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 400)
        self.assertIsNone(headers.get("Retry-After"))
        self.assertEqual(json.loads(raw)["error"]["code"], "provider_portable_projection_rejected")
        self.assertEqual(received, [])

    def test_search_history_is_removed_before_dmx_fallback(self):
        payload = {
            "previous_response_id": "stale",
            "prompt_cache_key": "stale-cache",
            "input": [
                {"type": "message", "role": "system", "content": "policy"},
                {"type": "web_search_call", "action": {"type": "search"}},
                {"type": "message", "role": "developer", "content": "rules"},
                {"type": "tool_search_call", "call_id": "s", "execution": "server"},
                {"type": "tool_search_output", "call_id": "s", "execution": "server"},
                {"type": "message", "role": "assistant", "content": "old answer"},
                {"type": "message", "role": "user", "content": "current"},
            ],
        }
        body = self._body(payload)
        sanitized, _ = rewrite.sanitize_responses_body(body)
        expected, _ = policy.build_fallback(cast("bytes", sanitized))
        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()
        self.assertEqual(received, [sanitized, expected])
        forwarded = json.loads(received[0])
        self.assertNotIn("previous_response_id", forwarded)
        self.assertNotIn("prompt_cache_key", forwarded)
        self.assertFalse(
            {"web_search_call", "tool_search_call", "tool_search_output"}
            & {item["type"] for item in forwarded["input"]}
        )

    def test_rejected_projection_returns_400_without_an_upstream_fallback(self):
        cases = (
            (
                [
                    {"type": "future_item", "opaque": "x"},
                    {"type": "message", "role": "user", "content": "current"},
                ],
                "unknown_item_type",
            ),
            (
                [
                    {"type": "web_search_call", "action": {"type": "search"}},
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": "x"}],
                    },
                ],
                "empty_portable_content",
            ),
        )
        for items, expected_reason in cases:
            with self.subTest(items=items), tempfile.TemporaryDirectory() as tmp:
                state.reset_for_test()
                port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
                try:
                    code, _, raw = self._read_http_error(port, self._body({"input": items}))
                finally:
                    cleanup()
                self.assertEqual(code, 400)
                error = json.loads(raw)["error"]
                self.assertEqual(error["code"], "provider_portable_projection_rejected")
                self.assertEqual(error["reason"], expected_reason)
                self.assertEqual(received, [])

    def test_fallback_failure_is_terminal_after_exactly_two_upstream_attempts(self):
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "remove-on-fallback",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        cases = (
            (400, b'{"error":{"code":"bad_request"}}'),
            (477, EMPTY_RESPONSE),
            (500, b'{"error":{"code":"upstream_failure"}}'),
        )
        for second_status, second_payload in cases:
            with self.subTest(second_status=second_status):
                state.reset_for_test()
                responses = [(477, EMPTY_RESPONSE), (second_status, second_payload)]
                responses += [(second_status, second_payload)] * (3 * (second_status in (477, 500)))
                with tempfile.TemporaryDirectory() as tmp:
                    port, received, cleanup = serve_proxy(responses, tmp)
                    try:
                        code, _headers, raw = self._read_http_error(port, body)
                    finally:
                        cleanup()
                self.assertEqual(code, 503)
                self.assertEqual(len(received), 2)
                self.assertEqual(json.loads(raw)["error"]["attempts"], 2)

    def test_unknown_477_is_passed_through_without_fallback_or_cooldown(self):
        body = self._body({"stream": False, "input": []})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, UNKNOWN_477)], tmp)
            try:
                code, _headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 477)
        self.assertEqual(raw, UNKNOWN_477)
        self.assertEqual(received, [body])
        key = policy.policy_fingerprint(body)
        self.assertEqual(self._cooldown_remaining(key, now=100.0), 0)

    def test_streaming_request_recovers_only_before_any_sse_bytes(self):
        body = self._body(
            {
                "stream": True,
                "previous_response_id": "remove-on-fallback",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE), recovered], tmp)
            try:
                with self._request(port, body) as response:
                    payload = response.read()
            finally:
                cleanup()

        self.assertEqual(response.status, 200)
        self.assertIn(b'"delta":"ok"', payload)
        self.assertEqual(len(received), 2)
        self.assertNotEqual(received[1], body)

    def test_streaming_fallback_exhaustion_is_standard_http_503(self):
        body = self._body({"stream": True, "input": []})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
            try:
                code, headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 503)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Retry-After"], "3")
        self.assertEqual(json.loads(raw)["error"]["attempts"], 2)
        self.assertEqual(len(received), 2)

    def test_failed_recovery_cools_identical_request_without_upstream_replay(self):
        body = self._body({"stream": False, "input": []})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE)] * 8, tmp)
            try:
                first = self._read_http_error(port, body)
                second = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(first[0], 503)
        self.assertEqual(second[0], 503)
        self.assertEqual(json.loads(second[2])["error"]["attempts"], 0)
        self.assertEqual(len(received), 2)
        status = proxy.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_cooldown_hits"], 1
        )

    def test_cooldown_ttl_capacity_and_concurrent_access_are_bounded(self):
        first = self._body(
            {
                "previous_response_id": "first",
                "input": [{"type": "message", "role": "user", "content": "same"}],
            }
        )
        second = self._body(
            {
                "previous_response_id": "second",
                "input": [{"type": "message", "role": "user", "content": "same"}],
            }
        )
        first_key = policy.policy_fingerprint(first)
        second_key = policy.policy_fingerprint(second)
        self._remember_failure(first_key, now=10.0)
        self.assertGreater(self._cooldown_remaining(first_key, now=10.1), 0)
        self.assertEqual(self._cooldown_remaining(second_key, now=10.1), 0)

        self._remember_failure("expires", now=100.0)
        self.assertGreater(self._cooldown_remaining("expires", now=100.1), 0)
        self.assertTrue(state.has_empty_response_failure_for_test("expires"))
        past_ttl = 100.0 + policy.COOLDOWN_SECONDS + 0.1
        self.assertEqual(self._cooldown_remaining("expires", now=past_ttl), 0)
        # The TTL purge is a real eviction, not merely a read-time comparison:
        # the reading call above must have removed the expired entry itself.
        self.assertFalse(state.has_empty_response_failure_for_test("expires"))

        # A stale entry is also purged by the next *write* to an unrelated key.
        self._remember_failure("stale", now=300.0)
        self._remember_failure("other", now=300.0 + policy.COOLDOWN_SECONDS + 0.1)
        self.assertFalse(state.has_empty_response_failure_for_test("stale"))
        self.assertTrue(state.has_empty_response_failure_for_test("other"))

        def remember(index):
            key = f"key-{index}"
            self._remember_failure(key, now=200.0 + index / 10_000)
            return self._cooldown_remaining(key, now=200.0)

        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(remember, range(policy.COOLDOWN_CAPACITY + 100)))
        self.assertLessEqual(
            state.empty_response_failure_count_for_test(),
            policy.COOLDOWN_CAPACITY,
        )
        self.assertFalse(state.has_empty_response_failure_for_test("key-0"))

    def test_successful_fallback_does_not_enter_cooldown_and_metrics_are_secret_free(self):
        secret = "private-prompt-must-not-appear"
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "remove-on-fallback",
                "input": [{"type": "message", "role": "user", "content": secret}],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            port, _received, cleanup = serve_proxy([(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        key = policy.policy_fingerprint(body)
        self.assertEqual(self._cooldown_remaining(key), 0)
        status = proxy.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )
        self.assertNotIn(secret, json.dumps(status))
        self.assertNotIn(key, json.dumps(status))

    def test_dedicated_slot_survives_ordinary_transient_retry_budget(self):
        body = self._body(
            {
                "stream": False,
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        transient = b'{"error":{"code":"upstream_failure"}}'
        responses = [
            (500, transient),
            (500, transient),
            (500, transient),
            (477, EMPTY_RESPONSE),
            (200, SUCCESS),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy(responses, tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 5)
        status = proxy.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )

    def test_fallback_follows_response_failed_recovery_without_metric_overlap(self):
        error = b'{"error":{"code":"response_failed"}}'
        body = self._body(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "x" * 100_000},
                    {"type": "message", "role": "user", "content": "latest"},
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy(
                [(400, error), (477, EMPTY_RESPONSE), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        counters = cast("dict[str, int]", proxy.runtime_status()["counters"])
        self.assertEqual(len(received), 3)
        self.assertEqual(counters["response_failed_compaction_attempts"], 1)
        self.assertEqual(counters["response_failed_compaction_accepted"], 0)
        self.assertEqual(counters["empty_response_fallback_attempts"], 1)
        self.assertEqual(counters["empty_response_fallback_accepted"], 1)

    def test_downstream_disconnect_releases_response_slot(self):
        body = self._body(
            {
                "previous_response_id": "stale",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        started, release = threading.Event(), threading.Event()
        scripted = {
            "status": 200,
            "chunks": [SUCCESS],
            "started_event": started,
            "release_event": release,
        }
        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = serve_proxy([(477, EMPTY_RESPONSE), scripted], tmp)
            try:
                sock = socket.create_connection(("127.0.0.1", port))
                sock.sendall(
                    b"\r\n".join(
                        (
                            b"POST /v1/responses HTTP/1.1",
                            f"Host: 127.0.0.1:{port}".encode(),
                            f"Content-Length: {len(body)}".encode(),
                            b"Connection: close",
                            b"",
                            body,
                        )
                    )
                )
                self.assertTrue(started.wait(timeout=10))
                with contextlib.suppress(OSError):
                    sock.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_LINGER,
                        struct.pack("HH" if sys.platform == "win32" else "ii", 1, 0),
                    )
                sock.close()
                release.set()
                for _ in range(50):
                    active = proxy.runtime_status()["active_responses"]
                    if not active:
                        break
                    time.sleep(0.1)
            finally:
                cleanup()

        self.assertEqual(len(received), 2)
        self.assertEqual(proxy.runtime_status()["active_responses"], 0)
        self.assertEqual(self._cooldown_remaining(policy.policy_fingerprint(body)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
