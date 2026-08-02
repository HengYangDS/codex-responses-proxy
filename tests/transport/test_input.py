#!/usr/bin/env python3
"""HTTP orchestration contracts for exact Responses input recovery."""

from __future__ import annotations

import http.client
import io
import json
from email.message import Message
from http.server import BaseHTTPRequestHandler
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from codex_responses_proxy.listener import entrypoint as proxy
from codex_responses_proxy.transport import exchange as upstream_exchange
from codex_responses_proxy.transport import responses
from codex_responses_proxy.replay import request as rewrite
from codex_responses_proxy.runtime import admission, logging, telemetry
from codex_responses_proxy.transport import cooldown
from codex_responses_proxy.transport import relay as downstream
from codex_responses_proxy.transport import sse
from tests.listener.proxy_fixture import request, running_proxy


EXACT_ERROR = json.dumps(
    {
        "error": {
            "message": (
                "invalid request body: Invalid 'input': value did not match any expected variant"
            ),
            "type": "invalid_request_error",
            "param": "",
            "code": "validation_error",
        }
    },
    separators=(",", ":"),
).encode()


def _request_body(*, stream: bool = False, secret: str = "private-current-prompt") -> bytes:
    return json.dumps(
        {
            "model": "gpt-5.6-terra",
            "stream": stream,
            "instructions": "top-level-current-policy",
            "previous_response_id": "stale-response-binding",
            "conversation": {"id": "stale-conversation-binding"},
            "prompt_cache_key": "stale-private-cache-key",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": secret},
                {
                    "type": "custom_tool_call",
                    "call_id": "stale-call",
                    "name": "exec",
                    "input": "{}",
                },
            ],
        },
        separators=(",", ":"),
    ).encode()


