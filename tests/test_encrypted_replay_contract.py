"""Synthetic, secret-free replay compatibility contract for the live proxy source."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from io import BytesIO

_PROXY_PATH = Path(__file__).parents[1] / "proxy" / "dmx_responses_proxy.py"
_SPEC = importlib.util.spec_from_file_location("live_proxy_contract", _PROXY_PATH)
assert _SPEC and _SPEC.loader
_PROXY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROXY)

_CONTROL_PATH = Path(__file__).parents[1] / "control.py"
_CONTROL_SPEC = importlib.util.spec_from_file_location("candidate_proxy_control", _CONTROL_PATH)
assert _CONTROL_SPEC and _CONTROL_SPEC.loader
_CONTROL = importlib.util.module_from_spec(_CONTROL_SPEC)
sys.modules[_CONTROL_SPEC.name] = _CONTROL
_CONTROL_SPEC.loader.exec_module(_CONTROL)


def sanitize(payload: object):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    rewritten, note = _PROXY.sanitize_responses_body(raw)
    return json.loads(rewritten), note, raw, rewritten


class ReplayContract(unittest.TestCase):
    def test_runtime_status_reports_the_source_loaded_by_this_process(self):
        self.assertEqual(
            _PROXY.runtime_status()["source_sha256"],
            hashlib.sha256(_PROXY_PATH.read_bytes()).hexdigest(),
        )

    def test_loaded_source_identity_is_not_recomputed_at_health_check_time(self):
        original = _PROXY.LOADED_SOURCE_SHA256
        try:
            _PROXY.LOADED_SOURCE_SHA256 = "loaded-at-startup"
            self.assertEqual(_PROXY.source_sha256(), "loaded-at-startup")
        finally:
            _PROXY.LOADED_SOURCE_SHA256 = original

    def test_streaming_empty_response_exhaustion_returns_retryable_json_before_stream_starts(self):
        class Handler:
            def __init__(self):
                self.status = None
                self.headers = []
                self.wfile = BytesIO()

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers.append((name.lower(), value))

            def end_headers(self):
                pass

        handler = Handler()
        result = _PROXY.send_terminal_failure(
            handler,
            b'{"stream":true}',
            code="dmx_empty_response_exhausted",
            message="fixture upstream unavailable",
            attempts=4,
        )
        self.assertEqual(result, "json_error")
        self.assertEqual(handler.status, 503)
        self.assertIn(("content-type", "application/json"), handler.headers)
        self.assertIn(("retry-after", "3"), handler.headers)
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["error"]["type"], "upstream_unavailable")
        self.assertEqual(payload["error"]["code"], "dmx_empty_response_exhausted")

    def test_relay_maps_exhausted_streaming_477_to_retryable_json_before_stream_starts(self):
        class Handler:
            def __init__(self):
                self.path = "/v1/responses"
                self.headers = {"Content-Length": str(len(b'{"stream":true}'))}
                self.rfile = io.BytesIO(b'{"stream":true}')
                self.wfile = io.BytesIO()
                self.status = None
                self.sent_headers = []

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.sent_headers.append((name.lower(), value))

            def end_headers(self):
                pass

        original_urlopen = _PROXY._urlopen
        original_sleep = _PROXY.time.sleep
        attempts = 0
        try:
            def empty_response(*_args, **_kwargs):
                nonlocal attempts
                attempts += 1
                raise urllib.error.HTTPError(
                    "https://fixture.invalid/v1/responses",
                    477,
                    "empty response",
                    {},
                    io.BytesIO(
                        b'{"error":{"type":"dmx_api_error","code":"empty_response"}}'
                    ),
                )

            _PROXY._urlopen = empty_response
            _PROXY.time.sleep = lambda _seconds: None
            handler = Handler()
            _PROXY.Handler._relay(handler, "POST")
        finally:
            _PROXY._urlopen = original_urlopen
            _PROXY.time.sleep = original_sleep

        self.assertEqual(handler.status, 503)
        self.assertIn(("content-type", "application/json"), handler.sent_headers)
        self.assertIn(("retry-after", "3"), handler.sent_headers)
        self.assertNotIn(b"event: error", handler.wfile.getvalue())
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["error"]["code"], "dmx_empty_response_exhausted")
        self.assertEqual(attempts, 2)

    def test_opaque_agent_history_is_projected_to_standard_message_history(self):
        payload = {
            "stream": True,
            "prompt_cache_key": "stale-cache-key",
            "previous_response_id": "stale-response",
            "conversation": "stale-conversation",
            "include": ["reasoning.encrypted_content", "other.include"],
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Follow the policy."}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Earlier user context."}],
                },
                {
                    "type": "agent_message",
                    "content": [
                        {"type": "output_text", "text": "Opaque prior agent state."},
                        {"type": "encrypted_content", "encrypted_content": "opaque-fixture"},
                    ],
                },
                {"type": "custom_tool_call", "call_id": "call-1", "name": "fixture", "input": "{}"},
                {"type": "custom_tool_call_output", "call_id": "call-1", "output": "fixture"},
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Current user request."}],
                },
            ],
        }

        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))

        self.assertNotEqual(raw, rewritten)
        self.assertIn("compat_projection=True", note)
        self.assertIn("opaque_agent_messages=1", note)
        self.assertNotIn("prompt_cache_key", output)
        self.assertNotIn("previous_response_id", output)
        self.assertNotIn("conversation", output)
        self.assertEqual(output["include"], ["other.include"])
        self.assertEqual([item.get("role") for item in output["input"]], ["developer", "user", "user"])
        self.assertEqual(output["input"][-1]["content"][0]["text"], "Current user request.")
        self.assertFalse(any(item.get("type") == "agent_message" for item in output["input"]))
        self.assertNotIn(b"encrypted_content", rewritten)

    def test_compatibility_projection_preserves_a_current_user_request_when_budget_is_tight(self):
        payload = {
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "D" * 200}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Earlier" * 120}],
                },
                {
                    "type": "agent_message",
                    "content": [{"type": "encrypted_content", "encrypted_content": "opaque-fixture"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Current user request."}],
                },
            ]
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()

        projected, metrics = _PROXY._project_opaque_agent_history(raw, budget=220)

        self.assertIsNotNone(projected)
        self.assertIsNotNone(metrics)
        result = json.loads(projected)
        self.assertEqual(result["input"][-1]["content"][0]["text"], "Current user request.")
        self.assertFalse(any(item.get("type") == "agent_message" for item in result["input"]))
        self.assertLess(len(projected), len(raw))

    def test_compatibility_projection_uses_the_smallest_valid_request_when_current_user_exceeds_budget(self):
        payload = {
            "input": [
                {
                    "type": "agent_message",
                    "content": [{"type": "encrypted_content", "encrypted_content": "opaque-fixture"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Current user request is intentionally larger than the test budget."}],
                },
            ]
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()

        projected, metrics = _PROXY._project_opaque_agent_history(raw, budget=20)

        self.assertIsNotNone(projected)
        self.assertFalse(metrics["budget_met"])
        output = json.loads(projected)
        self.assertEqual(output["input"][0]["role"], "user")
        self.assertNotIn(b"encrypted_content", projected)

    def test_opaque_history_with_no_portable_user_message_preserves_legacy_surgical_repair(self):
        payload = {
            "input": [
                {
                    "type": "agent_message",
                    "content": [{"type": "encrypted_content", "encrypted_content": "opaque-fixture"}],
                }
            ]
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()

        rewritten, note = _PROXY.sanitize_responses_body(raw)

        self.assertEqual(rewritten, raw)
        self.assertEqual(note, "clean (nothing to strip)")

    def test_empty_response_cooldown_blocks_repeat_of_the_same_payload_without_upstream_call(self):
        class Handler:
            def __init__(self):
                self.path = "/v1/responses"
                self.headers = {"Content-Length": str(len(b'{"stream":true}'))}
                self.rfile = io.BytesIO(b'{"stream":true}')
                self.wfile = io.BytesIO()
                self.status = None
                self.sent_headers = []

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.sent_headers.append((name.lower(), value))

            def end_headers(self):
                pass

        _PROXY._reset_runtime_metrics_for_test()
        fingerprint = _PROXY._request_fingerprint(b'{"stream":true}')
        _PROXY._remember_empty_response_failure(fingerprint)
        original_urlopen = _PROXY._urlopen
        try:
            _PROXY._urlopen = lambda *_args, **_kwargs: self.fail("cooldown must prevent an upstream call")
            handler = Handler()
            _PROXY.Handler._relay(handler, "POST")
        finally:
            _PROXY._urlopen = original_urlopen
            _PROXY._reset_runtime_metrics_for_test()

        self.assertEqual(handler.status, 503)
        self.assertIn(("retry-after", str(_PROXY.EMPTY_RESPONSE_COOLDOWN_SECONDS)), handler.sent_headers)
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["error"]["code"], "dmx_empty_response_cooldown")

    def test_retiring_worker_stops_the_listener_without_rejecting_already_accepted_streams(self):
        class Server:
            def __init__(self):
                self.shutdown_calls = 0

            def shutdown(self):
                self.shutdown_calls += 1

        original_server = _PROXY._SERVER_INSTANCE
        original_active = _PROXY._ACTIVE_RESPONSES
        original_sleep = _PROXY.time.sleep
        try:
            server = Server()
            _PROXY._SERVER_INSTANCE = server
            _PROXY._ACTIVE_RESPONSES = 0
            _PROXY.time.sleep = lambda _seconds: self.fail("no wait is needed when no streams are active")
            _PROXY._retire_after_handoff()
        finally:
            _PROXY._SERVER_INSTANCE = original_server
            _PROXY._ACTIVE_RESPONSES = original_active
            _PROXY.time.sleep = original_sleep

        self.assertEqual(server.shutdown_calls, 1)

    def test_rolling_handoff_refuses_to_retire_when_replacement_is_not_ready(self):
        original_server = _PROXY._SERVER_INSTANCE
        original_retiring = _PROXY._RETIRING
        original_in_progress = _PROXY._HANDOFF_IN_PROGRESS
        original_spawn = _PROXY._spawn_replacement_listener
        try:
            _PROXY._SERVER_INSTANCE = object()
            _PROXY._RETIRING = False
            _PROXY._HANDOFF_IN_PROGRESS = False
            _PROXY._spawn_replacement_listener = lambda: None
            result = _PROXY._start_rolling_handoff()
        finally:
            _PROXY._SERVER_INSTANCE = original_server
            _PROXY._RETIRING = original_retiring
            _PROXY._HANDOFF_IN_PROGRESS = original_in_progress
            _PROXY._spawn_replacement_listener = original_spawn

        self.assertEqual(result, {"accepted": False, "reason": "replacement_not_ready"})
        self.assertFalse(_PROXY._is_retiring())

    def test_control_rolling_handoff_refuses_when_replacement_control_rejects(self):
        ctx = type("Ctx", (), {"port": 8791})()
        original = _CONTROL.common.verify_payload_manifest
        original_listeners = _CONTROL.common.verified_proxy_listener_pids
        original_urlopen = _CONTROL.urllib.request.OpenerDirector.open
        try:
            _CONTROL.common.verify_payload_manifest = lambda _ctx: (True, "ok")
            _CONTROL.common.verified_proxy_listener_pids = lambda _ctx: [12345]

            class Response:
                status = 202
                def read(self):
                    return b'{"accepted":false,"reason":"replacement_not_ready"}'
                def __enter__(self):
                    return self
                def __exit__(self, *_args):
                    return False

            _CONTROL.urllib.request.OpenerDirector.open = lambda *_args, **_kwargs: Response()
            with self.assertRaisesRegex(_CONTROL.common.InstallError, "replacement_not_ready"):
                _CONTROL.rolling_handoff(ctx, timeout_seconds=0.1)
        finally:
            _CONTROL.common.verify_payload_manifest = original
            _CONTROL.common.verified_proxy_listener_pids = original_listeners
            _CONTROL.urllib.request.OpenerDirector.open = original_urlopen

    def test_compatibility_projection_failure_is_not_silently_retried_as_opaque_history(self):
        class Handler:
            def __init__(self):
                self.path = "/v1/responses"
                self.headers = {"Content-Length": str(len(self.body))}
                self.rfile = io.BytesIO(self.body)
                self.wfile = io.BytesIO()
                self.status = None
                self.sent_headers = []

            body = json.dumps({
                "stream": True,
                "input": [
                    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Current request"}]},
                    {"type": "agent_message", "content": [{"type": "encrypted_content", "encrypted_content": "opaque-fixture"}]},
                ],
            }, separators=(",", ":")).encode()

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.sent_headers.append((name.lower(), value))

            def end_headers(self):
                pass

        attempted_bodies = []
        original_urlopen = _PROXY._urlopen
        original_sleep = _PROXY.time.sleep
        try:
            def empty_response(request, **_kwargs):
                attempted_bodies.append(request.data)
                raise urllib.error.HTTPError(
                    "https://fixture.invalid/v1/responses", 477, "empty response", {},
                    io.BytesIO(b'{"error":{"type":"dmx_api_error","code":"empty_response"}}'),
                )

            _PROXY._urlopen = empty_response
            _PROXY.time.sleep = lambda _seconds: None
            handler = Handler()
            _PROXY.Handler._relay(handler, "POST")
        finally:
            _PROXY._urlopen = original_urlopen
            _PROXY.time.sleep = original_sleep

        self.assertEqual(handler.status, 503)
        self.assertEqual(len(attempted_bodies), 2)
        for attempted in attempted_bodies:
            self.assertNotIn(b"encrypted_content", attempted)
            self.assertIn(b"Current request", attempted)

    def test_malformed_typed_encrypted_block_must_be_removed(self):
        payload = {"input": [{"type": "agent_message", "content": [{"type": "output_text", "text": "fixture"}, {"type": "encrypted_content"}]}]}
        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))
        self.assertNotEqual(raw, rewritten)
        self.assertIn("malformed_encrypted_blocks=1", note)
        self.assertEqual(output["input"][0]["content"], [{"type": "output_text", "text": "fixture"}])

    def test_valid_typed_encrypted_block_must_be_preserved(self):
        payload = {"input": [{"type": "agent_message", "content": [{"type": "encrypted_content", "encrypted_content": "opaque-fixture"}]}]}
        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))
        self.assertEqual(raw, rewritten)
        self.assertEqual(note, "clean (nothing to strip)")
        self.assertEqual(output, payload)

    def test_plain_payload_must_be_byte_equivalent(self):
        payload = {"input": [{"type": "user", "content": [{"type": "input_text", "text": "fixture"}]}]}
        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))
        self.assertEqual(raw, rewritten)
        self.assertEqual(note, "clean (nothing to strip)")
        self.assertEqual(output, payload)

    def test_top_level_reasoning_is_removed_but_agent_message_is_preserved(self):
        payload = {"input": [{"type": "reasoning", "encrypted_content": "provider-fixture"}, {"type": "agent_message", "content": [{"type": "encrypted_content", "encrypted_content": "agent-fixture"}]}]}
        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))
        self.assertNotEqual(raw, rewritten)
        self.assertIn("reasoning_items=1", note)
        self.assertEqual(output["input"], [{"type": "agent_message", "content": [{"type": "encrypted_content", "encrypted_content": "agent-fixture"}]}])

    def test_unknown_typed_content_is_left_unchanged(self):
        payload = {"input": [{"type": "agent_message", "content": [{"type": "future_encrypted_variant"}]}]}
        output, note, raw, rewritten = sanitize(copy.deepcopy(payload))
        self.assertEqual(raw, rewritten)
        self.assertEqual(note, "clean (nothing to strip)")
        self.assertEqual(output, payload)

    def test_sse_valid_encrypted_content_is_preserved(self):
        event = b'event: response.output_item.added\ndata: {"type":"agent_message","content":[{"type":"encrypted_content","encrypted_content":"opaque-fixture"}]}\n\n'
        rewritten, count = _PROXY.sanitize_sse_event(event)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, event)


if __name__ == "__main__":
    unittest.main()
