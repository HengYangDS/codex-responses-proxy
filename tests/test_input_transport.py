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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import entrypoint as proxy
from codex_dmx_proxy.listener import responses
from codex_dmx_proxy.listener import rewrite
from codex_dmx_proxy.listener import state
from codex_dmx_proxy.listener import sse
from tests.support.proxy_http import request, running_proxy


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

    def __init__(self, body: bytes = b"", *, path: str = "/v1/responses") -> None:
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
        old_log_path = state.LOG_PATH
        self._log_directory = tempfile.TemporaryDirectory()
        state.LOG_PATH = str(Path(self._log_directory.name) / "proxy.log")
        self.addCleanup(self._log_directory.cleanup)
        self.addCleanup(setattr, state, "LOG_PATH", old_log_path)
        state.reset_for_test()

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
        self.assertEqual(json.loads(received[0]), json.loads(body))
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
            logs = Path(state.LOG_PATH).read_text(encoding="utf-8")

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
        expected = json.loads(cast("bytes", rewrite.sanitize_responses_body(body)[0]))
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
                "empty_response",
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
                state.reset_for_test()
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
                self.assertEqual(counters["empty_response_fallback_attempts"], 0)
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
            real_urlopen = responses.urlopen_direct
            calls = 0

            def fail_second(outbound: urllib.request.Request, timeout: float):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise transport_error
                return real_urlopen(outbound, timeout)

            with mock.patch.object(responses, "urlopen_direct", side_effect=fail_second):
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
            logs = Path(state.LOG_PATH).read_text(encoding="utf-8")

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
            logs = Path(state.LOG_PATH).read_text(encoding="utf-8")

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
            state.reset_for_test()
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

        state.reset_for_test()
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
        with mock.patch.object(state, "admit_response", return_value=("timeout", 0)):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"timed out waiting", handler.output())

        state.reset_for_test()
        handler = _MemoryHandler(path="/v1/health")
        with mock.patch.object(responses, "urlopen_direct", side_effect=OSError("private")):
            responses.relay(handler, "GET")
        self.assertEqual(handler.statuses, [502])
        self.assertIn(b"upstream_transport_error", handler.output())

    def test_direct_relay_covers_retry_and_fallback_transport_failure(self) -> None:
        transient = _http_error(503, "failure", b"temporary")
        success = _DirectResponse(b"ok")
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        with (
            mock.patch.object(responses, "urlopen_direct", side_effect=[transient, success]),
            mock.patch.object(responses.time, "sleep", return_value=None),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [200])
        self.assertIn(b"ok", handler.output())

        empty = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        fallback_error = OSError("private")
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream_error = _http_error(477, "empty", empty)
        with mock.patch.object(
            responses, "urlopen_direct", side_effect=[upstream_error, fallback_error]
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"dmx_empty_response_exhausted", handler.output())

    def test_direct_relay_handles_large_request_cooldown_and_dead_loop(self) -> None:
        body = json.dumps({"input": "x" * 400_000}).encode()
        handler = _MemoryHandler(body)
        with mock.patch.object(responses, "urlopen_direct", return_value=_DirectResponse(b"ok")):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [200])

        state.reset_for_test()
        body = json.dumps({"input": []}).encode()
        handler = _MemoryHandler(body)
        with mock.patch.object(state, "empty_response_cooldown_remaining", return_value=1.0):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"dmx_empty_response_exhausted", handler.output())

        state.reset_for_test()
        handler = _MemoryHandler(body)
        with (
            mock.patch.object(responses, "INPUT_VARIANT_DIALOGUE_SLOTS", -4),
            mock.patch.object(responses.response_failed, "DIALOGUE_SLOTS", 0),
            mock.patch.object(responses.response_failed, "MAX_STAGES", 0),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [502])
        self.assertIn(b"upstream_transport_error", handler.output())

    def test_direct_relay_rejects_unsafe_empty_response_projection(self) -> None:
        empty = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream_error = _http_error(477, "empty", empty)
        with (
            mock.patch.object(responses, "urlopen_direct", side_effect=upstream_error),
            mock.patch.object(
                responses.empty_response,
                "build_fallback",
                return_value=(None, {"reason": "unsafe"}),
            ),
            mock.patch.object(
                responses.empty_response, "recover_dialogue", return_value=(None, {})
            ),
        ):
            responses.relay(handler, "POST")
        self.assertEqual(handler.statuses, [503])
        self.assertIn(b"dmx_empty_response_exhausted", handler.output())

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
        handler = _MemoryHandler(path="/v1/health")
        with mock.patch.object(responses, "urlopen_direct", return_value=_DirectResponse(partial)):
            responses.relay(handler, "GET")
        self.assertEqual(handler.statuses, [200])
        self.assertIn(b"partial", handler.output())

        statuses = []
        for error in (BrokenPipeError(), RuntimeError("private")):
            handler = _MemoryHandler(path="/v1/health")
            handler.wfile = mock.Mock()
            handler.wfile.write.side_effect = error
            with mock.patch.object(
                responses, "urlopen_direct", return_value=_DirectResponse(b"body")
            ):
                responses.relay(handler, "GET")
            statuses.append(handler.statuses)
        self.assertEqual(statuses, [[200], [200]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