class _MemoryHandler(BaseHTTPRequestHandler):
    """Small handler surface for direct transport branch contracts."""

    def __init__(self, body: bytes = b"", *, path: str = "/dmxapi/v1/responses") -> None:
        self.path = path
        self.headers = Message()
        self.headers["Content-Length"] = str(len(body))
        self.headers["Connection"] = "close"
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.statuses: list[int] = []
        self.sent_headers: list[tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:
        del message
        self.statuses.append(code)

    def send_header(self, keyword: str, value: str) -> None:
        self.sent_headers.append((keyword, value))

    def end_headers(self) -> None:
        pass

    def output(self) -> bytes:
        """Return the bytes written through the in-memory response stream."""
        return cast("io.BytesIO", self.wfile).getvalue()


def _http_error(code: int, message: str, body: bytes) -> urllib.error.HTTPError:
    """Return an HTTP error with the stdlib header contract."""
    return urllib.error.HTTPError(
        "https://upstream.test/v1/responses", code, message, Message(), io.BytesIO(body)
    )


class _DirectResponse:
    """Scripted response supporting normal reads and read exceptions."""

    def __init__(
        self,
        *reads: bytes | BaseException,
        content_type: str = "application/json",
        status: int = 200,
        fp: object | None = None,
    ) -> None:
        self._reads = list(reads)
        self.headers = {"Content-Type": content_type, "Content-Length": "opaque"}
        self.status = status
        self.fp = fp if fp is not None else object()

    def read(self, amount: int = -1) -> bytes:
        del amount
        item = self._reads.pop(0) if self._reads else b""
        if isinstance(item, BaseException):
            raise item
        return item


class InputTransportContracts(unittest.TestCase):
    """Exercise the recovery boundary through real loopback HTTP servers."""

    def setUp(self) -> None:
        old_log_path = logging.LOG_PATH
        self._log_directory = tempfile.TemporaryDirectory()
        logging.LOG_PATH = str(Path(self._log_directory.name) / "proxy.log")
        self.addCleanup(self._log_directory.cleanup)
        self.addCleanup(setattr, logging, "LOG_PATH", old_log_path)
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()

    @staticmethod
    def _status_snapshot() -> dict[str, object]:
        return proxy.runtime_status()

    @classmethod
    def _status_maps(cls) -> tuple[dict[str, int], dict[str, int]]:
        status = cls._status_snapshot()
        counters = cast("dict[str, int]", status["counters"])
        classifications = cast("dict[str, int]", status["upstream_classifications"])
        return counters, classifications

    def test_exact_error_recovers_once_with_fresh_content_length(self) -> None:
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = _request_body()
        with running_proxy([(400, EXACT_ERROR), (200, success)]) as (port, received):
            with request(port, body) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 2)
        recovery = received[1]
        self.assertLess(len(recovery), len(body))
        recovered = json.loads(recovery)
        self.assertIs(recovered["store"], False)
        self.assertEqual(recovered["instructions"], "top-level-current-policy")
        self.assertNotIn("previous_response_id", recovered)
        self.assertNotIn("conversation", recovered)
        self.assertNotIn("prompt_cache_key", recovered)
        self.assertEqual(recovered["include"], ["other"])
        self.assertEqual(
            recovered["input"],
            [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "private-current-prompt"},
            ],
        )
        status = self._status_snapshot()
        counters = cast("dict[str, int]", status["counters"])
        classifications = cast("dict[str, int]", status["upstream_classifications"])
        self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_accepted"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_exhausted"], 0)
        self.assertEqual(classifications, {"input_variant_validation_error": 1})
        public_status = json.dumps(status, sort_keys=True)
        self.assertNotRegex(
            public_status,
            "private-current-prompt|top-level-current-policy|stale-response-binding|"
            "stale-conversation-binding|stale-private-cache-key",
        )
        self.assertIn("release", status)
        self.assertIn("serving_payload_sha256", status)
        self.assertIn("release_receipt_sha256", status)

    def test_exact_error_without_a_strictly_smaller_recovery_is_passed_through(self) -> None:
        body = json.dumps(
            {"input": [{"type": "message", "role": "user", "content": "current"}]},
            separators=(",", ":"),
        ).encode()
        with running_proxy([(400, EXACT_ERROR)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.exception as error:
                self.assertEqual(error.code, 400)
                self.assertEqual(error.read(), EXACT_ERROR)

        self.assertEqual(len(received), 1)
        self.assertEqual(
            json.loads(received[0]),
            {**json.loads(body), "store": False},
        )
        counters, classifications = self._status_maps()
        self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 0)
        self.assertEqual(counters["response_failed_compaction_attempts"], 0)
        self.assertEqual(counters["response_failed_dialogue_recovery_attempts"], 0)
        self.assertEqual(classifications, {"input_variant_validation_error": 1})

    def test_top_level_error_metadata_still_admits_the_exact_contract(self) -> None:
        exact_with_metadata = json.loads(EXACT_ERROR)
        exact_with_metadata.update(
            {
                "request_id": "opaque-upstream-request-id",
                "provider": "opaque-envelope-metadata",
            }
        )
        response_body = json.dumps(exact_with_metadata, separators=(",", ":")).encode()
        success = b'{"id":"resp_recovered","status":"completed"}'
        body = _request_body()
        with running_proxy([(400, response_body), (200, success)]) as (port, received):
            with request(port, body) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), success)
            logs = Path(logging.LOG_PATH).read_text(encoding="utf-8")

        self.assertEqual(len(received), 2)
        self.assertNotIn("opaque-upstream-request-id", logs)
        self.assertNotIn("opaque-envelope-metadata", logs)
        counters, classifications = self._status_maps()
        self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_accepted"], 1)
        self.assertEqual(classifications, {"input_variant_validation_error": 1})

    def test_unknown_validation_error_is_passed_through_without_retry(self) -> None:
        unknown = json.dumps(
            {
                "error": {
                    "message": "invalid request body: another schema contract",
                    "type": "invalid_request_error",
                    "param": "input",
                    "code": "validation_error",
                }
            },
            separators=(",", ":"),
        ).encode()
        body = _request_body()
        with running_proxy([(400, unknown)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.exception as error:
                self.assertEqual(error.code, 400)
                self.assertEqual(error.headers["Content-Length"], str(len(unknown)))
                self.assertEqual(error.read(), unknown)

        self.assertEqual(len(received), 1)
        forwarded = json.loads(received[0])
        expected = json.loads(cast("bytes", rewrite.sanitize_responses_body(body).body))
        self.assertEqual(forwarded, expected)
        counters, classifications = self._status_maps()
        self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 0)
        self.assertEqual(classifications, {"http_400": 1})

    def test_recovery_second_http_error_is_terminal_without_other_recovery(self) -> None:
        terminal_errors = {
            "classified-477": (
                477,
                b'{"error":{"message":"official provider returned an empty response",'
                b'"type":"dmx_api_error","code":"empty_response"}}',
                "wire_policy_failure",
            ),
            "response-failed": (
                400,
                b'{"error":{"message":"OpenAI responses stream failed: response_failed",'
                b'"type":"new_api_error","code":"response_failed"}}',
                "response_failed",
            ),
            "ordinary-retry": (
                503,
                b'{"error":{"message":"temporary outage","code":"upstream_failure"}}',
                "http_503_full",
            ),
            "same-exact-error": (400, EXACT_ERROR, "input_variant_validation_error"),
        }
        for label, (status_code, terminal_body, classification) in terminal_errors.items():
            with self.subTest(label=label):
                admission.reset_for_test()
                telemetry.reset_for_test()
                cooldown.reset_for_test()
                body = _request_body()
                with running_proxy([(400, EXACT_ERROR), (status_code, terminal_body)]) as (
                    port,
                    received,
                ):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        request(port, body)
                    with raised.exception as error:
                        self.assertEqual(error.code, status_code)
                        self.assertEqual(error.headers["Content-Length"], str(len(terminal_body)))
                        self.assertEqual(error.read(), terminal_body)

                self.assertEqual(len(received), 2)
                counters, classifications = self._status_maps()
                self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 1)
                self.assertEqual(counters["input_variant_dialogue_recovery_exhausted"], 1)
                self.assertEqual(counters["wire_failure_retry_attempts"], 0)
                self.assertEqual(counters["response_failed_compaction_attempts"], 0)
                self.assertEqual(counters["response_failed_dialogue_recovery_attempts"], 0)
                self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 0)
                expected_classifications = {classification: 1, "input_variant_validation_error": 1}
                expected_classifications[classification] += (
                    classification == "input_variant_validation_error"
                )
                self.assertEqual(classifications, expected_classifications)

    def test_recovery_transport_failure_is_terminal_without_normal_retry(self) -> None:
        body = _request_body()
        transport_error = urllib.error.URLError("private-upstream-detail")
        with running_proxy([(400, EXACT_ERROR)]) as (port, received):
            real_urlopen = upstream_exchange.urlopen_direct
            calls = 0

            def fail_second(outbound: urllib.request.Request, timeout: float):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise transport_error
                return real_urlopen(outbound, timeout)

            with mock.patch.object(upstream_exchange, "urlopen_direct", side_effect=fail_second):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    request(port, body)
            with raised.exception as error:
                payload = json.loads(error.read())
                self.assertEqual(error.code, 502)
                self.assertEqual(
                    error.headers["Content-Length"],
                    str(len(json.dumps(payload, separators=(",", ":")).encode())),
                )
                self.assertEqual(payload["error"]["code"], "input_variant_recovery_transport_error")
            logs = Path(logging.LOG_PATH).read_text(encoding="utf-8")

        self.assertEqual(calls, 2)
        self.assertEqual(len(received), 1)
        self.assertNotIn("private-upstream-detail", logs)
        self.assertNotIn("private-current-prompt", logs)
        self.assertNotIn("stale-private-cache-key", logs)
        self.assertIn("exception=URLError", logs)
        self.assertNotIn("event=upstream_transport_retry", logs)
        counters, _classifications = self._status_maps()
        self.assertEqual(counters["input_variant_dialogue_recovery_exhausted"], 1)

    def test_recovered_sse_failure_does_not_reconnect(self) -> None:
        body = _request_body(stream=True)
        incomplete = b'data: {"type":"response.created"}\n\n'
        unexpected_reconnect = b'data: {"type":"response.completed"}\n\n'
        with running_proxy(
            [
                (400, EXACT_ERROR),
                {"status": 200, "payload": incomplete, "content_type": "text/event-stream"},
                {
                    "status": 200,
                    "payload": unexpected_reconnect,
                    "content_type": "text/event-stream",
                },
            ]
        ) as (port, received):
            with mock.patch.object(sse.time, "sleep", return_value=None):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    request(port, body)
            with raised.exception as error:
                payload = json.loads(error.read())
                self.assertEqual(error.code, 503)
                self.assertEqual(payload["error"]["code"], "stream_pre_content_exhausted")
                self.assertEqual(payload["error"]["attempts"], 1)

        self.assertEqual(len(received), 2)
        counters, _classifications = self._status_maps()
        self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 0)
        self.assertEqual(counters["input_variant_dialogue_recovery_exhausted"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_accepted"], 0)

    def test_recovered_sse_completes_once_without_reconnect(self) -> None:
        body = _request_body(stream=True)
        completed = (
            b'data: {"type":"response.created"}\n\n'
            b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
            b'data: {"type":"response.completed"}\n\n'
        )
        with running_proxy(
            [
                (400, EXACT_ERROR),
                {
                    "status": 200,
                    "chunks": [completed],
                    "content_type": "text/event-stream",
                },
            ]
        ) as (port, received):
            with request(port, body) as response:
                self.assertEqual(response.status, 200)
                downstream = response.read()
            logs = Path(logging.LOG_PATH).read_text(encoding="utf-8")

        self.assertEqual(len(received), 2)
        self.assertEqual(downstream.count(b'"type":"response.created"'), 1)
        self.assertEqual(downstream.count(b'"type":"response.output_text.delta"'), 1)
        self.assertEqual(downstream.count(b'"type":"response.completed"'), 1)
        self.assertNotIn("private-current-prompt", logs)
        self.assertNotIn("stale-conversation-binding", logs)
        counters, classifications = self._status_maps()
        self.assertEqual(counters["streams_pre_content_reconnect_attempts"], 0)
        self.assertEqual(counters["input_variant_dialogue_recovery_attempts"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_accepted"], 1)
        self.assertEqual(counters["input_variant_dialogue_recovery_exhausted"], 0)
        self.assertEqual(classifications, {"input_variant_validation_error": 1})

    def test_direct_sse_reader_covers_sanitization_and_failure_details(self) -> None:
        encrypted = (
            b'data: {"type":"response.output_item.added","item":'
            b'{"type":"reasoning","encrypted_content":"secret"}}\n\n'
        )
        cases = (
            (
                _DirectResponse(
                    http.client.IncompleteRead(b'data: {"type": "response.incomplete"}')
                ),
                "response.incomplete",
                "incomplete",
                object,
            ),
            (
                _DirectResponse(socket.timeout("private")),
                None,
                "timeout",
                socket.timeout,
            ),
            (_DirectResponse(RuntimeError("private")), None, "eof", RuntimeError),
            (_DirectResponse(encrypted), None, "eof", object),
        )
        results = []
        for upstream, terminal, detail, error_type in cases:
            admission.reset_for_test()
            telemetry.reset_for_test()
            cooldown.reset_for_test()
            handler = _MemoryHandler()
            result = sse._read_one_stream(handler, upstream, "/v1/responses", 1, lambda: None)
            results.append(
                (
                    result["terminal"],
                    result["detail"],
                    isinstance(result["error"], error_type),
                )
            )
        self.assertEqual(results, [(terminal, detail, True) for _, terminal, detail, _ in cases])
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        self.assertEqual(counters["encrypted_sse_keys_stripped"], 1)
        self.assertNotIn(b"secret", handler.output())

    def test_direct_sse_relay_handles_reopen_failure_and_incomplete_terminal(self) -> None:
        failed = _DirectResponse(b'data: {"type":"response.failed"}\n\n')
        handler = _MemoryHandler()
        with mock.patch.object(sse.time, "sleep", return_value=None):
            result = sse.relay(
                handler,
                failed,
                "/v1/responses",
                1,
                reopen=mock.Mock(side_effect=OSError("private")),
            )
        self.assertTrue(result["pre_content_exhausted"])
        self.assertEqual(result["attempts"], 1)

        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        handler = _MemoryHandler()
        result = sse.relay(
            handler,
            _DirectResponse(b'data: {"type": "response.incomplete"}\n\n'),
            "/v1/responses",
            2,
            send_headers=lambda: None,
        )
        self.assertFalse(result["pre_content_exhausted"])
        self.assertTrue(handler.output().endswith(b"0\r\n\r\n"))
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        self.assertEqual(counters["streams_incomplete"], 1)

    def test_direct_relay_covers_queue_timeout_and_transport_exhaustion(self) -> None:
        body = json.dumps({"input": []}).encode()
        handler = _MemoryHandler(body)
        with mock.patch.object(admission, "admit_response", return_value=("timeout", 0)):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"timed out waiting", handler.output())

        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        handler = _MemoryHandler(path="/dmxapi/v1/responses")
        with mock.patch.object(upstream_exchange, "urlopen_direct", side_effect=OSError("private")):
            responses.relay(handler, "GET")
        self.assertEqual(handler.statuses, [502])
        self.assertIn(b"upstream_transport_error", handler.output())

    def test_direct_relay_covers_retry_and_fallback_transport_failure(self) -> None:
        transient = _http_error(503, "failure", b"temporary")
        success = _DirectResponse(b'{"id":"resp_ok","status":"completed"}')
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        with (
            mock.patch.object(
                upstream_exchange, "urlopen_direct", side_effect=[transient, success]
            ),
            mock.patch.object(upstream_exchange.time, "sleep", return_value=None),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [200])
        self.assertIn(b"resp_ok", handler.output())

        empty = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        fallback_error = OSError("private")
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream_error = _http_error(477, "empty", empty)
        with mock.patch.object(
            upstream_exchange, "urlopen_direct", side_effect=[upstream_error, fallback_error]
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"dmx_empty_response_exhausted", handler.output())

    def test_rate_limit_is_relayed_after_one_upstream_attempt_without_sleep(self) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        headers = Message()
        headers["Content-Type"] = "application/json; charset=utf-8"
        headers["Retry-After"] = "7"
        headers["X-Request-Id"] = "rate-limit-request"

        def rate_limited(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://upstream.test/v1/responses",
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(payload),
            )

        handler = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        with (
            mock.patch.object(
                upstream_exchange, "urlopen_direct", side_effect=rate_limited
            ) as open_,
            mock.patch.object(upstream_exchange.time, "sleep", return_value=None) as sleep,
        ):
            responses.relay(handler, "POST")

        self.assertEqual(open_.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(handler.statuses, [429])
        self.assertEqual(handler.output(), payload)
        self.assertIn(("Retry-After", "7"), handler.sent_headers)
        self.assertIn(("X-Request-Id", "rate-limit-request"), handler.sent_headers)

    def test_rate_limit_bypasses_even_a_broad_provider_wire_retry_policy(self) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Retry-After"] = "7"
        policy = mock.Mock()
        policy.request_fingerprint.return_value = "test-wire-fingerprint"
        policy.is_retryable_failure.return_value = True
        policy.POLICY_VERSION = "test-wire-policy"
        profiles = dict(responses.PROVIDERS.profiles)
        current = profiles["ucloud"]
        profiles["ucloud"] = type(current)(current.name, current.base_url, policy)
        registry = type(responses.PROVIDERS)(profiles)

        def rate_limited(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://upstream.test/v1/responses",
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(payload),
            )

        handler = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        with (
            mock.patch.object(responses, "PROVIDERS", registry),
            mock.patch.object(
                upstream_exchange, "urlopen_direct", side_effect=rate_limited
            ) as open_,
            mock.patch.object(upstream_exchange.time, "sleep", return_value=None) as sleep,
        ):
            responses.relay(handler, "POST")

        self.assertEqual(open_.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(handler.statuses, [429])
        self.assertEqual(handler.output(), payload)

    def test_rate_limit_cooldown_is_provider_scoped_and_skips_upstream(self) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        first = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        second = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        other = _MemoryHandler(json.dumps({"input": []}).encode(), path="/aihubmix/v1/responses")

        with mock.patch.object(
            upstream_exchange,
            "urlopen_direct",
            side_effect=[
                _http_error(429, "Too Many Requests", payload),
                _DirectResponse(b'{"id":"resp_other","status":"completed"}'),
            ],
        ) as open_:
            responses.relay(first, "POST")
            responses.relay(second, "POST")
            responses.relay(other, "POST")

        self.assertEqual(open_.call_count, 2)
        self.assertEqual(first.statuses, [429])
        self.assertEqual(second.statuses, [429])
        self.assertIn(b"provider_rate_limit_cooldown", second.output())
        self.assertIn(("Retry-After", "5"), second.sent_headers)
        self.assertEqual(other.statuses, [200])
        self.assertEqual(other.output(), b'{"id":"resp_other","status":"completed"}')

    def test_rate_limit_cooldown_rejects_before_global_admission(self) -> None:
        cooldown.remember_failure(
            cooldown.provider_key("ucloud"),
            cooldown_seconds=5,
        )
        handler = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        with (
            mock.patch.object(admission, "admit_response") as admit,
            mock.patch.object(upstream_exchange, "urlopen_direct") as open_,
        ):
            responses.relay(handler, "POST")

        admit.assert_not_called()
        open_.assert_not_called()
        self.assertEqual(handler.statuses, [429])
        self.assertIn(b"provider_rate_limit_cooldown", handler.output())

    def test_direct_relay_handles_large_request_cooldown_and_dead_loop(self) -> None:
        body = json.dumps({"input": "x" * 400_000}).encode()
        handler = _MemoryHandler(body)
        with mock.patch.object(
            upstream_exchange,
            "urlopen_direct",
            return_value=_DirectResponse(b'{"id":"resp_large","status":"completed"}'),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [200])

        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        body = json.dumps({"input": []}).encode()
        handler = _MemoryHandler(body)
        with mock.patch.object(cooldown, "remaining", return_value=1.0):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"dmx_empty_response_exhausted", handler.output())

        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        handler = _MemoryHandler(body)
        with (
            mock.patch.object(upstream_exchange, "INPUT_VARIANT_DIALOGUE_SLOTS", -4),
            mock.patch.object(upstream_exchange.response_failed, "DIALOGUE_SLOTS", 0),
            mock.patch.object(upstream_exchange.response_failed, "MAX_STAGES", 0),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [502])
        self.assertIn(b"upstream_transport_error", handler.output())

    def test_direct_transport_terminal_branches_emit_bounded_results(self) -> None:
        handler = _MemoryHandler()
        exchange = mock.Mock(
            handler=handler,
            is_responses=True,
            used_input_variant_dialogue=False,
        )
        exchange.profile.wire_policy = None

        with self.assertRaisesRegex(RuntimeError, "wire recovery requires a provider policy"):
            upstream_exchange._reject_wire_failure(exchange, "fingerprint", 2, "event", "")
        self.assertFalse(upstream_exchange._retry_wire_failure(exchange))

        outcome = upstream_exchange._transport_error(exchange, OSError("private"), 3)
        self.assertEqual(outcome, "terminal")
        self.assertEqual(handler.statuses, [502])
        self.assertIn(b"upstream_transport_error", handler.output())

    def test_direct_non_responses_body_covers_empty_and_terminal_chunks(self) -> None:
        handler = _MemoryHandler(path="/dmxapi/v1/health")
        exchange = mock.Mock(handler=handler, is_responses=True)
        exchange.input_variant_accepted = mock.Mock()
        downstream.relay_body(exchange, _DirectResponse(b"", b""))
        self.assertEqual(handler.statuses, [200])
        self.assertEqual(handler.output(), b"0\r\n\r\n")
        exchange.input_variant_accepted.assert_called_once_with()

        admission.reset_for_test()
        telemetry.reset_for_test()
        handler = _MemoryHandler(path="/dmxapi/v1/health")
        exchange = mock.Mock(handler=handler, is_responses=True)
        exchange.input_variant_accepted = mock.Mock()
        downstream.relay_body(
            exchange,
            _DirectResponse(b"partial", http.client.IncompleteRead(b"terminal")),
        )
        self.assertIn(b"partial", handler.output())
        self.assertIn(b"terminal", handler.output())
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        self.assertEqual(counters["responses_completed"], 1)
        exchange.input_variant_accepted.assert_called_once_with()

    def test_direct_sse_relay_flushes_completed_prelude(self) -> None:
        handler = _MemoryHandler()
        sent = 0

        def mark_headers() -> None:
            nonlocal sent
            sent += 1

        result = sse.relay(
            handler,
            _DirectResponse(
                b'data: {"type":"response.created"}\n\ndata: {"type":"response.completed"}\n\n'
            ),
            "/v1/responses",
            1,
            send_headers=mark_headers,
        )
        self.assertFalse(result["pre_content_exhausted"])
        self.assertEqual(sent, 1)
        self.assertEqual(handler.output().count(b"response.completed"), 1)

    def test_direct_non_sse_stream_handles_incomplete_and_writer_failures(self) -> None:
        partial = http.client.IncompleteRead(b"partial")
        handler = _MemoryHandler(path="/dmxapi/v1/responses")
        with mock.patch.object(
            upstream_exchange, "urlopen_direct", return_value=_DirectResponse(partial)
        ):
            responses.relay(handler, "GET")
        self.assertEqual(handler.statuses, [200])
        self.assertIn(b"partial", handler.output())

        statuses = []
        for error in (BrokenPipeError(), RuntimeError("private")):
            handler = _MemoryHandler(path="/dmxapi/v1/responses")
            handler.wfile = mock.Mock()
            handler.wfile.write.side_effect = error
            with mock.patch.object(
                upstream_exchange, "urlopen_direct", return_value=_DirectResponse(b"body")
            ):
                responses.relay(handler, "GET")
            statuses.append(handler.statuses)
        self.assertEqual(statuses, [[200], [200]])

    def test_non_stream_responses_strip_ciphertext_before_downstream_commit(self) -> None:
        upstream = json.dumps(
            {
                "id": "resp_provider_bound",
                "status": "completed",
                "output": [
                    {"type": "reasoning", "encrypted_content": "reasoning-secret"},
                    {
                        "type": "agent_message",
                        "content": [
                            {"type": "encrypted_content", "encrypted_content": "agent-secret"},
                            {"type": "output_text", "text": "visible"},
                        ],
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        with mock.patch.object(
            upstream_exchange, "urlopen_direct", return_value=_DirectResponse(upstream)
        ):
            responses.relay(handler, "POST")

        self.assertEqual(handler.statuses, [200])
        self.assertNotIn(b"secret", handler.output())
        self.assertIn(b"visible", handler.output())

    def test_empty_responses_request_fails_before_upstream_io(self) -> None:
        handler = _MemoryHandler(b"")

        with mock.patch.object(upstream_exchange, "urlopen_direct") as opened:
            responses.relay(handler, "POST")

        self.assertEqual(handler.statuses, [400])
        self.assertIn(b"provider_portable_projection_rejected", handler.output())
        opened.assert_not_called()

    def test_invalid_successful_responses_fail_before_downstream_commit(self) -> None:
        invalid = (
            _DirectResponse(b""),
            _DirectResponse(http.client.IncompleteRead(b'{"status":"completed"')),
            _DirectResponse(b"not-json"),
            _DirectResponse(b'{"id":"resp","status":"in_progress","output":[]}'),
        )
        for upstream in invalid:
            with self.subTest(upstream=upstream):
                admission.reset_for_test()
                handler = _MemoryHandler(json.dumps({"input": []}).encode())
                with mock.patch.object(upstream_exchange, "urlopen_direct", return_value=upstream):
                    responses.relay(handler, "POST")
                self.assertEqual(handler.statuses, [503])
                self.assertIn(b"invalid_responses_success_body", handler.output())

    def test_oversized_successful_response_fails_before_downstream_commit(self) -> None:
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream = _DirectResponse(b'{"status":"completed","output":"', b"x" * 64, b'"}')

        with (
            mock.patch.object(upstream_exchange, "urlopen_direct", return_value=upstream),
            mock.patch.object(downstream, "MAX_RESPONSES_JSON_BYTES", 32),
        ):
            responses.relay(handler, "POST")

        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"response_too_large", handler.output())


if __name__ == "__main__":
    unittest.main(verbosity=2)
