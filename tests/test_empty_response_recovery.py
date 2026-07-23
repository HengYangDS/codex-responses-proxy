#!/usr/bin/env python3
"""Contract tests for the one-shot HTTP 477 empty-response recovery path.

The fake upstream returns 477 before any SSE response is established. A status
code cannot arrive after downstream SSE bytes, so the existing mid-stream EOF
logic remains a separate boundary and is not simulated here.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "proxy"))

import test_package as package_tests  # noqa: E402
import dmx_responses_proxy as proxy  # noqa: E402


EMPTY_RESPONSE = (
    b'{"error":{"message":"official provider returned an empty response",'
    b'"type":"dmx_api_error","code":"empty_response"}}'
)
UNKNOWN_477 = b'{"error":{"type":"dmx_api_error","code":"other"}}'
SUCCESS = b'{"id":"resp_recovered","status":"completed"}'


class EmptyResponseRecoveryTests(unittest.TestCase):
    _serve_proxy = package_tests.TestProxyTransport._serve_proxy
    _request = staticmethod(package_tests.TestProxyTransport._request)

    def setUp(self):
        self.p = proxy
        self.p._reset_runtime_metrics_for_test()

    @staticmethod
    def _body(payload):
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    def _read_http_error(self, port, body):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._request(port, body)
        error = raised.exception
        with error:
            payload = error.read()
            headers = error.headers
            code = error.code
        return code, headers, payload

    def _semantic_body(self):
        return self._body({
            "model": "gpt-5.6-terra",
            "stream": False,
            "previous_response_id": "resp_provider_state",
            "conversation": {"id": "conversation_provider_state"},
            "prompt_cache_key": "cache_provider_state",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {
                    "type": "reasoning",
                    "id": "reasoning_provider_state",
                    "encrypted_content": "opaque_provider_state",
                    "summary": [],
                },
                {
                    "type": "message",
                    "id": "message_provider_id",
                    "status": "completed",
                    "role": "developer",
                    "content": "current policy",
                },
                {
                    "type": "agent_message",
                    "id": "agent_provider_id",
                    "author": "planner",
                    "recipient": "user",
                    "phase": "commentary",
                    "content": [
                        {"type": "input_text", "text": "第一段 🧭"},
                        {"type": "input_text", "text": "second segment"},
                    ],
                },
                {
                    "type": "function_call",
                    "id": "function_provider_id",
                    "status": "completed",
                    "call_id": "function-1",
                    "name": "lookup",
                    "arguments": "{\"city\":\"杭州\"}",
                    "namespace": "weather",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "function_call_output",
                    "id": "function_output_provider_id",
                    "status": "completed",
                    "call_id": "function-1",
                    "output": "晴朗",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "custom_tool_call",
                    "id": "custom_provider_id",
                    "status": "completed",
                    "call_id": "custom-1",
                    "name": "terminal",
                    "input": "printf ok",
                    "namespace": "local",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "custom_tool_call_output",
                    "id": "custom_output_provider_id",
                    "status": "completed",
                    "call_id": "custom-1",
                    "output": [
                        {"type": "input_text", "text": "line one"},
                        {"type": "input_text", "text": "第二行"},
                    ],
                    "caller": {"type": "direct"},
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "continue from the tool results",
                },
            ],
        })

    def test_ordinary_first_attempt_is_exact_existing_sanitizer_output(self):
        body = self._semantic_body()
        sanitized, _note = self.p.sanitize_responses_body(body)

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
        sanitized, _note = self.p.sanitize_responses_body(body)

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
            ensure_ascii=False, separators=(",", ":"),
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

    def test_no_projection_needed_retries_the_exact_sanitized_bytes_once(self):
        body = self._body({
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        fallback, detail = self.p._build_empty_response_fallback(body)

        self.assertEqual(fallback, body)
        self.assertFalse(detail["projected"])

    def test_opaque_reasoning_has_a_fixed_explicit_marker(self):
        body = self._body({
            "input": [{
                "type": "reasoning",
                "id": "reasoning-id",
                "encrypted_content": "must-not-survive",
                "summary": [],
            }],
        })

        fallback, _detail = self.p._build_empty_response_fallback(body)

        projected = json.loads(fallback)
        self.assertEqual(projected["input"][0]["role"], "assistant")
        self.assertEqual(projected["input"][0]["phase"], "commentary")
        self.assertEqual(
            projected["input"][0]["content"],
            [{"type": "input_text", "text": self.p.EMPTY_RESPONSE_OPAQUE_REASONING_MARKER}],
        )
        self.assertNotIn("must-not-survive", fallback.decode())

    def test_builder_fails_closed_for_unknown_or_unrepresentable_history(self):
        cases = {
            "unknown item": [{"type": "future_item", "value": "opaque"}],
            "orphan output": [
                {"type": "function_call_output", "call_id": "missing", "output": "x"}
            ],
            "non-text agent content": [{
                "type": "agent_message",
                "author": "agent",
                "recipient": "user",
                "content": [{"type": "input_image", "image_url": "https://example.test/a.png"}],
            }],
            "encrypted agent content": [{
                "type": "agent_message",
                "author": "agent",
                "recipient": "user",
                "content": [{"type": "encrypted_content", "encrypted_content": "opaque"}],
            }],
            "duplicate output": [
                {"type": "custom_tool_call", "call_id": "c", "name": "t", "input": "x"},
                {"type": "custom_tool_call_output", "call_id": "c", "output": "one"},
                {"type": "custom_tool_call_output", "call_id": "c", "output": "two"},
            ],
            "invalid message role": [
                {"type": "message", "role": "narrator", "content": "hi"},
            ],
            "phase on a non-assistant message": [
                {"type": "message", "role": "user", "phase": "commentary", "content": "hi"},
            ],
            "unknown phase value": [
                {"type": "message", "role": "assistant", "phase": "final", "content": "hi"},
            ],
            "unknown extra message field": [
                {"type": "message", "role": "user", "content": "hi", "priority": "high"},
            ],
            "unknown extra content-block field": [
                {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "hi", "annotations": []},
                ]},
            ],
            "missing call_id": [
                {"type": "function_call", "name": "lookup", "arguments": "{}"},
            ],
            "empty name": [
                {"type": "function_call", "call_id": "c1", "name": "", "arguments": "{}"},
            ],
            "non-string arguments": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": {}},
            ],
            "unknown extra call field": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "extra": True},
            ],
            "malformed caller": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "direct", "extra": "field"}},
            ],
            "malformed namespace": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "namespace": ""},
            ],
            "agent_message empty author": [
                {"type": "agent_message", "author": "", "recipient": "user", "content": []},
            ],
            "agent_message unknown field": [
                {"type": "agent_message", "author": "a", "recipient": "user", "content": [],
                 "extra": True},
            ],
            "reasoning with visible summary": [
                {"type": "reasoning", "encrypted_content": "opaque",
                 "summary": [{"type": "summary_text", "text": "visible"}]},
            ],
            "reasoning unknown field": [
                {"type": "reasoning", "encrypted_content": "opaque", "unexpected": True},
            ],
        }
        for name, items in cases.items():
            with self.subTest(name=name):
                fallback, detail = self.p._build_empty_response_fallback(
                    self._body({"input": items})
                )
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

        oversized = self._body({
            "previous_response_id": "remove-me",
            "input": [{"type": "message", "role": "user", "content": "x" * 1000}],
        })
        fallback, detail = self.p._build_empty_response_fallback(oversized, budget=128)
        self.assertIsNone(fallback)
        self.assertEqual(detail["reason"], "budget_exceeded")

        for invalid_budget in (0, -1, 1.5, "128", True):
            fallback, detail = self.p._build_empty_response_fallback(
                self._body({"input": []}), budget=invalid_budget
            )
            self.assertIsNone(fallback)
            self.assertEqual(detail["reason"], "invalid_budget")

    def test_agent_message_header_is_deterministically_json_escaped(self):
        body = self._body({
            "input": [{
                "type": "agent_message",
                "author": 'planner"; drop table',
                "recipient": "user\nrecipient",
                "content": [{"type": "input_text", "text": "hello"}],
            }],
        })

        fallback, _detail = self.p._build_empty_response_fallback(body)

        projected = json.loads(fallback)
        header = projected["input"][0]["content"][0]
        self.assertEqual(
            header["text"],
            json.dumps(
                {
                    "type": "agent_message",
                    "author": 'planner"; drop table',
                    "recipient": "user\nrecipient",
                },
                ensure_ascii=False, separators=(",", ":"),
            ),
        )
        # The header is valid, self-contained JSON: embedded quotes/newlines in
        # author/recipient cannot break out of the fixed envelope.
        json.loads(header["text"])

    def test_string_input_is_preserved_losslessly(self):
        no_op = self._body({"stream": False, "input": "hello there"})
        fallback, detail = self.p._build_empty_response_fallback(no_op)
        self.assertEqual(fallback, no_op)
        self.assertFalse(detail["projected"])

        with_binding = self._body({
            "stream": False,
            "previous_response_id": "remove-me",
            "input": "hello there",
        })
        fallback, detail = self.p._build_empty_response_fallback(with_binding)
        self.assertTrue(detail["projected"])
        projected = json.loads(fallback)
        self.assertEqual(projected["input"], "hello there")
        self.assertNotIn("previous_response_id", projected)

    def test_unsafe_projection_returns_503_without_a_fallback_upstream_call(self):
        body = self._body({"stream": False, "input": [{"type": "future_item"}]})

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE)] * 4, tmp
            )
            try:
                code, headers, raw = self._read_http_error(port, body)
            finally:
                cleanup()

        self.assertEqual(code, 503)
        self.assertEqual(headers["Retry-After"], "3")
        self.assertEqual(json.loads(raw)["error"]["code"], "dmx_empty_response_exhausted")
        self.assertEqual(len(received), 1)

    def test_fallback_failure_is_terminal_after_exactly_two_upstream_attempts(self):
        body = self._body({
            "stream": False,
            "previous_response_id": "remove-on-fallback",
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        cases = (
            (400, b'{"error":{"code":"bad_request"}}'),
            (477, EMPTY_RESPONSE),
            (500, b'{"error":{"code":"upstream_failure"}}'),
        )
        for second_status, second_payload in cases:
            with self.subTest(second_status=second_status):
                self.p._reset_runtime_metrics_for_test()
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
        key = self.p._empty_response_policy_fingerprint(body)
        self.assertEqual(self.p._empty_response_cooldown_remaining(key, now=100.0), 0)

    def test_streaming_request_recovers_only_before_any_sse_bytes(self):
        body = self._body({
            "stream": True,
            "previous_response_id": "remove-on-fallback",
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE), recovered], tmp
            )
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
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE)] * 4, tmp
            )
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
            port, received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE)] * 8, tmp
            )
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
        self.assertEqual(status["counters"]["empty_response_cooldown_hits"], 1)

    def test_policy_fingerprint_binds_version_and_sanitized_original_bytes(self):
        first = self._body({
            "previous_response_id": "first",
            "input": [{"type": "message", "role": "user", "content": "same"}],
        })
        second = self._body({
            "previous_response_id": "second",
            "input": [{"type": "message", "role": "user", "content": "same"}],
        })
        first_fallback, _ = self.p._build_empty_response_fallback(first)
        second_fallback, _ = self.p._build_empty_response_fallback(second)
        self.assertEqual(first_fallback, second_fallback)

        first_key = self.p._empty_response_policy_fingerprint(first)
        second_key = self.p._empty_response_policy_fingerprint(second)
        expected = hashlib.sha256(
            self.p.EMPTY_RESPONSE_COMPAT_POLICY_VERSION.encode("utf-8") + first
        ).hexdigest()
        self.assertEqual(first_key, expected)
        self.assertNotEqual(first_key, second_key)
        self.p._remember_empty_response_failure(first_key, now=10.0)
        self.assertGreater(self.p._empty_response_cooldown_remaining(first_key, now=10.1), 0)
        self.assertEqual(self.p._empty_response_cooldown_remaining(second_key, now=10.1), 0)

    def test_cooldown_ttl_capacity_and_concurrent_access_are_bounded(self):
        self.p._remember_empty_response_failure("expires", now=100.0)
        self.assertGreater(self.p._empty_response_cooldown_remaining("expires", now=100.1), 0)
        with self.p._EMPTY_RESPONSE_FAILURES_LOCK:
            self.assertIn("expires", self.p._EMPTY_RESPONSE_FAILURES)
        past_ttl = 100.0 + self.p.EMPTY_RESPONSE_COOLDOWN_SECONDS + 0.1
        self.assertEqual(self.p._empty_response_cooldown_remaining("expires", now=past_ttl), 0)
        # The TTL purge is a real eviction, not merely a read-time comparison:
        # the reading call above must have removed the expired entry itself.
        with self.p._EMPTY_RESPONSE_FAILURES_LOCK:
            self.assertNotIn("expires", self.p._EMPTY_RESPONSE_FAILURES)

        # A stale entry is also purged by the next *write* to an unrelated key.
        self.p._remember_empty_response_failure("stale", now=300.0)
        self.p._remember_empty_response_failure(
            "other", now=300.0 + self.p.EMPTY_RESPONSE_COOLDOWN_SECONDS + 0.1
        )
        with self.p._EMPTY_RESPONSE_FAILURES_LOCK:
            self.assertNotIn("stale", self.p._EMPTY_RESPONSE_FAILURES)
            self.assertIn("other", self.p._EMPTY_RESPONSE_FAILURES)

        def remember(index):
            key = f"key-{index}"
            self.p._remember_empty_response_failure(key, now=200.0 + index / 10_000)
            return self.p._empty_response_cooldown_remaining(key, now=200.0)

        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(remember, range(self.p.EMPTY_RESPONSE_COOLDOWN_CAPACITY + 100)))
        with self.p._EMPTY_RESPONSE_FAILURES_LOCK:
            self.assertLessEqual(
                len(self.p._EMPTY_RESPONSE_FAILURES),
                self.p.EMPTY_RESPONSE_COOLDOWN_CAPACITY,
            )
            self.assertNotIn("key-0", self.p._EMPTY_RESPONSE_FAILURES)

    def test_successful_fallback_does_not_enter_cooldown_and_metrics_are_secret_free(self):
        secret = "private-prompt-must-not-appear"
        body = self._body({
            "stream": False,
            "previous_response_id": "remove-on-fallback",
            "input": [{"type": "message", "role": "user", "content": secret}],
        })
        with tempfile.TemporaryDirectory() as tmp:
            port, _received, cleanup = self._serve_proxy(
                [(477, EMPTY_RESPONSE), (200, SUCCESS)], tmp
            )
            try:
                with self._request(port, body) as response:
                    self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        key = self.p._empty_response_policy_fingerprint(body)
        self.assertEqual(self.p._empty_response_cooldown_remaining(key), 0)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["empty_response_fallback_attempts"], 1)
        self.assertEqual(status["counters"]["empty_response_fallback_accepted"], 1)
        self.assertNotIn(secret, json.dumps(status))
        self.assertNotIn(key, json.dumps(status))

    def test_existing_400_response_failed_chain_remains_independent(self):
        response_failed = b'{"error":{"code":"response_failed"}}'
        body = self._body({
            "stream": False,
            "input": [
                {"type": "message", "role": "user", "content": "x" * 100_000},
                {"type": "message", "role": "user", "content": "latest"},
            ],
        })
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
        self.assertEqual(status["counters"]["response_failed_compaction_attempts"], 1)
        self.assertEqual(status["counters"]["empty_response_fallback_attempts"], 0)
        with self.p._EMPTY_RESPONSE_FAILURES_LOCK:
            self.assertEqual(len(self.p._EMPTY_RESPONSE_FAILURES), 0)

    def test_dedicated_slot_survives_ordinary_transient_retry_budget(self):
        # Three ordinary 500s consume the entire ordinary retry ceiling
        # (``max_attempts - 1``); a classified 477 hitting immediately after
        # must still get its own dedicated fallback attempt and succeed, even
        # when the pair-safe ``response_failed`` compaction budget -- whose
        # spare loop range this dedicated slot must not depend on -- is
        # disabled entirely.
        body = self._body({
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        transient = b'{"error":{"code":"upstream_failure"}}'
        responses = [
            (500, transient), (500, transient), (500, transient),
            (477, EMPTY_RESPONSE), (200, SUCCESS),
        ]

        original_stages = self.p.RESPONSE_FAILED_MAX_STAGES
        self.p.RESPONSE_FAILED_MAX_STAGES = 0
        try:
            with tempfile.TemporaryDirectory() as tmp:
                port, received, cleanup = self._serve_proxy(responses, tmp)
                try:
                    with self._request(port, body) as response:
                        self.assertEqual(response.read(), SUCCESS)
                finally:
                    cleanup()
        finally:
            self.p.RESPONSE_FAILED_MAX_STAGES = original_stages

        self.assertEqual(len(received), 5)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["empty_response_fallback_attempts"], 1)
        self.assertEqual(status["counters"]["empty_response_fallback_accepted"], 1)

    def test_success_after_compaction_and_fallback_credits_only_fallback(self):
        # A request that first goes through a ``response_failed`` pair-safe
        # compaction stage and *then* hits a classified 477 must, on eventual
        # success, credit only ``empty_response_fallback_accepted``: the
        # earlier compacted bytes were never themselves accepted upstream.
        response_failed = b'{"error":{"code":"response_failed"}}'
        body = self._body({
            "stream": False,
            "input": [
                {"type": "message", "role": "user", "content": "x" * 100_000},
                {"type": "message", "role": "user", "content": "latest"},
            ],
        })
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
        self.assertEqual(status["counters"]["response_failed_compaction_attempts"], 1)
        self.assertEqual(status["counters"]["response_failed_compaction_accepted"], 0)
        self.assertEqual(status["counters"]["empty_response_fallback_attempts"], 1)
        self.assertEqual(status["counters"]["empty_response_fallback_accepted"], 1)

    def test_final_answer_phase_is_preserved_and_unknown_values_still_rejected(self):
        body = self._body({
            "input": [
                {"type": "message", "role": "assistant", "phase": "final_answer", "content": "done"},
                {"type": "agent_message", "author": "a", "recipient": "b", "phase": "final_answer",
                 "content": [{"type": "input_text", "text": "hi"}]},
            ],
        })
        fallback, detail = self.p._build_empty_response_fallback(body)
        self.assertIsNotNone(fallback)
        projected = json.loads(fallback)
        self.assertEqual(projected["input"][0]["phase"], "final_answer")
        self.assertEqual(projected["input"][1]["phase"], "final_answer")

        # An unknown/unvetted phase remains rejected for both item shapes.
        for items in (
            [{"type": "message", "role": "assistant", "phase": "final", "content": "hi"}],
            [{"type": "agent_message", "author": "a", "recipient": "b", "phase": "final",
              "content": [{"type": "input_text", "text": "hi"}]}],
        ):
            with self.subTest(items=items):
                fallback, detail = self.p._build_empty_response_fallback(self._body({"input": items}))
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

    def test_caller_validation_accepts_direct_and_well_formed_program_and_rejects_others(self):
        accepted = self._body({
            "input": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "program", "caller_id": "prog-1"}},
                {"type": "function_call_output", "call_id": "c1", "output": "ok",
                 "caller": {"type": "program", "caller_id": "prog-1"}},
            ],
        })
        fallback, detail = self.p._build_empty_response_fallback(accepted)
        self.assertIsNotNone(fallback)
        projected = json.loads(fallback)
        self.assertEqual(projected["input"][0]["caller"], {"type": "program", "caller_id": "prog-1"})
        self.assertEqual(projected["input"][1]["caller"], {"type": "program", "caller_id": "prog-1"})

        rejected_cases = {
            "arbitrary type on call": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "indirect"}},
            ],
            "program missing caller_id on call": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "program"}},
            ],
            "program empty caller_id on call": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "program", "caller_id": ""}},
            ],
            "program extra key on call": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}",
                 "caller": {"type": "program", "caller_id": "p", "extra": "x"}},
            ],
            "arbitrary type on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok",
                 "caller": {"type": "indirect"}},
            ],
            "program missing caller_id on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok",
                 "caller": {"type": "program"}},
            ],
            "program empty caller_id on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok",
                 "caller": {"type": "program", "caller_id": ""}},
            ],
        }
        for name, items in rejected_cases.items():
            with self.subTest(name=name):
                fallback, detail = self.p._build_empty_response_fallback(self._body({"input": items}))
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

    def test_non_list_or_non_string_include_entry_is_rejected(self):
        for bad_include in ("reasoning.encrypted_content", ["ok", 5], {"x": 1}):
            with self.subTest(bad_include=bad_include):
                fallback, detail = self.p._build_empty_response_fallback(
                    self._body({"include": bad_include, "input": []})
                )
                self.assertIsNone(fallback)
                self.assertEqual(detail["reason"], "invalid_include")

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
        body = self._body({
            "stream": False,
            "previous_response_id": "remove-on-fallback",
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        transient = b'{"error":{"code":"upstream_failure"}}'
        response_failed = b'{"error":{"code":"response_failed"}}'
        responses = (
            [(500, transient)] * 3
            + [(400, response_failed)] * 4
            + [(477, EMPTY_RESPONSE), (200, SUCCESS)]
        )

        def fake_compact(raw, budget=None):
            fake_compact.calls += 1
            filler = "x" * (50 - 10 * fake_compact.calls)
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
        fake_compact.calls = 0

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

        sanitized, _note = self.p.sanitize_responses_body(body)
        expected_fallback, expected_detail = self.p._build_empty_response_fallback(sanitized)
        self.assertIsNotNone(expected_fallback)

        with tempfile.TemporaryDirectory() as tmp:
            port, received, cleanup = self._serve_proxy(responses, tmp)
            try:
                with mock.patch.object(
                    self.p, "_compact_response_failed_request", side_effect=fake_compact
                ), mock.patch.object(
                    self.p, "_recover_response_failed_dialogue", side_effect=fake_dialogue
                ):
                    with self._request(port, body) as response:
                        self.assertEqual(response.read(), SUCCESS)
            finally:
                cleanup()

        self.assertEqual(len(received), 9)
        self.assertEqual(received[-1], expected_fallback)
        status = self.p.runtime_status()
        self.assertEqual(status["counters"]["response_failed_compaction_attempts"], 3)
        self.assertEqual(status["counters"]["response_failed_compaction_accepted"], 0)
        self.assertEqual(status["counters"]["response_failed_dialogue_recovery_attempts"], 1)
        self.assertEqual(status["counters"]["response_failed_dialogue_recovery_accepted"], 0)
        self.assertEqual(status["counters"]["empty_response_fallback_attempts"], 1)
        self.assertEqual(status["counters"]["empty_response_fallback_accepted"], 1)

    def test_downstream_disconnect_during_fallback_does_not_loop_or_leak(self):
        # Simulate a downstream client disconnect while the classified-477
        # fallback request is in flight. Use the ``started_event`` /
        # ``release_event`` barrier to pause the second upstream response,
        # close the downstream socket with an RST (SO_LINGER), then release.
        body = self._body({
            "stream": False,
            "previous_response_id": "remove-on-fallback",
            "input": [{"type": "message", "role": "user", "content": "hello"}],
        })
        sanitized, _ = self.p.sanitize_responses_body(body)
        fallback_body, _ = self.p._build_empty_response_fallback(sanitized)

        started = threading.Event()
        release = threading.Event()

        responses = [
            (477, EMPTY_RESPONSE),
            {
                "status": 200,
                "chunks": [SUCCESS],
                "started_event": started,
                "release_event": release,
            }
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
                    body
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
                    if self.p.runtime_status()["active_responses"] == 0:
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
        key = self.p._empty_response_policy_fingerprint(body)
        self.assertEqual(self.p._empty_response_cooldown_remaining(key), 0)
        self.assertEqual(status["counters"]["empty_response_fallback_accepted"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)