#!/usr/bin/env python3
"""Pure proxy payload, retry-policy, runtime identity, and logging contracts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.compatibility import response_failed  # noqa: E402
from codex_dmx_proxy.listener import rewrite  # noqa: E402
from codex_dmx_proxy.listener import state  # noqa: E402
from tests.support.repository_fixtures import assert_private_log_mode  # noqa: E402


def _body(input_items, **extra):
    return json.dumps({"input": input_items, **extra}, separators=(",", ":")).encode()


def _message(role, content):
    return {"type": "message", "role": role, "content": content}


def _call(kind, call_id, payload):
    key = "arguments" if kind == "function_call" else "input"
    name = "wait" if kind == "function_call" else "exec"
    return {"type": kind, "call_id": call_id, "name": name, key: payload}


def _output(kind, call_id, payload):
    return {"type": kind, "call_id": call_id, "output": payload}


class TestProxySanitize(unittest.TestCase):
    """Verify the packaged proxy's core stripping logic still works."""

    def setUp(self):
        from codex_dmx_proxy.listener import entrypoint as p

        self.p = p
        state.reset_for_test()

    def assert_rejected(self, function, fixtures):
        for raw, budget in fixtures:
            with self.subTest(raw=raw, budget=budget):
                self.assertEqual(function(raw, budget), (None, None))

    def assert_compacted(self, compact: bytes | None, detail: Mapping[str, object] | None):
        """Narrow a successful compaction result for contract assertions."""
        self.assertIsNotNone(compact)
        self.assertIsNotNone(detail)
        return cast("bytes", compact), cast("Mapping[str, object]", detail)

    def test_strips_reasoning_and_encrypted(self):
        body = _body(
            [
                {"type": "reasoning", "encrypted_content": "gAAAA_secret"},
                {"type": "message", "role": "user", "content": "hello"},
            ],
            include=["reasoning.encrypted_content", "other"],
        )
        out, _ = rewrite.sanitize_responses_body(body)
        obj = json.loads(cast("bytes", out))
        self.assertEqual(obj["input"], [{"type": "message", "role": "user", "content": "hello"}])
        self.assertNotIn("reasoning.encrypted_content", obj["include"])

    def test_projects_agent_message_and_removes_encrypted_content(self):
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "reasoning",
                        "encrypted_content": "gAAAA_replay_only",
                    },
                    {
                        "type": "agent_message",
                        "author": "agent",
                        "recipient": "user",
                        "content": [
                            {"type": "input_text", "text": "reply"},
                            {
                                "type": "encrypted_content",
                                "encrypted_content": "required_agent_message_payload",
                            },
                        ],
                    },
                ],
                "include": ["reasoning.encrypted_content", "other"],
            }
        ).encode()

        out, note = rewrite.sanitize_responses_body(body)
        obj = json.loads(cast("bytes", out))

        self.assertEqual(len(obj["input"]), 1)  # replayed reasoning still dropped
        agent = obj["input"][0]
        self.assertEqual((agent["role"], agent["phase"]), ("assistant", "commentary"))
        header, content = agent["content"].split("\n", 1)
        self.assertEqual(
            json.loads(header),
            {"type": "agent_message", "author": "agent", "recipient": "user"},
        )
        self.assertEqual(content, "reply")
        self.assertNotIn("required_agent_message_payload", cast("bytes", out).decode())
        self.assertIn("encrypted_blocks=1", note)
        self.assertIn("reasoning_items=1", note)
        self.assertNotIn("reasoning.encrypted_content", obj["include"])

    def test_removes_all_agent_ciphertext_blocks(self):
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "agent_message",
                        "author": "agent",
                        "recipient": "user",
                        "content": [
                            {"type": "input_text", "text": "before"},
                            {"type": "encrypted_content"},
                            {
                                "type": "encrypted_content",
                                "encrypted_content": "valid_required_payload",
                            },
                            {"type": "input_text", "text": "after"},
                        ],
                    }
                ],
            }
        ).encode()

        out, note = rewrite.sanitize_responses_body(body)
        obj = json.loads(cast("bytes", out))

        self.assertIn("encrypted_blocks=2", note)
        _header, content = obj["input"][0]["content"].split("\n", 1)
        self.assertEqual(content, "beforeafter")
        self.assertNotIn("valid_required_payload", cast("bytes", out).decode())

    def test_rejects_unknown_fields_that_resemble_encrypted_content(self):
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "custom_tool_call",
                        "payload": {"type": "encrypted_content"},
                    }
                ],
            }
        ).encode()

        out, note = rewrite.sanitize_responses_body(body)

        self.assertIsNone(out)
        self.assertEqual(note, "rejected unknown_call_field")

    def test_sanitize_sse_event_strips_reasoning_and_agent_ciphertext(self):
        raw = (
            b"event: response.completed\n"
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"replay","id":"r"},'
            b'{"type":"agent_message","content":[{"type":"encrypted_content",'
            b'"encrypted_content":"required"}]}'
            b"]}}\n\n"
        )
        out, removed = rewrite.sanitize_sse_event(raw)
        event = json.loads(out.split(b"data: ", 1)[1])
        output = event["response"]["output"]
        self.assertEqual(removed, 2)
        self.assertNotIn("encrypted_content", output[0])
        self.assertEqual(
            output[1]["content"],
            [{"type": "output_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )

    def test_retry_disposition_classifies_gateway_and_terminal_failures(self):
        cases = (
            (524, b"gateway timeout", "full"),
            (477, b'{"error":{"type":"dmx_api_error","code":"empty_response"}}', "full"),
            (477, b'{"error":"unprocessable"}', ""),
            (477, b'{"error":{"type":"other_gateway","code":"empty_response"}}', ""),
            (400, b'{"error":{"code":"response_failed"}}', "full"),
            (418, b"teapot", ""),
            (400, b"invalid_encrypted_content", ""),
            (400, b"could not be verified", ""),
            (400, b'{"code":"invalid_prompt"} request blocked', "full"),
            (400, b"invalid_payload", "once"),
            (400, b"does not match the expected schema", "once"),
        )
        for status, payload, expected in cases:
            with self.subTest(status=status, payload=payload):
                self.assertEqual(response_failed.retry_disposition(status, payload), expected)
        self.assertEqual(json.loads(response_failed.exhausted_payload(4))["error"]["attempts"], 4)

    def test_response_failed_compaction_keeps_complete_tool_pairs_and_latest_user(self):
        """Fallback removes only an old prefix; no retained output is orphaned."""
        body = _body(
            [
                _message("user", "old" + "x" * 300_000),
                _call("custom_tool_call", "custom-1", "{}"),
                _output("custom_tool_call_output", "custom-1", "y" * 300_000),
                _call("function_call", "function-1", "{}"),
                _output("function_call_output", "function-1", "done"),
                _message("user", "latest user context must survive"),
            ],
            prompt_cache_key="cache-key-must-not-reach-the-fallback",
        )

        compact, detail = response_failed.compact_request(body)

        compact, detail = self.assert_compacted(compact, detail)
        self.assertGreaterEqual(detail["removed_inputs"], 1)
        self.assertLessEqual(len(compact), response_failed.COMPACTION_BUDGET)
        obj = json.loads(compact)
        self.assertNotIn("prompt_cache_key", obj)
        self.assertEqual(obj["input"][-1]["content"], "latest user context must survive")
        calls = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call", "function_call")
        }
        outputs = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call_output", "function_call_output")
        }
        self.assertTrue(outputs.issubset(calls))
        self.assertIn("function-1", calls)

    def test_response_failed_compaction_never_starts_at_an_orphaned_tool_output(self):
        body = _body(
            [
                _message("user", "old" + "x" * 10_000),
                _call("custom_tool_call", "custom-oversize", "{}"),
                _output("custom_tool_call_output", "custom-oversize", "y" * 600_000),
                _message("user", "newest user context"),
            ]
        )

        compact, detail = response_failed.compact_request(body)

        compact, detail = self.assert_compacted(compact, detail)
        self.assertEqual(detail["removed_inputs"], 3)
        obj = json.loads(compact)
        self.assertEqual(obj["input"], [_message("user", "newest user context")])

    def test_response_failed_compaction_reduces_an_already_sub_budget_failure(self):
        body = _body(
            [
                _message("user", "old" + "x" * 280_000),
                _message("user", "latest user context"),
                _call("custom_tool_call", "latest-call", "{}"),
                _output("custom_tool_call_output", "latest-call", "y" * 180_000),
            ],
            prompt_cache_key="stale-full-history-key",
        )
        self.assertLess(len(body), response_failed.COMPACTION_BUDGET)

        compact, detail = response_failed.compact_request(body)

        compact, detail = self.assert_compacted(compact, detail)
        self.assertLessEqual(len(compact), len(body) // 2)
        self.assertEqual(detail["removed_inputs"], 1)
        self.assertNotIn("prompt_cache_key", json.loads(compact))

    def test_response_failed_compaction_uses_smallest_safe_suffix_when_budget_is_impossible(self):
        body = _body(
            [
                _message("user", "old context"),
                _message("user", "latest user context"),
                _call("custom_tool_call", "latest-call", "{}"),
                _output("custom_tool_call_output", "latest-call", "y" * 220_000),
            ]
        )

        compact, detail = response_failed.compact_request(body, budget=20_000)

        compact, detail = self.assert_compacted(compact, detail)
        self.assertFalse(detail["budget_met"])
        self.assertLess(len(compact), len(body))
        obj = json.loads(compact)
        self.assertEqual(obj["input"][0]["content"], "latest user context")
        self.assertTrue(response_failed.tool_pair_boundary_is_safe(obj["input"], 0))

    def test_response_failed_compaction_is_a_noop_when_no_safe_suffix_fits(self):
        body = _body(
            [_message("user", "newest user context")],
            tools=[{"type": "function", "name": "huge", "parameters": "x" * 600_000}],
            prompt_cache_key="must-remain-on-original-request",
        )

        compact, detail = response_failed.compact_request(body)

        self.assertIsNone(compact)
        self.assertIsNone(detail)
        self.assertEqual(json.loads(body)["prompt_cache_key"], "must-remain-on-original-request")

    def test_response_failed_dialogue_recovery_keeps_latest_context_without_tool_replay(self):
        body = _body(
            [
                _message("developer", "old policy"),
                _message("user", "old request"),
                _call("custom_tool_call", "old", "{}"),
                _output("custom_tool_call_output", "old", "old result"),
                _message("developer", "current policy"),
                _message("user", "intermediate request"),
                _message("user", "latest user request"),
                _call("custom_tool_call", "new", "{}"),
                _output("custom_tool_call_output", "new", "large" + "x" * 100_000),
            ],
            prompt_cache_key="stale-full-history-key",
        )

        recovery, detail = response_failed.recover_dialogue(body)

        recovery, detail = self.assert_compacted(recovery, detail)
        recovered = json.loads(recovery)
        self.assertNotIn("prompt_cache_key", recovered)
        self.assertEqual(
            recovered["input"],
            [_message("developer", "current policy"), _message("user", "latest user request")],
        )
        self.assertEqual(detail["dropped_input_items"], 7)
        self.assertLess(len(recovery), len(body))

    def test_response_failed_dialogue_recovery_allows_current_user_without_instruction(self):
        body = _body(
            [
                _message("user", "old request"),
                _message("assistant", "old response"),
                _message("user", "latest user request"),
                _call("custom_tool_call", "new", "{}"),
                _output("custom_tool_call_output", "new", "large" + "x" * 100_000),
            ]
        )

        recovery, detail = response_failed.recover_dialogue(body)

        recovery, detail = self.assert_compacted(recovery, detail)
        self.assertEqual(
            json.loads(recovery)["input"],
            [_message("user", "latest user request")],
        )
        self.assertEqual(detail["retained_messages"], 1)

    def test_source_tree_without_an_installed_manifest_has_no_release_claim(self):
        self.assertEqual(self.p.release_version(), "0+unknown")

    def test_runtime_status_reports_loaded_serving_payload_sha256(self):
        identity = self.p.runtime_status()["serving_payload_sha256"]
        if self.p._LOADED_PAYLOAD is None:
            self.assertIsNone(identity)
        else:
            self.assertEqual(identity, self.p._LOADED_PAYLOAD.serving_payload_sha256)

    def test_log_redacts_secrets_limits_line_length_and_removes_query_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            old_log_path = state.LOG_PATH
            state.LOG_PATH = str(log_path)
            try:
                state.log(
                    "authorization: Bearer super-secret-token "
                    "encrypted=gAAAA_replay_secret "
                    "x" * 2048
                )
                state.log(f"path={state.safe_request_path('/v1/responses?prompt=private')}")
            finally:
                state.LOG_PATH = old_log_path

            text = log_path.read_text(encoding="utf-8")
            mode = log_path.stat().st_mode & 0o777
        self.assertNotIn("super-secret-token", text)
        self.assertNotIn("gAAAA_replay_secret", text)
        self.assertNotIn("prompt=private", text)
        self.assertIn("[redacted]", text)
        self.assertIn("path=/v1/responses", text)
        assert_private_log_mode(self, mode)
        self.assertLessEqual(
            max(len(line.encode("utf-8")) for line in text.splitlines()),
            state.LOG_LINE_MAX_BYTES + 96,
        )

    def test_log_rotation_discards_an_oversized_legacy_segment_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            log_path.write_bytes(b"x" * 8192)
            old_log_path = state.LOG_PATH
            old_max = state.LOG_MAX_BYTES
            old_backups = state.LOG_BACKUP_COUNT
            state.LOG_PATH = str(log_path)
            state.LOG_MAX_BYTES = 4096
            state.LOG_BACKUP_COUNT = 1
            try:
                state.log("event=rotation_probe")
            finally:
                state.LOG_PATH = old_log_path
                state.LOG_MAX_BYTES = old_max
                state.LOG_BACKUP_COUNT = old_backups

            self.assertTrue(log_path.exists())
            self.assertLessEqual(log_path.stat().st_size, 4096)
            self.assertFalse((Path(tmp) / "proxy.log.1").exists())
            self.assertIn(
                "log_retention_discarded_oversized_bytes=8192", log_path.read_text(encoding="utf-8")
            )

    def test_fail_closed_on_non_json(self):
        raw = b"not json at all"
        out, note = rewrite.sanitize_responses_body(raw)
        self.assertIsNone(out)
        self.assertEqual(note, "rejected invalid_json")

    def test_fail_closed_on_json_values_that_are_not_response_objects(self):
        for raw in (b"[]", b"null", b'"text"'):
            with self.subTest(raw=raw):
                out, note = rewrite.sanitize_responses_body(raw)
                self.assertIsNone(out)
                self.assertEqual(note, "rejected request_not_object")

    def test_sse_sanitizer_passes_non_json_and_non_target_events_unchanged(self):
        events = (
            b"data: [DONE]\n\n",
            b'data: {"encrypted_content":\n\n',
            b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
        )
        for raw in events:
            with self.subTest(raw=raw):
                self.assertEqual(rewrite.sanitize_sse_event(raw), (raw, 0))

    def test_request_sanitizer_fails_closed_when_mutation_cannot_be_serialized(self):
        raw = (
            b'{"input":[{"type":"reasoning","encrypted_content":"opaque"},'
            b'{"type":"message","role":"user","content":"continue"}]}'
        )
        with mock.patch.object(rewrite.json, "dumps", side_effect=TypeError("unsupported")):
            out, note = rewrite.sanitize_responses_body(raw)
        self.assertIsNone(out)
        self.assertEqual(note, "rejected serialization_failed")

    def test_sse_sanitizer_fails_open_when_mutation_cannot_be_serialized(self):
        raw = (
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"opaque"}]}}\n\n'
        )
        with mock.patch.object(rewrite.json, "dumps", side_effect=TypeError("unsupported")):
            self.assertEqual(rewrite.sanitize_sse_event(raw), (raw, 0))

    def test_deep_request_fails_closed_and_sse_projection_remains_atomic(self):
        nested = '{"x":' * 496 + "0" + "}" * 496
        request = ('{"input":[{"type":"message","role":"user","content":' + nested + "}]}").encode()
        projected, note = rewrite.sanitize_responses_body(request)
        self.assertIsNone(projected)
        self.assertTrue(note.startswith("rejected "), note)

        event = (
            "data: "
            + '{"x":' * 997
            + '{"type":"reasoning","encrypted_content":"opaque"}'
            + "}" * 997
            + "\n\n"
        ).encode()
        self.assertEqual(rewrite.sanitize_sse_event(event), (event, 0))

    def test_response_failed_pair_boundary_ignores_non_object_items(self):
        items: list[object] = [
            1,
            {"type": "function_call_output", "call_id": "missing", "output": "x"},
        ]
        self.assertFalse(response_failed.tool_pair_boundary_is_safe(items, 0))
        self.assertTrue(response_failed.tool_pair_boundary_is_safe(items, 2))

    def test_response_failed_rejects_invalid_compaction_and_recovery_boundaries(self):
        common = ((b"not-json", None), (b"[]", None), (b'{"input":[]}', None))
        self.assert_rejected(
            response_failed.compact_request,
            (*common, (b'{"input":[1,2]}', None), (b'{"input":[{},{}]}', 0)),
        )
        valid = _body([_message("user", "old"), _message("user", "current")])
        self.assert_rejected(
            response_failed.recover_dialogue,
            (
                *common,
                (b'{"input":[{"type":"message","role":"developer","content":"x"}]}', None),
                (valid, 0),
                (valid, 1),
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
