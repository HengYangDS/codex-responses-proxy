#!/usr/bin/env python3
"""Provider-portable stream projection contracts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.replay import response as rewrite  # noqa: E402


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class ProviderPortableStreamTests(unittest.TestCase):
    def _event(self, item: object) -> bytes:
        return b"event: response.output_item.added\n" + b"data: " + _body({"item": item}) + b"\n\n"

    def test_removes_agent_ciphertext_and_preserves_plaintext(self) -> None:
        event = self._event(
            {
                "type": "agent_message",
                "content": [
                    {"type": "encrypted_content", "encrypted_content": "agent-secret"},
                    {"type": "output_text", "text": "visible"},
                ],
            }
        )

        rewritten, removed = rewrite.sanitize_sse_event(event)

        self.assertEqual(removed, 1)
        self.assertNotIn(b"agent-secret", rewritten)
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        self.assertEqual(payload["item"]["content"], [{"type": "output_text", "text": "visible"}])

    def test_marks_encrypted_only_tool_output(self) -> None:
        event = self._event(
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": [{"type": "encrypted_content", "encrypted_content": "tool-secret"}],
            }
        )

        rewritten, removed = rewrite.sanitize_sse_event(event)

        self.assertEqual(removed, 1)
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        self.assertEqual(
            payload["item"]["output"],
            [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )

    def test_marks_encrypted_only_agent_output_with_output_text(self) -> None:
        event = self._event(
            {
                "type": "agent_message",
                "content": [{"type": "encrypted_content", "encrypted_content": "agent-secret"}],
            }
        )

        rewritten, removed = rewrite.sanitize_sse_event(event)

        self.assertEqual(removed, 1)
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        self.assertEqual(
            payload["item"]["content"],
            [{"type": "output_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )

    def test_removes_root_ciphertext_with_non_block_content(self) -> None:
        cases = (
            {
                "type": "agent_message",
                "content": "visible",
                "encrypted_content": "agent-secret",
            },
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "visible",
                "encrypted_content": "tool-secret",
            },
        )
        for item in cases:
            with self.subTest(item_type=item["type"]):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                self.assertEqual(removed, 1)
                self.assertNotIn(b"secret", rewritten)

    def test_marks_root_only_ciphertext_in_nested_and_item_events(self) -> None:
        cases = (
            (
                self._event(
                    {
                        "type": "agent_message",
                        "content": [],
                        "encrypted_content": "agent-secret",
                    }
                ),
                "content",
                "output_text",
            ),
            (
                b"event: response.completed\n"
                + b"data: "
                + _body(
                    {
                        "response": {
                            "output": [
                                {
                                    "type": "function_call_output",
                                    "call_id": "c1",
                                    "output": None,
                                    "encrypted_content": "tool-secret",
                                }
                            ]
                        }
                    }
                )
                + b"\n\n",
                "output",
                "input_text",
            ),
        )
        for event, field, block_type in cases:
            with self.subTest(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(event)
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                item = payload.get("item") or payload["response"]["output"][0]
                self.assertEqual(removed, 1)
                self.assertEqual(
                    item[field],
                    [{"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}],
                )

    def test_marks_ciphertext_when_only_empty_text_blocks_remain(self) -> None:
        cases = (
            (
                {
                    "type": "agent_message",
                    "content": [
                        {"type": "output_text", "text": ""},
                        {"type": "encrypted_content", "encrypted_content": "agent-secret"},
                    ],
                },
                "content",
                "output_text",
            ),
            (
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": [
                        {"type": "input_text", "text": ""},
                        {"type": "encrypted_content", "encrypted_content": "tool-secret"},
                    ],
                },
                "output",
                "input_text",
            ),
            (
                {
                    "type": "agent_message",
                    "content": [
                        {"type": "refusal", "refusal": ""},
                        {"type": "encrypted_content", "encrypted_content": "agent-secret"},
                    ],
                },
                "content",
                "output_text",
            ),
        )
        for item, field, block_type in cases:
            with self.subTest(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                self.assertEqual(removed, 1)
                self.assertEqual(
                    payload["item"][field],
                    [{"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}],
                )

    def test_marks_root_ciphertext_when_content_has_only_empty_text_blocks(self) -> None:
        cases = (
            (
                {
                    "type": "agent_message",
                    "content": [{"type": "output_text", "text": ""}],
                    "encrypted_content": "agent-secret",
                },
                "content",
                "output_text",
            ),
            (
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": [{"type": "input_text", "text": ""}],
                    "encrypted_content": "tool-secret",
                },
                "output",
                "input_text",
            ),
        )
        for item, field, block_type in cases:
            with self.subTest(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                self.assertEqual(removed, 1)
                self.assertEqual(
                    payload["item"][field],
                    [{"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}],
                )

    def test_sse_event_with_unrecognized_ciphertext_text_is_unchanged(self) -> None:
        event = self._event({"type": "message", "content": "encrypted_content"})

        rewritten, removed = rewrite.sanitize_sse_event(event)

        self.assertEqual((rewritten, removed), (event, 0))

    def test_projects_non_stream_response_with_the_same_ciphertext_rules(self) -> None:
        raw = _body(
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
            }
        )

        projected, removed = rewrite.sanitize_json_response(raw)

        self.assertEqual(removed, 2)
        self.assertNotIn(b"secret", projected)
        response = json.loads(projected)
        self.assertEqual(response["status"], "completed")
        self.assertNotIn("encrypted_content", response["output"][0])
        self.assertEqual(
            response["output"][1]["content"], [{"type": "output_text", "text": "visible"}]
        )

    def test_non_stream_response_requires_valid_terminal_json(self) -> None:
        invalid = (
            b"",
            b"not-json",
            _body([]),
            _body({"id": "resp_missing_status", "output": []}),
            _body({"id": "resp_running", "status": "in_progress", "output": []}),
            _body({"id": "resp_failed", "status": "failed", "output": []}),
        )

        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                rewrite.sanitize_json_response(raw)

    def test_non_stream_response_rejects_unproved_ciphertext_carriers(self) -> None:
        raw = _body(
            {
                "id": "resp_future",
                "status": "completed",
                "output": [
                    {
                        "type": "future_output_item",
                        "encrypted_content": "provider-secret",
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "unproved_provider_ciphertext"):
            rewrite.sanitize_json_response(raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
