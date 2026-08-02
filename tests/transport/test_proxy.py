#!/usr/bin/env python3
"""End-to-end HTTP and SSE behavior through real loopback proxy hops."""

from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.recovery import response_failed as response_failed_policy  # noqa: E402
from codex_responses_proxy.runtime import admission, logging, telemetry  # noqa: E402
from codex_responses_proxy.transport import cooldown  # noqa: E402
from codex_responses_proxy.replay import request as rewrite  # noqa: E402
from codex_responses_proxy.transport import exchange as upstream_exchange  # noqa: E402
from tests.listener.proxy_fixture import running_proxy  # noqa: E402
from tests.listener.proxy_fixture import request  # noqa: E402


class TestProxyTransport(unittest.TestCase):
    """Exercise retry behavior through real local HTTP hops."""

    def setUp(self):
        from codex_responses_proxy.listener import entrypoint as p

        self.p = p
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()

    def exchange(self, scripted, body):
        """Run one loopback exchange and return received requests and payload."""
        with running_proxy(scripted) as (port, received), request(port, body) as response:
            self.assertEqual(response.status, 200)
            return received, response.read()

    def test_recovers_response_failed_with_pair_safe_compact_request(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "prompt_cache_key": "full-history-cache-key",
                "input": [
                    {"type": "message", "role": "user", "content": "old" + "x" * 100_000},
                    {
                        "type": "function_call",
                        "call_id": "call_old",
                        "name": "tool",
                        "arguments": "{}",
                    },
                    {"type": "function_call_output", "call_id": "call_old", "output": "old result"},
                    {"type": "message", "role": "user", "content": "latest user context"},
                ],
            },
            separators=(",", ":"),
        ).encode()

        received, payload = self.exchange([(400, response_failed), (200, success)], body)
        self.assertEqual(payload, success)

        self.assertEqual(received[0], rewrite.sanitize_responses_body(body).body)
        self.assertEqual(len(received), 2)
        compact = json.loads(received[1])
        self.assertLess(len(received[1]), len(body))
        self.assertNotIn("prompt_cache_key", compact)
        self.assertEqual(compact["input"][-1]["content"], "latest user context")
        call_types = {"custom_tool_call", "function_call"}
        output_types = {"custom_tool_call_output", "function_call_output"}
        calls = {item["call_id"] for item in compact["input"] if item.get("type") in call_types}
        outputs = {item["call_id"] for item in compact["input"] if item.get("type") in output_types}
        self.assertTrue(outputs.issubset(calls))

    def test_recovers_blocked_invalid_prompt_with_pair_safe_compact_request(self):
        blocked = (
            b'{"error":{"message":"Request blocked. (request id: fixture)",'
            b'"type":"invalid_request_error","param":"","code":"invalid_prompt"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "prompt_cache_key": "full-history-cache-key",
                "input": [
                    {"type": "message", "role": "developer", "content": "policy"},
                    {"type": "message", "role": "user", "content": "old" + "x" * 100_000},
                    {
                        "type": "function_call",
                        "call_id": "call_old",
                        "name": "tool",
                        "arguments": "{}",
                    },
                    {"type": "function_call_output", "call_id": "call_old", "output": "old result"},
                    {"type": "message", "role": "user", "content": "latest user context"},
                ],
            },
            separators=(",", ":"),
        ).encode()

        received, payload = self.exchange([(400, blocked), (200, success)], body)
        self.assertEqual(payload, success)

        self.assertEqual(received[0], rewrite.sanitize_responses_body(body).body)
        self.assertEqual(len(received), 2)
        compact = json.loads(received[1])
        self.assertLess(len(received[1]), len(body))
        self.assertNotIn("prompt_cache_key", compact)
        self.assertEqual(compact["input"][-1]["content"], "latest user context")
        classifications = cast(
            "dict[str, int]", self.p.runtime_status()["upstream_classifications"]
        )
        self.assertEqual(classifications.get("blocked_invalid_prompt"), 1)
        self.assertNotIn("response_failed", classifications)

    def test_passes_through_unrelated_invalid_prompt(self):
        invalid_prompt = (
            b'{"error":{"message":"caller supplied an unsupported option",'
            b'"type":"invalid_request_error","param":"tool_choice","code":"invalid_prompt"}}'
        )
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "input": [
                    {"type": "message", "role": "user", "content": "latest user context"},
                ],
            },
            separators=(",", ":"),
        ).encode()

        with running_proxy([(400, invalid_prompt)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.exception:
                self.assertEqual(raised.exception.code, 400)
                self.assertEqual(raised.exception.read(), invalid_prompt)

        self.assertEqual(json.loads(received[0]), {**json.loads(body), "store": False})

    def test_recovers_response_failed_with_dialogue_only_last_resort(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "prompt_cache_key": "full-history-cache-key",
                "input": [
                    {"type": "message", "role": "developer", "content": "old" + "x" * 100_000},
                    {"type": "message", "role": "developer", "content": "current policy"},
                    {"type": "message", "role": "user", "content": "latest user context"},
                    {
                        "type": "custom_tool_call",
                        "call_id": "call_new",
                        "name": "tool",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "call_new",
                        "output": "tool result",
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()

        with (
            running_proxy([(400, response_failed), (400, response_failed), (200, success)]) as (
                port,
                received,
            ),
            mock.patch.object(response_failed_policy, "MAX_STAGES", 1),
            mock.patch.object(logging, "log") as log,
            request(port, body) as response,
        ):
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), success)
        logs = "\n".join(call.args[0] for call in log.call_args_list)

        self.assertEqual(received[0], rewrite.sanitize_responses_body(body).body)
        self.assertEqual(len(received), 3)
        recovery = json.loads(received[2])
        self.assertNotIn("prompt_cache_key", recovery)
        self.assertEqual(
            recovery["input"],
            [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user context"},
            ],
        )
        self.assertIn("event=response_failed_dialogue_recovery_accepted", logs)
        self.assertNotIn("event=response_failed_compact_recovery_accepted", logs)

    def test_normalizes_exhausted_response_failed_recovery_to_retryable_503(self):
        response_failed = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "input": [
                    {"type": "message", "role": "developer", "content": "current policy"},
                    {"type": "message", "role": "user", "content": "latest user context"},
                    {
                        "type": "custom_tool_call",
                        "call_id": "call_new",
                        "name": "tool",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "call_new",
                        "output": "tool result",
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()

        with (
            running_proxy([(400, response_failed), (400, response_failed)]) as (port, received),
            mock.patch.object(response_failed_policy, "MAX_STAGES", 0),
        ):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            error = raised.exception
            with error:
                self.assertEqual(error.code, 503)
                self.assertEqual(error.headers["Retry-After"], "3")
                payload = json.loads(error.read())

        self.assertEqual(len(received), 1)
        self.assertEqual(payload["error"]["code"], "response_failed_recovery_exhausted")

    def test_retries_classified_empty_response_at_most_once_with_unchanged_body(self):
        empty_response = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            },
            separators=(",", ":"),
        ).encode()

        with mock.patch.object(upstream_exchange.time, "sleep", return_value=None):
            received, payload = self.exchange([(477, empty_response), (200, success)], body)
        self.assertEqual(payload, success)

        self.assertEqual(received[0], received[1])
        self.assertEqual(json.loads(received[0]), {**json.loads(body), "store": False})

    def test_runtime_metrics_classify_recovery_without_retaining_request_content(self):
        response_failed = b'{"error":{"type":"new_api_error","code":"response_failed"}}'
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = json.dumps(
            {
                "stream": False,
                "input": [
                    {"type": "reasoning", "encrypted_content": "secret-replay"},
                    {"type": "message", "role": "user", "content": "old context"},
                    {"type": "message", "role": "user", "content": "x" * 100_000},
                    {"type": "message", "role": "user", "content": "private prompt"},
                ],
            },
            separators=(",", ":"),
        ).encode()

        _received, payload = self.exchange([(400, response_failed), (200, success)], body)
        self.assertEqual(payload, success)

        status = self.p.runtime_status()
        counters = cast("dict[str, int]", status["counters"])
        classifications = cast("dict[str, int]", status["upstream_classifications"])
        self.assertEqual(counters["responses_received"], 1)
        self.assertEqual(counters["encrypted_replayed_reasoning_items_stripped"], 1)
        self.assertEqual(counters["response_failed_compaction_attempts"], 1)
        self.assertEqual(counters["response_failed_compaction_accepted"], 1)
        self.assertEqual(classifications["response_failed"], 1)
        self.assertNotIn("private prompt", json.dumps(status))
        self.assertNotIn("secret-replay", json.dumps(status))

    def test_loopback_healthz_returns_machine_readable_metrics(self):
        with (
            running_proxy([]) as (port, _received),
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f"http://127.0.0.1:{port}/healthz"
            ) as response,
        ):
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "application/json")
            status = json.loads(response.read())

        self.assertIn("counters", status)
        self.assertIn("upstream_classifications", status)
        self.assertIsNone(status["last_failure"])

    def test_loopback_drain_rejects_new_responses_and_can_be_reopened(self):
        success = b'{"id":"resp_served","status":"completed"}'
        body = json.dumps({"stream": False, "input": []}).encode()
        with running_proxy([(200, success)]) as (port, received):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drain = urllib.request.Request(
                f"http://127.0.0.1:{port}/control/drain",
                method="POST",
            )
            with opener.open(drain) as response:
                snapshot = json.loads(response.read())
            self.assertTrue(snapshot["draining"])
            self.assertEqual(snapshot["active_responses"], 0)

            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.exception:
                self.assertEqual(raised.exception.code, 503)
                self.assertEqual(raised.exception.headers["Retry-After"], "1")
                payload = json.loads(raised.exception.read())
            self.assertEqual(payload["error"]["code"], "proxy_draining")
            self.assertEqual(received, [])

            reopen = urllib.request.Request(
                f"http://127.0.0.1:{port}/control/drain",
                method="DELETE",
            )
            with opener.open(reopen) as response:
                self.assertFalse(json.loads(response.read())["draining"])
            with request(port, body) as response:
                self.assertEqual(response.read(), success)

        status = self.p.runtime_status()
        counters = cast("dict[str, int]", status["counters"])
        self.assertEqual(counters["responses_rejected_while_draining"], 1)
        self.assertFalse(status["draining"])

    def test_drain_lease_expires_without_a_controller_rollback_request(self):
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        with mock.patch.object(
            admission.time, "monotonic", side_effect=[10.0, 10.0, 12.1, 12.1, 12.1]
        ):
            started = admission.set_draining(True, lease_seconds=2)
            expired = self.p.runtime_status()
        self.assertTrue(started["draining"])
        self.assertFalse(expired["draining"])
        self.assertIsNone(expired["drain_lease_remaining_seconds"])
        counters = cast("dict[str, int]", expired["counters"])
        self.assertEqual(counters["drain_leases_expired"], 1)

    def test_drain_closes_admission_while_an_existing_response_finishes(self):
        success = b'{"id":"resp_served","status":"completed"}'
        body = json.dumps({"stream": False, "input": []}).encode()
        started = threading.Event()
        release = threading.Event()
        worker_result = {}

        scripted = {
            "status": 200,
            "content_type": "application/json",
            "chunks": [success],
            "started_event": started,
            "release_event": release,
        }
        with running_proxy([scripted]) as (port, received):

            def request_in_flight():
                try:
                    with request(port, body) as response:
                        worker_result["body"] = response.read()
                except BaseException as exc:  # asserted below; never hide a worker failure
                    worker_result["error"] = exc

            worker = threading.Thread(target=request_in_flight)
            worker.start()
            try:
                self.assertTrue(
                    started.wait(timeout=2), "upstream never received the first Responses request"
                )

                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                drain = urllib.request.Request(
                    f"http://127.0.0.1:{port}/control/drain",
                    method="POST",
                )
                with opener.open(drain) as response:
                    snapshot = json.loads(response.read())
                self.assertTrue(snapshot["draining"])
                self.assertEqual(snapshot["active_responses"], 1)

                with self.assertRaises(urllib.error.HTTPError) as raised:
                    request(port, body)
                with raised.exception:
                    self.assertEqual(raised.exception.code, 503)
                    self.assertEqual(
                        json.loads(raised.exception.read())["error"]["code"], "proxy_draining"
                    )
                self.assertEqual(json.loads(received[0]), {**json.loads(body), "store": False})

                release.set()
                worker.join(timeout=3)
                self.assertFalse(
                    worker.is_alive(), "in-flight request did not complete after drain"
                )
                self.assertNotIn("error", worker_result)
                self.assertEqual(worker_result["body"], success)

                with opener.open(f"http://127.0.0.1:{port}/healthz") as response:
                    drained = json.loads(response.read())
                self.assertTrue(drained["draining"])
                self.assertEqual(drained["active_responses"], 0)
            finally:
                release.set()

    def test_reconnects_a_pre_content_response_failed_stream(self):
        failed = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.failed"}\n\n',
            ],
        }
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"recovered"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        with mock.patch.object(upstream_exchange.time, "sleep", return_value=None):
            received, payload = self.exchange([failed, recovered], body)

        self.assertEqual(len(received), 2)
        self.assertIn(b"recovered", payload)
        self.assertEqual(payload.count(b"response.created"), 1)
        status = self.p.runtime_status()
        counters = cast("dict[str, int]", status["counters"])
        self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 1)
        self.assertEqual(counters["streams_completed"], 1)

    def test_normalizes_exhausted_pre_content_sse_failures_to_retryable_503(self):
        premature_eof = {"chunks": [b'data: {"type":"response.created"}\n\n']}
        body = json.dumps({"stream": True, "input": []}).encode()

        with (
            running_proxy([premature_eof] * 6) as (port, received),
            mock.patch.object(upstream_exchange.time, "sleep", return_value=None),
        ):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            error = raised.exception
            with error:
                self.assertEqual(error.code, 503)
                self.assertEqual(error.headers["Retry-After"], "3")
                payload = json.loads(error.read())

        self.assertEqual(len(set(received)), 1)
        self.assertEqual(json.loads(received[0]), {**json.loads(body), "store": False})
        self.assertEqual(payload["error"]["type"], "upstream_unavailable")
        self.assertEqual(payload["error"]["code"], "stream_pre_content_exhausted")
        self.assertEqual(payload["error"]["attempts"], 6)
        status = self.p.runtime_status()
        counters = cast("dict[str, int]", status["counters"])
        last_failure = cast("dict[str, object]", status["last_failure"])
        self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 5)
        self.assertEqual(counters["streams_pre_content_exhausted"], 1)
        self.assertEqual(counters["streams_failed"], 1)
        self.assertEqual(last_failure["classification"], "stream_pre_content_exhausted")

    def test_reconnects_a_pre_content_premature_eof(self):
        premature_eof = {"chunks": [b'data: {"type":"response.created"}\n\n']}
        recovered = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
                b'data: {"type":"response.completed"}\n\n',
            ],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        with mock.patch.object(upstream_exchange.time, "sleep", return_value=None):
            received, payload = self.exchange([premature_eof, recovered], body)

        self.assertEqual(len(received), 2)
        self.assertIn(b'"delta":"ok"', payload)
        counters = cast("dict[str, int]", self.p.runtime_status()["counters"])
        self.assertEqual(
            counters["streams_pre_content_reconnect_attempts"],
            1,
        )

    def test_does_not_reconnect_after_downstream_stream_bytes_are_committed(self):
        partial = {
            "chunks": [
                b'data: {"type":"response.created"}\n\n',
                b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
            ],
        }
        unexpected_retry = {
            "chunks": [b'data: {"type":"response.completed"}\n\n'],
        }
        body = json.dumps({"stream": True, "input": []}).encode()

        received, payload = self.exchange([partial, unexpected_retry], body)

        self.assertEqual(len(received), 1)
        self.assertIn(b"partial", payload)
        status = self.p.runtime_status()
        counters = cast("dict[str, int]", status["counters"])
        self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 0)
        self.assertEqual(counters["streams_failed"], 1)

    def test_normalizes_exhausted_classified_empty_response_to_retryable_503(self):
        empty_response = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        body = json.dumps(
            {
                "model": "gpt-5.6-terra",
                "stream": False,
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            },
            separators=(",", ":"),
        ).encode()

        with (
            running_proxy([(477, empty_response)] * 4) as (port, received),
            mock.patch.object(upstream_exchange.time, "sleep", return_value=None),
        ):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            error = raised.exception
            with error:
                self.assertEqual(error.code, 503)
                self.assertEqual(error.headers["Retry-After"], "3")
                payload = json.loads(error.read())

        self.assertEqual(received[0], received[1])
        self.assertEqual(json.loads(received[0]), {**json.loads(body), "store": False})
        self.assertEqual(payload["error"]["type"], "upstream_unavailable")
        self.assertEqual(payload["error"]["code"], "dmx_empty_response_exhausted")
        self.assertEqual(payload["error"]["attempts"], 2)

    def test_drops_unreplayable_images_and_keeps_text_and_https(self):
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "custom_tool_call",
                        "call_id": "image-call",
                        "name": "inspect",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "image-call",
                        "output": [
                            {"type": "input_text", "text": "before"},
                            {"type": "input_image", "image_url": "/tmp/example.png"},
                            {"type": "input_text", "text": "after"},
                        ],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": "https://example.test/valid.png"},
                            {
                                "type": "input_image",
                                "image_url": "data:image/png;base64,not-supported",
                            },
                        ],
                    },
                ]
            }
        ).encode()

        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        note = _projection.diagnostic()
        obj = json.loads(cast("bytes", out))

        self.assertIn("local_image_items=2", note)
        self.assertEqual(
            obj["input"][1]["output"],
            [
                {"type": "input_text", "text": "before"},
                {"type": "input_text", "text": "after"},
            ],
        )
        self.assertEqual(
            obj["input"][2]["content"],
            [{"type": "input_image", "image_url": "https://example.test/valid.png"}],
        )

    def test_drops_malformed_http_like_image_urls(self):
        bad_urls = [
            "https://",
            "https://bad host/example.png",
            "http:///missing-host",
            "https://example.test:not-a-port/image.png",
            "https://example.test/has space.png",
        ]
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "custom_tool_call",
                        "call_id": "image-call",
                        "name": "inspect",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "image-call",
                        "output": [{"type": "input_image", "image_url": url} for url in bad_urls]
                        + [
                            {"type": "input_image", "image_url": "https://example.test/valid.png"},
                        ],
                    },
                ],
            }
        ).encode()

        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        note = _projection.diagnostic()
        obj = json.loads(cast("bytes", out))

        self.assertIn(f"local_image_items={len(bad_urls)}", note)
        self.assertEqual(
            obj["input"][1]["output"],
            [{"type": "input_image", "image_url": "https://example.test/valid.png"}],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
