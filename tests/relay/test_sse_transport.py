"""Server-sent event transport contracts."""

from __future__ import annotations

import http.client
import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy.protocol import request as rewrite
from codex_responses_proxy.protocol import response as response_projection
from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.relay import (
    admission,
    cooldown,
    operational_log,
    sse,
    telemetry,
)
from codex_responses_proxy.relay import relay as downstream
from tests.relay.exchange_fixture import (
    EXACT_ERROR,
    DirectResponse,
    InputTransportFixture,
    MemoryHandler,
    request_body,
)
from tests.relay.proxy_fixture import request, running_proxy

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = provider_registry.load()


class TestSseTransport(InputTransportFixture):
    def test_recovered_sse_failure_does_not_reconnect(self, *, mocker) -> None:
        body = request_body(stream=True)
        incomplete = b'data: {"type":"response.created"}\n\n'
        unexpected_reconnect = b'data: {"type":"response.completed"}\n\n'
        with running_proxy(
            [
                (400, EXACT_ERROR),
                {
                    "status": 200,
                    "payload": incomplete,
                    "content_type": "text/event-stream",
                },
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
        body = request_body(stream=True)
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
                DirectResponse(
                    http.client.IncompleteRead(b'data: {"type": "response.incomplete"}')
                ),
                "response.incomplete",
                "incomplete",
                object,
            ),
            (
                DirectResponse(TimeoutError("private")),
                None,
                "timeout",
                socket.timeout,
            ),
            (DirectResponse(RuntimeError("private")), None, "eof", RuntimeError),
            (DirectResponse(encrypted), None, "eof", object),
        )
        results = []
        for upstream, _, _, error_type in cases:
            admission.reset_for_test()
            telemetry.reset_for_test()
            cooldown.reset_for_test()
            handler = MemoryHandler()
            result = sse._read_one_stream(handler, upstream, "/v1/responses", 1, lambda: None)
            results.append(
                (
                    result["terminal"],
                    result["detail"],
                    isinstance(result["error"], error_type),
                )
            )
        assert results == [(terminal, detail, True) for _, terminal, detail, _ in cases]
        assert b"secret" in handler.output()

    def test_live_sse_preserves_ciphertext_after_commit(self, *, mocker) -> None:
        plaintext = b'data: {"type":"response.output_text.delta","delta":"visible"}\n\n'
        encrypted = (
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"secret"}]}}\n\n'
        )
        mocker.patch.object(response_projection.json, "dumps", side_effect=TypeError("unsupported"))
        handler = MemoryHandler()
        result = sse.relay(
            handler,
            DirectResponse(plaintext + encrypted),
            "/dmxapi/v1/responses",
            1,
            send_headers=lambda: None,
        )

        assert not result["pre_content_exhausted"]
        assert result["result"] is not None
        assert result["result"]["detail"] == "completed"
        assert result["result"]["error"] is None
        assert b"visible" in handler.output()
        assert b"secret" in handler.output()
        assert handler.output().endswith(b"0\r\n\r\n")
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["stream_projection_failures"] == 0

    def test_live_sse_preserves_ciphertext_before_commit(self, *, mocker) -> None:
        body = request_body(stream=True)
        encrypted = (
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"secret"}]}}\n\n'
        )
        with running_proxy(
            [
                {
                    "status": 200,
                    "chunks": [encrypted],
                    "content_type": "text/event-stream",
                }
            ]
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
            with request(port, body) as response:
                status = response.status
                payload = response.read()

        assert status == 200
        assert b"secret" in payload
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["stream_projection_failures"] == 0

    def test_malformed_sse_fails_before_downstream_commit(self) -> None:
        malformed = b'data: {"type":\n\n'
        handler = MemoryHandler()

        result = sse.relay(
            handler,
            DirectResponse(malformed),
            "/dmxapi/v1/responses",
            1,
            send_headers=lambda: None,
        )

        assert result["pre_content_exhausted"]
        assert result["result"] is not None
        assert result["result"]["detail"] == "projection_failed"
        assert handler.output() == b""
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["stream_projection_failures"] == 1

    def test_public_sse_relay_rejects_an_unprojectable_stream(self, *, mocker) -> None:
        handler = MemoryHandler()
        exchange = mocker.Mock(
            handler=handler,
            request_id=7,
            used_input_variant_dialogue=False,
        )
        mocker.patch.object(
            sse,
            "relay",
            return_value={
                "result": {"detail": "projection_failed"},
                "pre_content_exhausted": True,
                "attempts": 1,
            },
        )

        downstream.relay_sse(exchange, DirectResponse())

        assert handler.statuses == [503]
        assert b"stream_projection_failed" in handler.output()
        exchange.log.assert_called_once_with("sse_projection_failed")

    def test_unexpected_terminal_validator_failure_is_bounded(self, *, mocker) -> None:
        handler = MemoryHandler()
        exchange = mocker.Mock(handler=handler)
        mocker.patch.object(
            response_projection,
            "validate_json_response",
            side_effect=RuntimeError("private-validator-detail"),
        )

        downstream.relay_responses_json(
            exchange,
            DirectResponse(b'{"status":"completed","output":[]}'),
        )

        assert handler.statuses == [503]
        payload = json.loads(handler.output())
        assert payload["error"]["code"] == "invalid_responses_success_body"
        assert payload["error"]["reason"] == "RuntimeError"
        exchange.log.assert_called_once_with(
            "invalid_responses_success_body", "reason=RuntimeError "
        )

    def test_direct_sse_relay_handles_reopen_failure_and_incomplete_terminal(
        self, *, mocker
    ) -> None:
        failed = DirectResponse(b'data: {"type":"response.failed"}\n\n')
        handler = MemoryHandler()
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
        handler = MemoryHandler()
        result = sse.relay(
            handler,
            DirectResponse(b'data: {"type": "response.incomplete"}\n\n'),
            "/v1/responses",
            2,
            send_headers=lambda: None,
        )
        assert not result["pre_content_exhausted"]
        assert handler.output().endswith(b"0\r\n\r\n")
        counters = cast("dict[str, int]", self._status_snapshot()["counters"])
        assert counters["streams_incomplete"] == 1

    def test_sse_deadline_and_reconnect_deadline_are_bounded(self, *, mocker) -> None:
        handler = MemoryHandler()
        read_budget = mocker.patch.object(sse, "_arm_read_budget", return_value=None)
        result = sse._read_one_stream(handler, DirectResponse(), "/v1/responses", 1, lambda: None)
        assert result["detail"] == "deadline"
        mocker.stop(read_budget)

        handler = MemoryHandler()
        mocker.patch.object(
            sse,
            "_read_one_stream",
            return_value={
                "terminal": None,
                "events": 0,
                "wrote_downstream": False,
                "detail": "deadline",
                "error": None,
            },
        )
        mocker.patch.object(sse.time, "monotonic", side_effect=[0.0, sse.UPSTREAM_TIMEOUT])
        result = sse.relay(
            handler,
            DirectResponse(b""),
            "/v1/responses",
            2,
            reopen=mocker.Mock(),
        )
        assert result["attempts"] == 1

        mocker.stopall()
        handler = MemoryHandler()
        mocker.patch.object(sse.time, "monotonic", return_value=2.0)
        result = sse._read_one_stream(
            handler,
            DirectResponse(TimeoutError("late")),
            "/v1/responses",
            3,
            lambda: None,
            deadline=1.0,
        )
        assert result["detail"] == "deadline"

    def test_direct_sse_relay_flushes_completed_prelude(self) -> None:
        handler = MemoryHandler()
        sent = 0

        def mark_headers() -> None:
            nonlocal sent
            sent += 1

        result = sse.relay(
            handler,
            DirectResponse(
                b'data: {"type":"response.created"}\n\ndata: {"type":"response.completed"}\n\n'
            ),
            "/v1/responses",
            1,
            send_headers=mark_headers,
        )
        assert not result["pre_content_exhausted"]
        assert sent == 1
        assert handler.output().count(b"response.completed") == 1
