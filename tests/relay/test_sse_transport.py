"""Server-sent event transport contracts."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from codex_responses_proxy.protocol import response as response_projection
from codex_responses_proxy.protocol.replay import projection as rewrite
from codex_responses_proxy.providers import registry as provider_registry
from codex_responses_proxy.relay import admission
from codex_responses_proxy.relay import cooldown
from codex_responses_proxy.relay import operational_log
from codex_responses_proxy.relay import relay as downstream
from codex_responses_proxy.relay import sse
from codex_responses_proxy.relay import telemetry
from tests.relay.exchange_fixture import EXACT_ERROR
from tests.relay.exchange_fixture import DirectResponse
from tests.relay.exchange_fixture import InputTransportFixture
from tests.relay.exchange_fixture import MemoryHandler
from tests.relay.exchange_fixture import request_body
from tests.relay.proxy_fixture import request
from tests.relay.proxy_fixture import running_proxy

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = provider_registry.load()


class TestSseTransport(InputTransportFixture):
    def test_terminal_stream_finishes_while_chunked_upstream_remains_open(self, *, mocker):
        completed = b'data: {"type":"response.completed"}\n\n'
        release = threading.Event()
        mocker.patch.object(sse, "UPSTREAM_READ_TIMEOUT", 1.0)
        mocker.patch.object(sse.time, "sleep", return_value=None)
        with running_proxy([{"chunks": [completed], "stall_event": release}]) as (port, received):
            try:
                with request(port, request_body(stream=True)) as response:
                    assert response.status == 200
                    assert completed in response.read()
                    assert not release.is_set()
            finally:
                release.set()
        assert len(received) == 1

    def test_malformed_committed_stream_remains_a_truncated_http_response(self):
        content = b'data: {"type":"response.output_text.delta","delta":"keep"}\n\n'
        with (
            running_proxy([{"chunks": [content, b'data: {"type":\n\n']}]) as (
                port,
                received,
            ),
            request(port, request_body(stream=True)) as response,
        ):
            assert response.status == 200
            with pytest.raises(http.client.IncompleteRead) as raised:
                response.read()
            assert content in raised.value.partial
            assert b"503" not in raised.value.partial
            assert b"stream_projection_failed" not in raised.value.partial
        assert len(received) == 1

    @pytest.mark.parametrize(
        "terminal", ["response.completed", "response.incomplete", "response.failed"]
    )
    def test_terminal_event_finishes_without_reading_or_forwarding_trailing_data(
        self, terminal, *, mocker
    ) -> None:
        event = b"data: " + json.dumps({"type": terminal}).encode() + b"\n\n"
        tail = b'data: {"type":"response.output_text.delta","delta":"after-terminal"}\n\n'
        upstream = DirectResponse(event + tail, TimeoutError("must not await upstream EOF"))
        read = mocker.spy(upstream, "read")
        close = mocker.spy(upstream, "close")
        handler = MemoryHandler()

        result = sse.relay(handler, upstream, "/v1/responses", 1)

        read.assert_called_once_with(8192)
        close.assert_called_once_with()
        assert result["result"] is not None
        assert result["result"]["terminal"] == terminal
        assert result["result"]["error"] is None
        assert event in handler.output()
        assert b"after-terminal" not in handler.output()

    @pytest.mark.parametrize("failure", [BrokenPipeError, ConnectionResetError, RuntimeError])
    def test_downstream_failure_releases_owned_upstream_without_reconnect(
        self, failure, *, mocker
    ) -> None:
        upstream = DirectResponse(b'data: {"type":"response.completed"}\n\n')
        close = mocker.spy(upstream, "close")
        handler = MemoryHandler()
        mocker.patch.object(handler.wfile, "write", side_effect=failure("private-detail"))
        reopen = mocker.Mock()

        with pytest.raises(failure):
            sse.relay(handler, upstream, "/v1/responses", 1, reopen=reopen)

        close.assert_called_once_with()
        reopen.assert_not_called()

    def test_malformed_event_after_commit_closes_without_a_second_http_response(
        self, *, mocker
    ) -> None:
        content = b'data: {"type":"response.output_text.delta","delta":"keep"}\n\n'
        upstream = DirectResponse(content, b'data: {"type":\n\n')
        close = mocker.spy(upstream, "close")
        handler = MemoryHandler()
        exchange = mocker.Mock(handler=handler, request_id=1, used_input_variant_dialogue=False)

        downstream.relay_sse(exchange, upstream)

        assert handler.statuses == [200]
        assert handler.close_connection
        assert content in handler.output()
        assert b"stream_projection_failed" not in handler.output()
        assert not handler.output().endswith(b"0\r\n\r\n")
        close.assert_called_once_with()
        exchange.upstream.assert_not_called()

    @pytest.mark.parametrize(
        "control", [b"data: [DONE]\n\n", b": keepalive\n\n", b"event: ping\n\n"]
    )
    def test_pre_content_failure_controls_preserve_reconnect(self, control, *, mocker) -> None:
        failed = (
            b'data:{"type" : "response.created"}\n\n'
            b'data:{"type" : "response.in_progress"}\n\n'
            b'data:{"type" : "response.failed",'
            b'"response":{"error":{"code":"server_error"}}}\n\n' + control
        )
        completed = b'data: {"type":"response.completed"}\n\n'
        handler = MemoryHandler()
        reopen = mocker.Mock(return_value=DirectResponse(completed))
        mocker.patch.object(sse.time, "sleep", return_value=None)

        result = sse.relay(
            handler, DirectResponse(failed), "/ucloud/v1/responses", 1, reopen=reopen
        )

        assert result["attempts"] == 2
        reopen.assert_called_once_with()
        assert b"response.failed" not in handler.output()
        assert handler.output().count(b"response.completed") == 1

    @pytest.mark.parametrize("event", ["response.output_text.delta", "response.output_item.added"])
    def test_committed_output_is_never_replayed(self, event, *, mocker) -> None:
        content = json.dumps(
            {"type": event, "delta": "keep", "item": {"type": "function_call"}}
        ).encode()
        raw = (
            b"data: " + content + b"\n\n"
            b'data: {"type":"response.failed","response":{"error":{"code":"server_error"}}}\n\n'
            b"data: [DONE]\n\n"
        )
        handler = MemoryHandler()
        reopen = mocker.Mock()

        result = sse.relay(handler, DirectResponse(raw), "/ucloud/v1/responses", 1, reopen=reopen)

        assert result["attempts"] == 1
        reopen.assert_not_called()
        assert content in handler.output()
        assert b"response.failed" in handler.output()

    @pytest.mark.parametrize("code", ["invalid_prompt", "rate_limit_exceeded", "unknown"])
    def test_permanent_failure_is_preserved_without_reconnect(self, code, *, mocker) -> None:
        raw = (
            b"data: "
            + json.dumps(
                {"type": "response.failed", "response": {"error": {"code": code}}}
            ).encode()
            + b"\n\n"
        )
        handler = MemoryHandler()
        reopen = mocker.Mock()

        result = sse.relay(handler, DirectResponse(raw), "/ucloud/v1/responses", 1, reopen=reopen)

        assert result["attempts"] == 1
        reopen.assert_not_called()
        assert raw in handler.output()

    def test_failed_response_with_output_is_not_replayed(self, *, mocker) -> None:
        raw = b'data: {"type":"response.failed","response":{"output":[{"type":"function_call"}],"error":{"code":"server_error"}}}\n\n'
        handler = MemoryHandler()
        reopen = mocker.Mock(return_value=DirectResponse())
        mocker.patch.object(sse.time, "sleep", return_value=None)

        result = sse.relay(handler, DirectResponse(raw), "/ucloud/v1/responses", 1, reopen=reopen)

        assert result["attempts"] == 1
        reopen.assert_not_called()
        assert raw in handler.output()

    def test_failure_diagnostics_correlate_without_disclosing_payload(self, *, mocker) -> None:
        request_id = "64781e82-1e8f-42af-a06a-409e154bbfe2"
        raw = (
            b"data: "
            + json.dumps(
                {
                    "type": "response.failed",
                    "response": {
                        "error": {
                            "code": "server_error",
                            "message": f"private-prompt-secret request ID {request_id} in your email",
                        }
                    },
                }
            ).encode()
            + b"\n\n"
        )
        mocker.patch.object(sse.time, "sleep", return_value=None)
        reopen = mocker.Mock(
            return_value=DirectResponse(b'data: {"type":"response.completed"}\n\n')
        )

        sse.relay(MemoryHandler(), DirectResponse(raw), "/ucloud/v1/responses", 7, reopen=reopen)

        logs = Path(operational_log.LOG_PATH).read_text()
        assert f"upstream_request_id={request_id}" in logs
        assert "code=server_error" in logs
        assert "req=7 event=sse_upstream_failed" in logs
        assert "private-prompt-secret" not in logs

    def test_reconnect_backoff_does_not_outlive_stream_deadline(self, *, mocker) -> None:
        handler = MemoryHandler()
        reopen = mocker.Mock(return_value=DirectResponse())
        mocker.patch.object(
            sse,
            "_read_one_stream",
            return_value={
                "terminal": None,
                "events": 0,
                "wrote_downstream": False,
                "detail": "eof",
                "error": None,
            },
        )
        sleep = mocker.patch.object(sse.time, "sleep", return_value=None)
        mocker.patch.object(
            sse.time, "monotonic", side_effect=[0.0] + [sse.UPSTREAM_TIMEOUT - 0.1] * 20
        )

        result = sse.relay(handler, DirectResponse(), "/ucloud/v1/responses", 1, reopen=reopen)

        assert result["attempts"] == 1
        sleep.assert_not_called()
        reopen.assert_not_called()

    def test_transient_failure_reconnects_are_bounded(self, *, mocker) -> None:
        raw = (
            b'data: {"type":"response.failed","response":{"error":{"code":"server_error"}}}\n\n'
            b"data: [DONE]\n\n"
        )
        handler = MemoryHandler()
        reopen = mocker.Mock(side_effect=lambda: DirectResponse(raw))
        mocker.patch.object(sse.time, "sleep", return_value=None)

        result = sse.relay(handler, DirectResponse(raw), "/ucloud/v1/responses", 1, reopen=reopen)

        assert result["pre_content_exhausted"]
        assert result["attempts"] == 6
        assert reopen.call_count == 5
        assert handler.output() == b""

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
        final_output = b""
        for upstream, _, _, error_type in cases:
            admission.reset_for_test()
            telemetry.reset_for_test()
            cooldown.reset_for_test()
            handler = MemoryHandler()
            result = sse._read_one_stream(handler, upstream, lambda: None)
            results.append(
                (
                    result["terminal"],
                    result["detail"],
                    isinstance(result["error"], error_type),
                )
            )
            final_output = handler.output()
        assert results == [(terminal, detail, True) for _, terminal, detail, _ in cases]
        assert b"secret" in final_output

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
        failed = DirectResponse(
            b'data: {"type":"response.failed","response":{"error":{"code":"server_error"}}}\n\n'
        )
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
        result = sse._read_one_stream(handler, DirectResponse(), lambda: None)
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
