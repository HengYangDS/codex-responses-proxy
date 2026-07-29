#!/usr/bin/env python3
"""HTTP orchestration contracts for exact Responses input recovery."""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TypedDict, cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proxy"))

import dmx_responses_proxy as proxy
import responses_transport
import runtime_state
import sse_transport


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


class _ScriptedResponse(TypedDict, total=False):
    """One typed upstream response used by the loopback fixture."""

    status: int
    payload: bytes
    content_type: str


type ScriptedResponse = tuple[int, bytes] | _ScriptedResponse


class _ReceivedRequest(TypedDict):
    """Request facts retained by the fixture without decoding caller content."""

    body: bytes
    content_length: str | None


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


class InputTransportContracts(unittest.TestCase):
    """Exercise the recovery boundary through real loopback HTTP servers."""

    def setUp(self) -> None:
        runtime_state.reset_for_test()

    @contextlib.contextmanager
    def _servers(
        self,
        scripted: list[ScriptedResponse],
        log_dir: Path,
    ) -> Iterator[tuple[int, list[_ReceivedRequest]]]:
        received: list[_ReceivedRequest] = []
        scripted_lock = threading.Lock()

        class UpstreamHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                del format, args

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request_body = self.rfile.read(length)
                received.append(
                    {
                        "body": request_body,
                        "content_length": self.headers.get("Content-Length"),
                    }
                )
                with scripted_lock:
                    response = scripted.pop(0)
                if isinstance(response, tuple):
                    status, payload = response
                    content_type = "application/json"
                else:
                    status = response.get("status", 200)
                    payload = response.get("payload", b"")
                    content_type = response.get("content_type", "application/json")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        old_upstream = responses_transport.UPSTREAM
        old_log_path = runtime_state.LOG_PATH
        responses_transport.UPSTREAM = f"http://127.0.0.1:{upstream.server_address[1]}"
        runtime_state.LOG_PATH = str(log_dir / "proxy.log")
        server = proxy.create_server(("127.0.0.1", 0))
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            yield server.server_address[1], received
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)
            responses_transport.UPSTREAM = old_upstream
            runtime_state.LOG_PATH = old_log_path

    @staticmethod
    def _request(port: int, body: bytes):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)

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
        with tempfile.TemporaryDirectory() as directory:
            with self._servers([(400, EXACT_ERROR), (200, success)], Path(directory)) as (
                port,
                received,
            ):
                response = self._request(port, body)
                with response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 2)
        recovery = received[1]["body"]
        self.assertLess(len(recovery), len(body))
        self.assertEqual(received[0]["content_length"], str(len(received[0]["body"])))
        self.assertEqual(received[1]["content_length"], str(len(recovery)))
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
        for private_value in (
            "private-current-prompt",
            "top-level-current-policy",
            "stale-response-binding",
            "stale-conversation-binding",
            "stale-private-cache-key",
        ):
            self.assertNotIn(private_value, public_status)
        self.assertIn("release", status)
        self.assertIn("serving_payload_sha256", status)
        self.assertIn("release_receipt_sha256", status)

    def test_exact_error_without_a_strictly_smaller_recovery_is_passed_through(self) -> None:
        body = json.dumps(
            {"input": [{"type": "message", "role": "user", "content": "current"}]},
            separators=(",", ":"),
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            with self._servers([(400, EXACT_ERROR)], Path(directory)) as (port, received):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    self._request(port, body)
                with raised.exception as error:
                    self.assertEqual(error.code, 400)
                    self.assertEqual(error.read(), EXACT_ERROR)

        self.assertEqual(len(received), 1)
        self.assertEqual(json.loads(received[0]["body"]), json.loads(body))
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
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            with self._servers([(400, response_body), (200, success)], log_dir) as (
                port,
                received,
            ):
                with self._request(port, body) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), success)
            logs = (log_dir / "proxy.log").read_text(encoding="utf-8")

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
        with tempfile.TemporaryDirectory() as directory:
            with self._servers([(400, unknown)], Path(directory)) as (port, received):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    self._request(port, body)
                with raised.exception as error:
                    self.assertEqual(error.code, 400)
                    self.assertEqual(error.headers["Content-Length"], str(len(unknown)))
                    self.assertEqual(error.read(), unknown)

        self.assertEqual(len(received), 1)
        forwarded = json.loads(received[0]["body"])
        expected = json.loads(body)
        expected["include"] = ["other"]
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
                runtime_state.reset_for_test()
                body = _request_body()
                with tempfile.TemporaryDirectory() as directory:
                    with self._servers(
                        [(400, EXACT_ERROR), (status_code, terminal_body)], Path(directory)
                    ) as (port, received):
                        with self.assertRaises(urllib.error.HTTPError) as raised:
                            self._request(port, body)
                        with raised.exception as error:
                            self.assertEqual(error.code, status_code)
                            self.assertEqual(
                                error.headers["Content-Length"], str(len(terminal_body))
                            )
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
                if classification == "input_variant_validation_error":
                    expected_classifications = {"input_variant_validation_error": 2}
                self.assertEqual(classifications, expected_classifications)

    def test_recovery_transport_failure_is_terminal_without_normal_retry(self) -> None:
        body = _request_body()
        transport_error = urllib.error.URLError("private-upstream-detail")
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            with self._servers([(400, EXACT_ERROR)], log_dir) as (port, received):
                real_urlopen = responses_transport.urlopen_direct
                calls = 0

                def fail_second(request: urllib.request.Request, timeout: float):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise transport_error
                    return real_urlopen(request, timeout)

                with mock.patch.object(
                    responses_transport, "urlopen_direct", side_effect=fail_second
                ):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        self._request(port, body)
                with raised.exception as error:
                    payload = json.loads(error.read())
                    self.assertEqual(error.code, 502)
                    self.assertEqual(
                        error.headers["Content-Length"],
                        str(len(json.dumps(payload, separators=(",", ":")).encode())),
                    )
                    self.assertEqual(
                        payload["error"]["code"], "input_variant_recovery_transport_error"
                    )
            logs = (log_dir / "proxy.log").read_text(encoding="utf-8")

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
        with tempfile.TemporaryDirectory() as directory:
            with self._servers(
                [
                    (400, EXACT_ERROR),
                    {"status": 200, "payload": incomplete, "content_type": "text/event-stream"},
                    {
                        "status": 200,
                        "payload": unexpected_reconnect,
                        "content_type": "text/event-stream",
                    },
                ],
                Path(directory),
            ) as (port, received):
                with mock.patch.object(sse_transport.time, "sleep", return_value=None):
                    with self.assertRaises(urllib.error.HTTPError) as raised:
                        self._request(port, body)
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
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            with self._servers(
                [
                    (400, EXACT_ERROR),
                    {"status": 200, "payload": completed, "content_type": "text/event-stream"},
                ],
                log_dir,
            ) as (port, received):
                with self._request(port, body) as response:
                    self.assertEqual(response.status, 200)
                    downstream = response.read()
            logs = (log_dir / "proxy.log").read_text(encoding="utf-8")

        self.assertEqual(len(received), 2)
        self.assertEqual(received[1]["content_length"], str(len(received[1]["body"])))
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
