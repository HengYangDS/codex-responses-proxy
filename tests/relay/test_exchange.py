"""HTTP orchestration contracts for exact Responses input recovery."""

from __future__ import annotations

from contextlib import ExitStack

import http.client
import io
import json
import re
import socket
import tempfile
import urllib.error
import urllib.request
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import cast

from codex_responses_proxy.protocol import request as rewrite
from codex_responses_proxy.protocol import response as response_projection
from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.relay import (
    admission,
    cooldown,
    operational_log,
    responses,
    sse,
    telemetry,
)
from codex_responses_proxy.relay import exchange as upstream_exchange
from codex_responses_proxy.relay import relay as downstream
from codex_responses_proxy.service import entrypoint as proxy
from tests.relay.proxy_fixture import request, running_proxy
import pytest

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = provider_registry.load()


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

    def close(self) -> None:
        """Satisfy the upstream response lifecycle contract."""


class InputTransportContracts:
    """Exercise the recovery boundary through real loopback HTTP servers."""

    def setup_method(self) -> None:
        self._cleanups = ExitStack()
        old_log_path = operational_log.LOG_PATH
        self._log_directory = tempfile.TemporaryDirectory()
        operational_log.LOG_PATH = str(Path(self._log_directory.name) / "proxy.log")
        self._cleanups.callback(self._log_directory.cleanup)
        self._cleanups.callback(setattr, operational_log, "LOG_PATH", old_log_path)
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()

    def teardown_method(self) -> None:
        self._cleanups.close()

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
                assert response.status == 200
                assert response.read() == success

        assert len(received) == 2
        recovery = received[1]
        assert len(recovery) < len(body)
        recovered = json.loads(recovery)
        assert recovered["store"] is False
        assert recovered["instructions"] == "top-level-current-policy"
        assert "previous_response_id" not in recovered
        assert "conversation" not in recovered
        assert "prompt_cache_key" not in recovered
        assert recovered["include"] == ["other"]
        assert recovered["input"] == [
            {"type": "message", "role": "developer", "content": "current policy"},
            {"type": "message", "role": "user", "content": "private-current-prompt"},
        ]
        status = self._status_snapshot()
        counters = cast("dict[str, int]", status["counters"])
        classifications = cast("dict[str, int]", status["upstream_classifications"])
        assert counters["input_variant_dialogue_recovery_attempts"] == 1
        assert counters["input_variant_dialogue_recovery_accepted"] == 1
        assert counters["input_variant_dialogue_recovery_exhausted"] == 0
        assert classifications == {"input_variant_validation_error": 1}
        public_status = json.dumps(status, sort_keys=True)
        assert not re.search(
            "private-current-prompt|top-level-current-policy|stale-response-binding|"
            "stale-conversation-binding|stale-private-cache-key",
            public_status,
        )
        assert "release" in status
        assert "serving_payload_sha256" in status
        assert "release_receipt_sha256" in status

    def test_exact_error_without_a_strictly_smaller_recovery_is_passed_through(self) -> None:
        body = json.dumps(
            {"input": [{"type": "message", "role": "user", "content": "current"}]},
            separators=(",", ":"),
        ).encode()
        with running_proxy([(400, EXACT_ERROR)]) as (port, received):
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.value as error:
                assert error.code == 400
                assert error.read() == EXACT_ERROR

        assert len(received) == 1
        assert json.loads(received[0]) == {**json.loads(body), "store": False}
        counters, classifications = self._status_maps()
        assert counters["input_variant_dialogue_recovery_attempts"] == 0
        assert counters["response_failed_compaction_attempts"] == 0
        assert counters["response_failed_dialogue_recovery_attempts"] == 0
        assert classifications == {"input_variant_validation_error": 1}

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
                assert response.status == 200
                assert response.read() == success
            logs = Path(operational_log.LOG_PATH).read_text(encoding="utf-8")

        assert len(received) == 2
        assert "opaque-upstream-request-id" not in logs
        assert "opaque-envelope-metadata" not in logs
        counters, classifications = self._status_maps()
        assert counters["input_variant_dialogue_recovery_attempts"] == 1
        assert counters["input_variant_dialogue_recovery_accepted"] == 1
        assert classifications == {"input_variant_validation_error": 1}

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
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.value as error:
                assert error.code == 400
                assert error.headers["Content-Length"] == str(len(unknown))
                assert error.read() == unknown

        assert len(received) == 1
        forwarded = json.loads(received[0])
        expected = json.loads(cast("bytes", rewrite.sanitize_responses_body(body).body))
        assert forwarded == expected
        counters, classifications = self._status_maps()
        assert counters["input_variant_dialogue_recovery_attempts"] == 0
        assert classifications == {"http_400": 1}

    def test_recovery_second_http_error_is_terminal_without_other_recovery(self, subtests) -> None:
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
            with subtests.test(label=label):
                admission.reset_for_test()
                telemetry.reset_for_test()
                cooldown.reset_for_test()
                body = _request_body()
                with running_proxy([(400, EXACT_ERROR), (status_code, terminal_body)]) as (
                    port,
                    received,
                ):
                    with pytest.raises(urllib.error.HTTPError) as raised:
                        request(port, body)
                    with raised.value as error:
                        assert error.code == status_code
                        assert error.headers["Content-Length"] == str(len(terminal_body))
                        assert error.read() == terminal_body

                assert len(received) == 2
                counters, classifications = self._status_maps()
                assert counters["input_variant_dialogue_recovery_attempts"] == 1
                assert counters["input_variant_dialogue_recovery_exhausted"] == 1
                assert counters["wire_failure_retry_attempts"] == 0
                assert counters["response_failed_compaction_attempts"] == 0
                assert counters["response_failed_dialogue_recovery_attempts"] == 0
                assert counters["streams_pre_content_reconnect_attempts"] == 0
                expected_classifications = {classification: 1, "input_variant_validation_error": 1}
                expected_classifications[classification] += (
                    classification == "input_variant_validation_error"
                )
                assert classifications == expected_classifications

    def test_recovery_transport_failure_is_terminal_without_normal_retry(self, *, mocker) -> None:
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

            mocker.patch.object(upstream_exchange, "urlopen_direct", side_effect=fail_second)
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.value as error:
                payload = json.loads(error.read())
                assert error.code == 502
                assert error.headers["Content-Length"] == str(
                    len(json.dumps(payload, separators=(",", ":")).encode())
                )
                assert payload["error"]["code"] == "input_variant_recovery_transport_error"
            logs = Path(operational_log.LOG_PATH).read_text(encoding="utf-8")

        assert calls == 2
        assert len(received) == 1
        assert "private-upstream-detail" not in logs
        assert "private-current-prompt" not in logs
        assert "stale-private-cache-key" not in logs
        assert "exception=URLError" in logs
        assert "event=upstream_transport_retry" not in logs
        counters, _classifications = self._status_maps()
        assert counters["input_variant_dialogue_recovery_exhausted"] == 1

    def test_recovered_sse_failure_does_not_reconnect(self, *, mocker) -> None:
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
            mocker.patch.object(sse.time, "sleep", return_value=None)
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.value as error:
                payload = json.loads(error.read())
                assert error.code == 503
                assert payload["error"]["code"] == "stream_pre_content_exhausted"
                assert payload["error"]["attempts"] == 1

        assert len(received) == 2
        counters, _classifications = self._status_maps()
        assert counters["streams_pre_content_reconnect_attempts"] == 0
        assert counters["input_variant_dialogue_recovery_exhausted"] == 1
        assert counters["input_variant_dialogue_recovery_accepted"] == 0

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
                assert response.status == 200
                downstream = response.read()
            logs = Path(operational_log.LOG_PATH).read_text(encoding="utf-8")

        assert len(received) == 2
        assert downstream.count(b'"type":"response.created"') == 1
        assert downstream.count(b'"type":"response.output_text.delta"') == 1
        assert downstream.count(b'"type":"response.completed"') == 1
        assert "private-current-prompt" not in logs
        assert "stale-conversation-binding" not in logs
        counters, classifications = self._status_maps()
        assert counters["streams_pre_content_reconnect_attempts"] == 0
        assert counters["input_variant_dialogue_recovery_attempts"] == 1
        assert counters["input_variant_dialogue_recovery_accepted"] == 1
        assert counters["input_variant_dialogue_recovery_exhausted"] == 0
        assert classifications == {"input_variant_validation_error": 1}

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
        assert results == [(terminal, detail, True) for _, terminal, detail, _ in cases]
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["encrypted_sse_keys_stripped"] == 1
        assert b"secret" not in handler.output()

    def test_sse_projection_failure_after_commit_terminates_without_ciphertext(
        self, *, mocker
    ) -> None:
        plaintext = b'data: {"type":"response.output_text.delta","delta":"visible"}\n\n'
        encrypted = (
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"secret"}]}}\n\n'
        )
        mocker.patch.object(response_projection.json, "dumps", side_effect=TypeError("unsupported"))
        handler = _MemoryHandler()
        result = sse.relay(
            handler,
            _DirectResponse(plaintext + encrypted),
            "/dmxapi/v1/responses",
            1,
            send_headers=lambda: None,
        )

        assert not result["pre_content_exhausted"]
        assert result["result"] is not None
        assert result["result"]["detail"] == "projection_failed"
        assert result["result"]["error"] is not None
        assert b"visible" in handler.output()
        assert b"secret" not in handler.output()
        assert handler.output().endswith(b"0\r\n\r\n")
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["stream_projection_failures"] == 1

    def test_sse_projection_failure_before_commit_returns_retryable_error(self, *, mocker) -> None:
        body = _request_body(stream=True)
        encrypted = (
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"secret"}]}}\n\n'
        )
        with running_proxy(
            [{"status": 200, "chunks": [encrypted], "content_type": "text/event-stream"}]
        ) as (port, _received):
            projected = rewrite.sanitize_responses_body(body).body
            assert projected is not None
            mocker.patch.object(
                rewrite,
                "sanitize_responses_body",
                return_value=rewrite.ProjectionResult(projected, "clean"),
            )
            real_dumps = response_projection.json.dumps

            def fail_encrypted_payload(payload, *args, **kwargs):
                if isinstance(payload, dict) and payload.get("type") == "response.completed":
                    raise TypeError("unsupported")
                return real_dumps(payload, *args, **kwargs)

            mocker.patch.object(
                response_projection.json, "dumps", side_effect=fail_encrypted_payload
            )
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, body)
            with raised.value as response:
                status = response.code
                payload = json.loads(response.read())

        assert status == 503
        assert payload["error"]["code"] == "stream_projection_failed"
        assert b"secret" not in json.dumps(payload).encode()
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["stream_projection_failures"] == 1

    def test_direct_sse_relay_handles_reopen_failure_and_incomplete_terminal(
        self, *, mocker
    ) -> None:
        failed = _DirectResponse(b'data: {"type":"response.failed"}\n\n')
        handler = _MemoryHandler()
        mocker.patch.object(sse.time, "sleep", return_value=None)
        result = sse.relay(
            handler,
            failed,
            "/v1/responses",
            1,
            reopen=mocker.Mock(side_effect=OSError("private")),
        )
        assert result["pre_content_exhausted"]
        assert result["attempts"] == 1

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
        assert not result["pre_content_exhausted"]
        assert handler.output().endswith(b"0\r\n\r\n")
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["streams_incomplete"] == 1

    def test_direct_relay_covers_transport_exhaustion_without_a_local_queue(
        self, *, mocker
    ) -> None:
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        handler = _MemoryHandler(path="/dmxapi/v1/models")
        mocker.patch.object(upstream_exchange, "urlopen_direct", side_effect=OSError("private"))
        responses.relay(handler, "GET", PROVIDERS)
        assert handler.statuses == [502]
        assert b"catalog_transport_error" in handler.output()

    def test_direct_relay_covers_retry_and_fallback_transport_failure(self, *, mocker) -> None:
        transient = _http_error(503, "failure", b"temporary")
        success = _DirectResponse(b'{"id":"resp_ok","status":"completed"}')
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        mocker.patch.object(upstream_exchange, "urlopen_direct", side_effect=[transient, success])
        mocker.patch.object(upstream_exchange.time, "sleep", return_value=None)
        responses.relay(handler, "POST", PROVIDERS)
        assert handler.statuses == [200]
        assert b"resp_ok" in handler.output()

        empty = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        fallback_error = OSError("private")
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream_error = _http_error(477, "empty", empty)
        mocker.patch.object(
            upstream_exchange, "urlopen_direct", side_effect=[upstream_error, fallback_error]
        )
        responses.relay(handler, "POST", PROVIDERS)
        assert handler.statuses == [503]
        assert b"dmx_empty_response_exhausted" in handler.output()

    def test_rate_limit_is_relayed_after_one_upstream_attempt_without_sleep(
        self, *, mocker
    ) -> None:
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
        open_ = mocker.patch.object(upstream_exchange, "urlopen_direct", side_effect=rate_limited)
        sleep = mocker.patch.object(upstream_exchange.time, "sleep", return_value=None)
        responses.relay(handler, "POST", PROVIDERS)

        assert open_.call_count == 1
        sleep.assert_not_called()
        assert handler.statuses == [429]
        assert handler.output() == payload
        assert ("Retry-After", "7") in handler.sent_headers
        assert ("X-Request-Id", "rate-limit-request") in handler.sent_headers

    def test_rate_limit_contract_holds_across_real_loopback_http(self) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        with running_proxy([(429, payload)]) as (port, received):
            with pytest.raises(urllib.error.HTTPError) as raised:
                request(port, json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
            with raised.value as error:
                assert error.code == 429
                assert error.read() == payload

        assert len(received) == 1

    def test_rate_limit_bypasses_even_a_broad_provider_wire_retry_policy(self, *, mocker) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Retry-After"] = "7"
        policy = mocker.Mock()
        policy.request_fingerprint.return_value = "test-wire-fingerprint"
        policy.is_retryable_failure.return_value = True
        policy.POLICY_VERSION = "test-wire-policy"
        profiles = dict(PROVIDERS.profiles)
        current = profiles["ucloud"]
        profiles["ucloud"] = type(current)(current.name, current.base_url, policy)
        registry = type(PROVIDERS)(profiles)

        def rate_limited(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://upstream.test/v1/responses",
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(payload),
            )

        handler = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        open_ = mocker.patch.object(upstream_exchange, "urlopen_direct", side_effect=rate_limited)
        sleep = mocker.patch.object(upstream_exchange.time, "sleep", return_value=None)
        responses.relay(handler, "POST", registry)

        assert open_.call_count == 1
        sleep.assert_not_called()
        assert handler.statuses == [429]
        assert handler.output() == payload

    def test_rate_limit_cooldown_is_provider_scoped_and_skips_upstream(self, *, mocker) -> None:
        payload = b'{"error":{"message":"provider concurrency limit reached"}}'
        first = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        second = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        other = _MemoryHandler(json.dumps({"input": []}).encode(), path="/aihubmix/v1/responses")
        open_ = mocker.patch.object(
            upstream_exchange,
            "urlopen_direct",
            side_effect=[
                _http_error(429, "Too Many Requests", payload),
                _DirectResponse(b'{"id":"resp_other","status":"completed"}'),
            ],
        )
        responses.relay(first, "POST", PROVIDERS)
        responses.relay(second, "POST", PROVIDERS)
        responses.relay(other, "POST", PROVIDERS)

        assert open_.call_count == 2
        assert first.statuses == [429]
        assert second.statuses == [429]
        assert b"provider_rate_limit_cooldown" in second.output()
        assert ("Retry-After", "5") in second.sent_headers
        assert other.statuses == [200]
        assert other.output() == b'{"id":"resp_other","status":"completed"}'

    def test_rate_limit_cooldown_rejects_before_lifecycle_admission(self, *, mocker) -> None:
        cooldown.remember_failure(
            cooldown.provider_key("ucloud"),
            cooldown_seconds=5,
        )
        handler = _MemoryHandler(json.dumps({"input": []}).encode(), path="/ucloud/v1/responses")
        admit = mocker.patch.object(admission, "admit_response")
        open_ = mocker.patch.object(upstream_exchange, "urlopen_direct")
        responses.relay(handler, "POST", PROVIDERS)

        admit.assert_not_called()
        open_.assert_not_called()
        assert handler.statuses == [429]
        assert b"provider_rate_limit_cooldown" in handler.output()

    def test_direct_relay_handles_large_request_and_cooldown(self, *, mocker) -> None:
        body = json.dumps({"input": "x" * 400_000}).encode()
        handler = _MemoryHandler(body)
        mocker.patch.object(
            upstream_exchange,
            "urlopen_direct",
            return_value=_DirectResponse(b'{"id":"resp_large","status":"completed"}'),
        )
        responses.relay(handler, "POST", PROVIDERS)
        assert handler.statuses == [200]

        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        body = json.dumps({"input": []}).encode()
        handler = _MemoryHandler(body)
        mocker.patch.object(cooldown, "remaining", return_value=1.0)
        responses.relay(handler, "POST", PROVIDERS)
        assert handler.statuses == [503]
        assert b"dmx_empty_response_exhausted" in handler.output()

    def test_direct_relay_reaches_terminal_transport_after_cooldown(self, *, mocker) -> None:
        body = json.dumps({"input": []}).encode()
        handler = _MemoryHandler(body)
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()
        mocker.patch.object(upstream_exchange, "_MAX_ATTEMPTS", 0)
        mocker.patch.object(upstream_exchange, "INPUT_VARIANT_DIALOGUE_SLOTS", 0)
        mocker.patch.object(upstream_exchange, "RESPONSE_FAILED_DIALOGUE_SLOTS", 0)
        mocker.patch.object(upstream_exchange, "RESPONSE_FAILED_MAX_STAGES", 0)
        responses.relay(handler, "POST", PROVIDERS)
        assert handler.statuses == [502]
        assert b"upstream_transport_error" in handler.output()

    def test_direct_transport_terminal_branches_emit_bounded_results(self, *, mocker) -> None:
        handler = _MemoryHandler()
        exchange = mocker.Mock(
            handler=handler,
            is_responses=True,
            used_input_variant_dialogue=False,
        )
        exchange.profile.wire_policy = None

        with pytest.raises(RuntimeError, match="wire recovery requires a provider policy"):
            upstream_exchange._reject_wire_failure(exchange, "fingerprint", 2, "event", "")
        assert not upstream_exchange._retry_wire_failure(exchange)

        sleep = mocker.patch.object(upstream_exchange.time, "sleep", return_value=None)
        assert upstream_exchange._transport_error(exchange, OSError("private"), 0) == "retry"
        sleep.assert_called_once()

        outcome = upstream_exchange._transport_error(exchange, OSError("private"), 3)
        assert outcome == "terminal"
        assert handler.statuses == [502]
        assert b"upstream_transport_error" in handler.output()

    def test_direct_non_responses_body_covers_empty_and_terminal_chunks(self, *, mocker) -> None:
        handler = _MemoryHandler(path="/dmxapi/v1/health")
        exchange = mocker.Mock(handler=handler, is_responses=True)
        exchange.input_variant_accepted = mocker.Mock()
        downstream.relay_body(exchange, _DirectResponse(b"", b""))
        assert handler.statuses == [200]
        assert handler.output() == b"0\r\n\r\n"
        exchange.input_variant_accepted.assert_called_once_with()

        admission.reset_for_test()
        telemetry.reset_for_test()
        handler = _MemoryHandler(path="/dmxapi/v1/health")
        exchange = mocker.Mock(handler=handler, is_responses=True)
        exchange.input_variant_accepted = mocker.Mock()
        downstream.relay_body(
            exchange,
            _DirectResponse(b"partial", http.client.IncompleteRead(b"terminal")),
        )
        assert b"partial" in handler.output()
        assert b"terminal" in handler.output()
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["responses_completed"] == 1
        exchange.input_variant_accepted.assert_called_once_with()

    def test_non_responses_helpers_bypass_responses_only_policy(self, *, mocker) -> None:
        handler = _MemoryHandler(path="/dmxapi/v1/models")
        exchange = mocker.Mock(handler=handler, is_responses=False)
        exchange.input_variant_accepted = mocker.Mock()

        assert responses._admit(exchange)
        assert not responses._cooldown_active(exchange)
        downstream.relay_body(exchange, _DirectResponse(b""))
        assert handler.output() == b"0\r\n\r\n"
        exchange.input_variant_accepted.assert_called_once_with()

        assert sse._arm_read_budget(_DirectResponse(), sse.time.monotonic() - 1, None) is None

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
        assert not result["pre_content_exhausted"]
        assert sent == 1
        assert handler.output().count(b"response.completed") == 1

    def test_direct_non_sse_stream_handles_incomplete_and_writer_failures(self, *, mocker) -> None:
        partial = http.client.IncompleteRead(b"partial")
        handler = _MemoryHandler(path="/dmxapi/v1/models")
        mocker.patch.object(
            upstream_exchange, "urlopen_direct", return_value=_DirectResponse(partial)
        )
        responses.relay(handler, "GET", PROVIDERS)
        assert handler.statuses == [200]
        assert b"partial" in handler.output()

        statuses = []
        for error in (BrokenPipeError(), RuntimeError("private")):
            handler = _MemoryHandler(path="/dmxapi/v1/models")
            handler.wfile = mocker.Mock()
            handler.wfile.write.side_effect = error
            mocker.patch.object(
                upstream_exchange, "urlopen_direct", return_value=_DirectResponse(b"body")
            )
            responses.relay(handler, "GET", PROVIDERS)
            statuses.append(handler.statuses)
        assert statuses == [[200], [200]]

    def test_non_stream_responses_strip_ciphertext_before_downstream_commit(
        self, *, mocker
    ) -> None:
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
        mocker.patch.object(
            upstream_exchange, "urlopen_direct", return_value=_DirectResponse(upstream)
        )
        responses.relay(handler, "POST", PROVIDERS)

        assert handler.statuses == [200]
        assert b"secret" not in handler.output()
        assert b"visible" in handler.output()

    def test_empty_responses_request_fails_before_upstream_io(self, *, mocker) -> None:
        handler = _MemoryHandler(b"")
        opened = mocker.patch.object(upstream_exchange, "urlopen_direct")
        responses.relay(handler, "POST", PROVIDERS)

        assert handler.statuses == [400]
        assert b"provider_portable_projection_rejected" in handler.output()
        opened.assert_not_called()

    def test_invalid_successful_responses_fail_before_downstream_commit(
        self, subtests, *, mocker
    ) -> None:
        invalid = (
            _DirectResponse(b""),
            _DirectResponse(http.client.IncompleteRead(b'{"status":"completed"')),
            _DirectResponse(b"not-json"),
            _DirectResponse(b'{"id":"resp","status":"in_progress","output":[]}'),
        )
        for upstream in invalid:
            with subtests.test(upstream=upstream):
                admission.reset_for_test()
                handler = _MemoryHandler(json.dumps({"input": []}).encode())
                mocker.patch.object(upstream_exchange, "urlopen_direct", return_value=upstream)
                responses.relay(handler, "POST", PROVIDERS)
                assert handler.statuses == [503]
                assert b"invalid_responses_success_body" in handler.output()

    def test_oversized_successful_response_fails_before_downstream_commit(self, *, mocker) -> None:
        handler = _MemoryHandler(json.dumps({"input": []}).encode())
        upstream = _DirectResponse(b'{"status":"completed","output":"', b"x" * 64, b'"}')
        mocker.patch.object(upstream_exchange, "urlopen_direct", return_value=upstream)
        mocker.patch.object(downstream, "MAX_RESPONSES_JSON_BYTES", 32)
        responses.relay(handler, "POST", PROVIDERS)

        assert handler.statuses == [503]
        assert b"response_too_large" in handler.output()
