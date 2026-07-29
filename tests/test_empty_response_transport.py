#!/usr/bin/env python3
"""HTTP dispatch, cooldown, retry, SSE, and disconnect contracts for empty responses."""

from __future__ import annotations

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
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proxy"))
sys.path.insert(0, str(ROOT))

import dmx_responses_proxy as proxy
import empty_response as policy
import response_failed as response_failed_policy
import responses_rewrite
import runtime_state
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
        self.p = proxy
        runtime_state.reset_for_test()

    _body = staticmethod(body)
    _request = staticmethod(request)

    @staticmethod
    def _serve_proxy(responses, log_dir):
        return serve_proxy(responses, log_dir)

    @staticmethod
    def _remember_failure(key, *, now=None):
        runtime_state.remember_empty_response_failure(
            key,
            capacity=policy.COOLDOWN_CAPACITY,
            cooldown_seconds=policy.COOLDOWN_SECONDS,
            now=now,
        )

    @staticmethod
    def _cooldown_remaining(key, *, now=None):
        return runtime_state.empty_response_cooldown_remaining(
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

    _semantic_body = staticmethod(semantic_body)

    def test_ordinary_first_attempt_is_exact_existing_sanitizer_output(self):
        body = self._semantic_body()
        sanitized, _note = responses_rewrite.sanitize_responses_body(body)

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(200, SUCCESS)], tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(received, [sanitized])
        first = json.loads(received[0])
        self.assertEqual(first["input"][0]["type"], "message")
        self.assertEqual(first["input"][1]["type"], "agent_message")
        self.assertEqual(first["input"][2]["type"], "function_call")
        self.assertIn("previous_response_id", first)

    def test_classified_477_projects_semantics_once_in_original_order(self):
        body = self._semantic_body()
        sanitized, _note = responses_rewrite.sanitize_responses_body(body)

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(received[0], sanitized)
        self.assertEqual(len(received), 2)
        fallback = json.loads(received[1])
        self.assertNotEqual(received[1], sanitized)
        for field in ("previous_response_id", "conversation", "prompt_cache_key"):
            self.assertNotIn(field, fallback)
        self.assertEqual(fallback["include"], ["other"])
        self.assertEqual(
            [item["type"] for item in fallback["input"]],
            [
                "message",
                "message",
                "function_call",
                "function_call_output",
                "custom_tool_call",
                "custom_tool_call_output",
                "message",
            ],
        )
        assistant = fallback["input"][1]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["phase"], "commentary")
        expected_header_text = json.dumps(
            {"type": "agent_message", "author": "planner", "recipient": "user"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertEqual(
            assistant["content"],
            [
                {"type": "input_text", "text": expected_header_text},
                {"type": "input_text", "text": "第一段 🧭"},
                {"type": "input_text", "text": "second segment"},
            ],
        )
        function_call, function_output, custom_call, custom_output = fallback["input"][2:6]
        self.assertEqual(function_call["call_id"], function_output["call_id"])
        self.assertEqual(custom_call["call_id"], custom_output["call_id"])
        self.assertEqual(function_call["namespace"], "weather")
        self.assertEqual(custom_output["output"][1]["text"], "第二行")
        for item in fallback["input"]:
            self.assertNotIn("id", item)
            self.assertNotIn("status", item)
        serialized = json.dumps(fallback, ensure_ascii=False)
        for provider_value in (
            "message_provider_id",
            "agent_provider_id",
            "function_provider_id",
            "function_output_provider_id",
            "custom_provider_id",
            "custom_output_provider_id",
            "opaque_provider_state",
        ):
            self.assertNotIn(provider_value, serialized)

    def test_unsafe_projection_returns_503_without_a_fallback_upstream_call(self):
        body = self._body({"stream": False, "input": [{"type": "future_item"}]})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
            try:
                code, headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 503)
        self.assertEqual(headers["Retry-After"], "3")
        self.assertEqual(json.loads(raw)["error"]["code"], "dmx_empty_response_exhausted")
        self.assertEqual(len(received), 1)

    def test_unknown_history_uses_strict_dialogue_fallback_when_current_messages_are_safe(self):
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "provider-history-binding",
                "prompt_cache_key": "provider-history-cache",
                "input": [
                    {"type": "message", "role": "system", "content": "system policy"},
                    {"type": "message", "role": "developer", "content": "current instruction"},
                    {"type": "web_search_call", "action": {"type": "search", "query": "old query"}},
                    {
                        "type": "tool_search_call",
                        "call_id": "search-1",
                        "execution": "server",
                        "arguments": {"query": "old query", "limit": 3},
                    },
                    {
                        "type": "tool_search_output",
                        "call_id": "search-1",
                        "execution": "server",
                        "tools": [{"type": "tool", "name": "search"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "old answer"}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "current user request"}],
                    },
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 2)
        fallback = json.loads(received[1])
        self.assertNotIn("previous_response_id", fallback)
        self.assertNotIn("prompt_cache_key", fallback)
        self.assertEqual(
            fallback["input"],
            [
                {"type": "message", "role": "system", "content": "system policy"},
                {"type": "message", "role": "developer", "content": "current instruction"},
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "current user request"}],
                },
            ],
        )

    def test_non_search_unknown_history_does_not_spend_dialogue_fallback(self):
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "provider-history-binding",
                "input": [
                    {"type": "future_item", "opaque": "x" * 256},
                    {"type": "message", "role": "user", "content": "current user request"},
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
            try:
                code, _headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 503)
        self.assertEqual(json.loads(raw)["error"]["attempts"], 1)
        self.assertEqual(len(received), 1)

    def test_unknown_history_with_unrepresentable_current_user_still_returns_503(self):
        body = self._body(
            {
                "stream": False,
                "input": [
                    {"type": "web_search_call", "action": {"type": "search", "query": "old query"}},
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": "https://example.test/image.png"}
                        ],
                    },
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
            try:
                code, _headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 503)
        self.assertEqual(json.loads(raw)["error"]["attempts"], 1)
        self.assertEqual(len(received), 1)

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
                runtime_state.reset_for_test()
                responses = [(477, EMPTY_RESPONSE), (second_status, second_payload)]
                if second_status in (477, 500):
                    responses.extend([(second_status, second_payload)] * 3)
                with tempfile.TemporaryDirectory() as tmp:
                    port, received, cleanup = self._serve_proxy(responses, tmp)
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
            port, received, cleanup = self._serve_proxy([(477, UNKNOWN_477)], tmp)
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
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE), recovered], tmp)
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
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE)] * 4, tmp)
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
            port, received, cleanup = self._serve_proxy([(477, EMPTY_RESPONSE)] * 8, tmp)
            try:
                first = self._read_http_error(port, body)
                second = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(first[0], 503)
        self.assertEqual(second[0], 503)
        self.assertEqual(json.loads(second[2])["error"]["attempts"], 0)
        self.assertEqual(len(received), 2)
        status = self.p.runtime_status()
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
        self.assertTrue(runtime_state.has_empty_response_failure_for_test("expires"))
        past_ttl = 100.0 + policy.COOLDOWN_SECONDS + 0.1
        self.assertEqual(self._cooldown_remaining("expires", now=past_ttl), 0)
        # The TTL purge is a real eviction, not merely a read-time comparison:
        # the reading call above must have removed the expired entry itself.
        self.assertFalse(runtime_state.has_empty_response_failure_for_test("expires"))

        # A stale entry is also purged by the next *write* to an unrelated key.
        self._remember_failure("stale", now=300.0)
        self._remember_failure("other", now=300.0 + policy.COOLDOWN_SECONDS + 0.1)
        self.assertFalse(runtime_state.has_empty_response_failure_for_test("stale"))
        self.assertTrue(runtime_state.has_empty_response_failure_for_test("other"))

        def remember(index):
            key = f"key-{index}"
            self._remember_failure(key, now=200.0 + index / 10_000)
            return self._cooldown_remaining(key, now=200.0)

        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(remember, range(policy.COOLDOWN_CAPACITY + 100)))
        self.assertLessEqual(
            runtime_state.empty_response_failure_count_for_test(),
            policy.COOLDOWN_CAPACITY,
        )
        self.assertFalse(runtime_state.has_empty_response_failure_for_test("key-0"))

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
            port, _received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        key = policy.policy_fingerprint(body)
        self.assertEqual(self._cooldown_remaining(key), 0)
        status = self.p.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )
        self.assertNotIn(secret, json.dumps(status))
        self.assertNotIn(key, json.dumps(status))

    def test_existing_400_response_failed_chain_remains_independent(self):
        response_failed = b'{"error":{"code":"response_failed"}}'
        body = self._body(
            {
                "stream": False,
                "input": [
                    {"type": "message", "role": "user", "content": "x" * 100_000},
                    {"type": "message", "role": "user", "content": "latest"},
                ],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(400, response_failed), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 2)
        status = self.p.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["response_failed_compaction_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 0
        )
        self.assertEqual(runtime_state.empty_response_failure_count_for_test(), 0)

    def test_dedicated_slot_survives_ordinary_transient_retry_budget(self):
        # Three ordinary 500s consume the entire ordinary retry ceiling
        # (``max_attempts - 1``); a classified 477 hitting immediately after
        # must still get its own dedicated fallback attempt and succeed, even
        # when the pair-safe ``response_failed`` compaction budget -- whose
        # spare loop range this dedicated slot must not depend on -- is
        # disabled entirely.
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

        original_stages = response_failed_policy.MAX_STAGES
        response_failed_policy.MAX_STAGES = 0
        try:
            with tempfile.TemporaryDirectory() as tmp:
                port, received, cleanup = self._serve_proxy(responses, tmp)
                try:
                    with self._request(port, body) as response:
                        self.assertEqual(response.read(), SUCCESS)
                finally:
                    cleanup()
        finally:
            response_failed_policy.MAX_STAGES = original_stages

        self.assertEqual(len(received), 5)
        status = self.p.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )

    def test_success_after_compaction_and_fallback_credits_only_fallback(self):
        # A request that first goes through a ``response_failed`` pair-safe
        # compaction stage and *then* hits a classified 477 must, on eventual
        # success, credit only ``empty_response_fallback_accepted``: the
        # earlier compacted bytes were never themselves accepted upstream.
        response_failed = b'{"error":{"code":"response_failed"}}'
        body = self._body(
            {
                "stream": False,
                "input": [
                    {"type": "message", "role": "user", "content": "x" * 100_000},
                    {"type": "message", "role": "user", "content": "latest"},
                ],
            }
        )
        responses = [(400, response_failed), (477, EMPTY_RESPONSE), (200, SUCCESS)]

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(responses, tmp)
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 3)
        status = self.p.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["response_failed_compaction_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["response_failed_compaction_accepted"], 0
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )

    def test_dedicated_fallback_dispatch_is_independent_of_outer_loop_capacity(self):
        # Three ordinary 500 retries, then four classified ``response_failed``
        # results consuming all three pair-safe compaction stages plus the one
        # dialogue-recovery transition, then a classified 477, then a
        # successful fallback. The outer loop's range is fully consumed by
        # the time the 477 is seen (it lands on the loop's very last
        # iteration), so the dedicated fallback attempt must be dispatched as
        # its own independent nested request rather than by ``continue``-ing
        # to another outer iteration that does not exist. If the fallback
        # merely ``continue``s at the last outer index, the ninth upstream
        # call below is never made and this test fails.
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "remove-on-fallback",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        transient = b'{"error":{"code":"upstream_failure"}}'
        response_failed = b'{"error":{"code":"response_failed"}}'
        responses = (
            [(500, transient)] * 3
            + [(400, response_failed)] * 4
            + [(477, EMPTY_RESPONSE), (200, SUCCESS)]
        )

        compact_calls = 0

        def fake_compact(raw: bytes, budget: int | None = None):
            nonlocal compact_calls
            compact_calls += 1
            filler = "x" * (50 - 10 * compact_calls)
            compacted = json.dumps(
                {"input": [{"type": "message", "role": "user", "content": filler}]},
                separators=(",", ":"),
            ).encode()
            metrics = {
                "original_bytes": len(raw),
                "compact_bytes": len(compacted),
                "budget_bytes": 1000,
                "removed_inputs": 1,
                "retained_inputs": 1,
                "prompt_cache_key_removed": False,
                "budget_met": True,
            }
            return compacted, metrics

        def fake_dialogue(raw, budget=None):
            recovered = json.dumps(
                {"input": [{"type": "message", "role": "user", "content": "d"}]},
                separators=(",", ":"),
            ).encode()
            metrics = {
                "original_bytes": len(raw),
                "recovery_bytes": len(recovered),
                "retained_messages": 1,
                "dropped_input_items": 1,
                "prompt_cache_key_removed": False,
            }
            return recovered, metrics

        sanitized, _note = responses_rewrite.sanitize_responses_body(body)
        expected_fallback, expected_detail = policy.build_fallback(sanitized)
        self.assertIsNotNone(expected_fallback)

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(responses, tmp)
            try:
                with (
                    mock.patch.object(
                        response_failed_policy, "compact_request", side_effect=fake_compact
                    ),
                    mock.patch.object(
                        response_failed_policy, "recover_dialogue", side_effect=fake_dialogue
                    ),
                ):
                    with self._request(port, body) as response:
                        self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 9)
        self.assertEqual(received[-1], expected_fallback)
        status = self.p.runtime_status()
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["response_failed_compaction_attempts"], 3
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["response_failed_compaction_accepted"], 0
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])[
                "response_failed_dialogue_recovery_attempts"
            ],
            1,
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])[
                "response_failed_dialogue_recovery_accepted"
            ],
            0,
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_attempts"], 1
        )
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )

    def test_downstream_disconnect_during_fallback_does_not_loop_or_leak(self):
        # Simulate a downstream client disconnect while the classified-477
        # fallback request is in flight. Use the ``started_event`` /
        # ``release_event`` barrier to pause the second upstream response,
        # close the downstream socket with an RST (SO_LINGER), then release.
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "remove-on-fallback",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        sanitized, _ = responses_rewrite.sanitize_responses_body(body)
        fallback_body, _ = policy.build_fallback(sanitized)

        started = threading.Event()
        release = threading.Event()

        responses = [
            (477, EMPTY_RESPONSE),
            {
                "status": 200,
                "chunks": [SUCCESS],
                "started_event": started,
                "release_event": release,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(responses, tmp)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(("127.0.0.1", port))

                # Raw HTTP POST
                request_lines = [
                    b"POST /responses HTTP/1.1",
                    f"Host: 127.0.0.1:{port}".encode(),
                    b"Content-Type: application/json",
                    f"Content-Length: {len(body)}".encode(),
                    b"Connection: close",
                    b"",
                    body,
                ]
                sock.sendall(b"\r\n".join(request_lines))

                # 1. First upstream attempt (477) happens immediately.
                # 2. Proxy builds fallback and starts second upstream attempt.
                if not started.wait(timeout=10):
                    self.fail("Fallback upstream did not start in time")

                # 3. Downstream client disconnects with RST while upstream is in-flight.
                # macOS/Linux: ii (int, int); Windows: HH (ushort, ushort) or similar.
                # We try both or fallback to plain close as requested.
                try:
                    fmt = "HH" if sys.platform == "win32" else "ii"
                    linger = struct.pack(fmt, 1, 0)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
                except Exception:
                    pass
                sock.close()

                # 4. Release the upstream to finish the fallback attempt.
                release.set()

                # 5. Wait for proxy to detect disconnect and release the slot.
                for _ in range(50):
                    if cast("int", self.p.runtime_status()["active_responses"]) == 0:
                        break
                    time.sleep(0.1)
            finally:
                cleanup()

        # Assert exactly two upstream bodies received (no replay/loop)
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0], sanitized)
        self.assertEqual(received[1], fallback_body)

        # Assert active count returns to zero
        status = self.p.runtime_status()
        self.assertEqual(status["active_responses"], 0)

        # Assert accepted fallback does not arm cooldown
        key = policy.policy_fingerprint(body)
        self.assertEqual(self._cooldown_remaining(key), 0)
        self.assertEqual(
            cast("dict[str, int]", status["counters"])["empty_response_fallback_accepted"], 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
