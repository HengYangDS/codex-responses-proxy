#!/usr/bin/env python3
"""Provider-portable request projection edge contracts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.replay import request as rewrite  # noqa: E402


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class ProviderPortableRequestEdgeTests(unittest.TestCase):
    def test_preserves_supported_optional_portable_shapes(self) -> None:
        raw = _body(
            {
                "input": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "refusal", "refusal": "cannot comply"}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": "https://example.test/image.png",
                                "detail": "original",
                            }
                        ],
                    },
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "lookup",
                        "arguments": "{}",
                        "caller": {"type": "direct"},
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": None,
                        "encrypted_content": "provider-bound",
                        "caller": {"type": "program", "caller_id": "planner"},
                    },
                ]
            }
        )

        _projection = rewrite.sanitize_responses_body(raw)
        projected_raw = _projection.body
        note = _projection.diagnostic()

        self.assertIsNotNone(projected_raw, note)
        projected = json.loads(cast("bytes", projected_raw))
        message, image_message, call, output = projected["input"]
        self.assertEqual(message["content"], "cannot comply")
        self.assertEqual(image_message["content"][0]["detail"], "original")
        self.assertEqual(call["caller"], {"type": "direct"})
        self.assertEqual(output["caller"], {"type": "program", "caller_id": "planner"})
        self.assertEqual(
            output["output"],
            [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )
        self.assertNotIn("provider-bound", cast("bytes", projected_raw).decode())

    def test_projects_root_only_ciphertext_to_explicit_portable_markers(self) -> None:
        raw = _body(
            {
                "input": [
                    {
                        "type": "agent_message",
                        "author": "planner",
                        "recipient": "user",
                        "content": [],
                        "encrypted_content": "agent-secret",
                    },
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "lookup",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": [],
                        "encrypted_content": "tool-secret",
                    },
                ]
            }
        )

        _projection = rewrite.sanitize_responses_body(raw)
        projected_raw = _projection.body
        note = _projection.diagnostic()

        self.assertIsNotNone(projected_raw, note)
        agent, _call, output = json.loads(cast("bytes", projected_raw))["input"]
        header, marker = agent["content"].split("\n", 1)
        self.assertEqual(
            json.loads(header),
            {"type": "agent_message", "author": "planner", "recipient": "user"},
        )
        self.assertEqual(marker, rewrite.OPAQUE_CONTENT_MARKER)
        self.assertEqual(
            output["output"],
            [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )
        self.assertIn("encrypted_blocks=2", note)
        self.assertIn("omission_markers=2", note)

        for content in ("", None):
            with self.subTest(root_only_agent_content=content):
                _projection = rewrite.sanitize_responses_body(
                    _body(
                        {
                            "input": [
                                {
                                    "type": "agent_message",
                                    "author": "planner",
                                    "recipient": "user",
                                    "content": content,
                                    "encrypted_content": "agent-secret",
                                }
                            ]
                        }
                    )
                )
                projected_raw = _projection.body
                note = _projection.diagnostic()
                self.assertIsNotNone(projected_raw, note)
                projected = json.loads(cast("bytes", projected_raw))["input"][0]
                self.assertTrue(projected["content"].endswith(rewrite.OPAQUE_CONTENT_MARKER))


if __name__ == "__main__":
    unittest.main(verbosity=2)
