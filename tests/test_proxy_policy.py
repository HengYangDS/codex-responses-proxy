#!/usr/bin/env python3
"""Pure proxy payload, retry-policy, runtime identity, and logging contracts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY_ROOT = ROOT / "proxy"
for entry in (str(ROOT), str(PROXY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import response_failed  # noqa: E402
import responses_rewrite  # noqa: E402
import runtime_state  # noqa: E402
from tests.support.repository_fixtures import assert_private_log_mode  # noqa: E402


class TestProxySanitize(unittest.TestCase):
    """Verify the packaged proxy's core stripping logic still works."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "proxy"))
        import dmx_responses_proxy as p

        self.p = p
        runtime_state.reset_for_test()

    def test_strips_reasoning_and_encrypted(self):
        body = json.dumps(
            {
                "input": [
                    {"type": "reasoning", "encrypted_content": "gAAAA_secret"},
                    {"type": "message", "content": "hello"},
                ],
                "include": ["reasoning.encrypted_content", "other"],
            }
        ).encode()
        out, note = responses_rewrite.sanitize_responses_body(body)
        obj = json.loads(out)
        self.assertEqual(len(obj["input"]), 1)  # reasoning dropped
        self.assertEqual(obj["input"][0]["type"], "message")
        self.assertNotIn("reasoning.encrypted_content", obj["include"])
        self.assertEqual(obj["input"], [{"type": "message", "content": "hello"}])

    def test_preserves_required_agent_message_encrypted_content(self):
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

        out, note = responses_rewrite.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertEqual(len(obj["input"]), 1)  # replayed reasoning still dropped
        encrypted = obj["input"][0]["content"][1]
        self.assertEqual(encrypted["type"], "encrypted_content")
        self.assertEqual(
            encrypted["encrypted_content"],
            "required_agent_message_payload",
        )
        self.assertIn("agent_message_encrypted=1", note)
        self.assertIn("malformed_encrypted_blocks=0", note)
        self.assertNotIn("reasoning.encrypted_content", obj["include"])

    def test_drops_only_legacy_encrypted_content_blocks_missing_payload(self):
        body = json.dumps(
            {
                "input": [
                    {
                        "type": "agent_message",
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

        out, note = responses_rewrite.sanitize_responses_body(body)
        obj = json.loads(out)

        self.assertIn("malformed_encrypted_blocks=1", note)
        self.assertEqual(
            obj["input"][0]["content"],
            [
                {"type": "input_text", "text": "before"},
                {
                    "type": "encrypted_content",
                    "encrypted_content": "valid_required_payload",
                },
                {"type": "input_text", "text": "after"},
            ],
        )

    def test_keeps_unrelated_encrypted_content_shape_outside_legacy_content_lists(self):
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

        out, note = responses_rewrite.sanitize_responses_body(body)

        self.assertEqual(out, body)
        self.assertIn("clean", note)

    def test_sanitize_sse_event_strips_reasoning_but_keeps_agent_message_payload(self):
        raw = (
            b"event: response.completed\n"
            b'data: {"type":"response.completed","response":{"output":['
            b'{"type":"reasoning","encrypted_content":"replay","id":"r"},'
            b'{"type":"agent_message","content":[{"type":"encrypted_content",'
            b'"encrypted_content":"required"}]}'
            b"]}}\n\n"
        )
        out, removed = responses_rewrite.sanitize_sse_event(raw)
        event = json.loads(out.split(b"data: ", 1)[1])
        output = event["response"]["output"]
        self.assertEqual(removed, 1)
        self.assertNotIn("encrypted_content", output[0])
        self.assertEqual(output[1]["content"][0]["encrypted_content"], "required")

    def test_retries_gateway_524_as_transient_upstream_failure(self):
        self.assertEqual(response_failed.retry_disposition(524, b"gateway timeout"), "full")

    def test_retries_dmx_empty_response_477_as_transient_upstream_failure(self):
        error = (
            b'{"error":{"message":"official provider returned an empty response",'
            b'"type":"dmx_api_error","code":"empty_response"}}'
        )
        self.assertEqual(response_failed.retry_disposition(477, error), "full")

    def test_does_not_retry_unrelated_477(self):
        self.assertEqual(response_failed.retry_disposition(477, b'{"error":"unprocessable"}'), "")
        self.assertEqual(
            response_failed.retry_disposition(
                477,
                b'{"error":{"type":"other_gateway","code":"empty_response"}}',
            ),
            "",
        )

    def test_retries_upstream_response_failed_400_once(self):
        error = (
            b'{"error":{"message":"OpenAI responses stream failed: '
            b'response_failed - Response failed",'
            b'"type":"new_api_error","code":"response_failed"}}'
        )
        self.assertEqual(response_failed.retry_disposition(400, error), "full")

    def test_response_failed_compaction_keeps_complete_tool_pairs_and_latest_user(self):
        """Fallback removes only an old prefix; no retained output is orphaned."""
        body = json.dumps(
            {
                "prompt_cache_key": "cache-key-must-not-reach-the-fallback",
                "input": [
                    {"type": "message", "role": "user", "content": "old" + "x" * 300_000},
                    {
                        "type": "custom_tool_call",
                        "call_id": "custom-1",
                        "name": "exec",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "custom-1",
                        "output": "y" * 300_000,
                    },
                    {
                        "type": "function_call",
                        "call_id": "function-1",
                        "name": "wait",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "function-1",
                        "output": "done",
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": "latest user context must survive",
                    },
                ],
            }
        ).encode()

        compact, detail = response_failed.compact_request(body)

        self.assertIsNotNone(compact)
        self.assertIsNotNone(detail)
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
        body = json.dumps(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "old" + "x" * 10_000},
                    {
                        "type": "custom_tool_call",
                        "call_id": "custom-oversize",
                        "name": "exec",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "custom-oversize",
                        "output": "y" * 600_000,
                    },
                    {"type": "message", "role": "user", "content": "newest user context"},
                ],
            }
        ).encode()

        compact, detail = response_failed.compact_request(body)

        self.assertIsNotNone(compact)
        self.assertEqual(detail["removed_inputs"], 3)
        obj = json.loads(compact)
        self.assertEqual(
            obj["input"],
            [
                {"type": "message", "role": "user", "content": "newest user context"},
            ],
        )

    def test_response_failed_compaction_keeps_latest_user_when_tool_work_follows_it(self):
        body = json.dumps(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "old" + "x" * 300_000},
                    {"type": "message", "role": "user", "content": "latest user context"},
                    {
                        "type": "custom_tool_call",
                        "call_id": "latest-call",
                        "name": "exec",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "latest-call",
                        "output": "y" * 300_000,
                    },
                ],
            }
        ).encode()

        compact, detail = response_failed.compact_request(body)

        self.assertIsNotNone(compact)
        self.assertEqual(detail["removed_inputs"], 1)
        obj = json.loads(compact)
        self.assertEqual(obj["input"][0]["content"], "latest user context")

    def test_response_failed_compaction_reduces_an_already_sub_budget_failure(self):
        body = json.dumps(
            {
                "prompt_cache_key": "stale-full-history-key",
                "input": [
                    {"type": "message", "role": "user", "content": "old" + "x" * 280_000},
                    {"type": "message", "role": "user", "content": "latest user context"},
                    {
                        "type": "custom_tool_call",
                        "call_id": "latest-call",
                        "name": "exec",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "latest-call",
                        "output": "y" * 180_000,
                    },
                ],
            }
        ).encode()
        self.assertLess(len(body), response_failed.COMPACTION_BUDGET)

        compact, detail = response_failed.compact_request(body)

        self.assertIsNotNone(compact)
        self.assertLessEqual(len(compact), len(body) // 2)
        self.assertEqual(detail["removed_inputs"], 1)
        self.assertNotIn("prompt_cache_key", json.loads(compact))

    def test_response_failed_compaction_uses_smallest_safe_suffix_when_budget_is_impossible(self):
        body = json.dumps(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "old context"},
                    {"type": "message", "role": "user", "content": "latest user context"},
                    {
                        "type": "custom_tool_call",
                        "call_id": "latest-call",
                        "name": "exec",
                        "input": "{}",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "latest-call",
                        "output": "y" * 220_000,
                    },
                ],
            }
        ).encode()

        compact, detail = response_failed.compact_request(body, budget=20_000)

        self.assertIsNotNone(compact)
        self.assertFalse(detail["budget_met"])
        self.assertLess(len(compact), len(body))
        obj = json.loads(compact)
        self.assertEqual(obj["input"][0]["content"], "latest user context")
        self.assertTrue(response_failed.tool_pair_boundary_is_safe(obj["input"], 0))

    def test_response_failed_compaction_is_a_noop_when_no_safe_suffix_fits(self):
        body = json.dumps(
            {
                "tools": [{"type": "function", "name": "huge", "parameters": "x" * 600_000}],
                "prompt_cache_key": "must-remain-on-original-request",
                "input": [
                    {"type": "message", "role": "user", "content": "newest user context"},
                ],
            }
        ).encode()

        compact, detail = response_failed.compact_request(body)

        self.assertIsNone(compact)
        self.assertIsNone(detail)
        self.assertEqual(json.loads(body)["prompt_cache_key"], "must-remain-on-original-request")

    def test_response_failed_dialogue_recovery_keeps_latest_context_without_tool_replay(self):
        body = json.dumps(
            {
                "prompt_cache_key": "stale-full-history-key",
                "input": [
                    {"type": "message", "role": "developer", "content": "old policy"},
                    {"type": "message", "role": "user", "content": "old request"},
                    {"type": "custom_tool_call", "call_id": "old", "name": "tool", "input": "{}"},
                    {"type": "custom_tool_call_output", "call_id": "old", "output": "old result"},
                    {"type": "message", "role": "developer", "content": "current policy"},
                    {"type": "message", "role": "user", "content": "intermediate request"},
                    {"type": "message", "role": "user", "content": "latest user request"},
                    {"type": "custom_tool_call", "call_id": "new", "name": "tool", "input": "{}"},
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "new",
                        "output": "large" + "x" * 100_000,
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()

        recovery, detail = response_failed.recover_dialogue(body)

        self.assertIsNotNone(recovery)
        self.assertIsNotNone(detail)
        recovered = json.loads(recovery)
        self.assertNotIn("prompt_cache_key", recovered)
        self.assertEqual(
            recovered["input"],
            [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": "latest user request"},
            ],
        )
        self.assertEqual(detail["dropped_input_items"], 7)
        self.assertLess(len(recovery), len(body))

    def test_response_failed_dialogue_recovery_allows_current_user_without_instruction(self):
        body = json.dumps(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "old request"},
                    {"type": "message", "role": "assistant", "content": "old response"},
                    {"type": "message", "role": "user", "content": "latest user request"},
                    {"type": "custom_tool_call", "call_id": "new", "name": "tool", "input": "{}"},
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "new",
                        "output": "large" + "x" * 100_000,
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()

        recovery, detail = response_failed.recover_dialogue(body)

        self.assertIsNotNone(recovery)
        self.assertIsNotNone(detail)
        self.assertEqual(
            json.loads(recovery)["input"],
            [{"type": "message", "role": "user", "content": "latest user request"}],
        )
        self.assertEqual(detail["retained_messages"], 1)

    def test_does_not_retry_unrelated_400(self):
        self.assertEqual(response_failed.retry_disposition(400, b'{"error":"bad request"}'), "")

    def test_runtime_server_version_uses_version_file(self):
        self.assertEqual(
            self.p.release_version(), Path(ROOT, "VERSION").read_text(encoding="utf-8").strip()
        )

    def test_runtime_status_reports_loaded_serving_payload_sha256(self):
        identity = self.p.runtime_status()["serving_payload_sha256"]
        if self.p._LOADED_PAYLOAD is None:
            self.assertIsNone(identity)
        else:
            self.assertEqual(identity, self.p._LOADED_PAYLOAD.serving_payload_sha256)

    def test_runtime_status_reports_protocol_v2_process_identity(self):
        status = self.p.runtime_status()
        self.assertEqual(status["handoff_protocol_version"], 2)
        self.assertEqual(status["pid"], os.getpid())
        self.assertEqual(status["handoff_state"], "idle")
        self.assertIsNone(status["handoff_transaction_id"])
        self.assertIs(status["accepting"], True)
        self.assertIs(status["draining"], False)

    def test_log_redacts_secrets_limits_line_length_and_removes_query_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            old_log_path = runtime_state.LOG_PATH
            runtime_state.LOG_PATH = str(log_path)
            try:
                runtime_state.log(
                    "authorization: Bearer super-secret-token "
                    "encrypted=gAAAA_replay_secret "
                    "x" * 2048
                )
                runtime_state.log(
                    f"path={runtime_state.safe_request_path('/v1/responses?prompt=private')}"
                )
            finally:
                runtime_state.LOG_PATH = old_log_path

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
            runtime_state.LOG_LINE_MAX_BYTES + 96,
        )

    def test_log_rotation_discards_an_oversized_legacy_segment_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "proxy.log"
            log_path.write_bytes(b"x" * 8192)
            old_log_path = runtime_state.LOG_PATH
            old_max = runtime_state.LOG_MAX_BYTES
            old_backups = runtime_state.LOG_BACKUP_COUNT
            runtime_state.LOG_PATH = str(log_path)
            runtime_state.LOG_MAX_BYTES = 4096
            runtime_state.LOG_BACKUP_COUNT = 1
            try:
                runtime_state.log("event=rotation_probe")
            finally:
                runtime_state.LOG_PATH = old_log_path
                runtime_state.LOG_MAX_BYTES = old_max
                runtime_state.LOG_BACKUP_COUNT = old_backups

            self.assertTrue(log_path.exists())
            self.assertLessEqual(log_path.stat().st_size, 4096)
            self.assertFalse((Path(tmp) / "proxy.log.1").exists())
            self.assertIn(
                "log_retention_discarded_oversized_bytes=8192", log_path.read_text(encoding="utf-8")
            )

    def test_fail_open_on_non_json(self):
        raw = b"not json at all"
        out, note = responses_rewrite.sanitize_responses_body(raw)
        self.assertEqual(out, raw)  # unchanged
        self.assertIn("passthrough", note)

    def test_clean_body_untouched(self):
        body = json.dumps({"input": [{"type": "message", "content": "hi"}]}).encode()
        out, note = responses_rewrite.sanitize_responses_body(body)
        self.assertIn("clean", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
