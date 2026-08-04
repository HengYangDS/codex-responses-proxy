"""Provider-portable request projection edge contracts."""

from __future__ import annotations

import json
from pathlib import Path

from codex_responses_proxy.protocol import request as rewrite

ROOT = Path(__file__).resolve().parents[2]


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class ProviderPortableRequestEdgeTests:
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

        assert projected_raw is not None, note
        projected = json.loads(projected_raw)
        message, image_message, call, output = projected["input"]
        assert message["content"] == "cannot comply"
        assert image_message["content"][0]["detail"] == "original"
        assert call["caller"] == {"type": "direct"}
        assert output["caller"] == {"type": "program", "caller_id": "planner"}
        assert output["output"] == [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}]
        assert "provider-bound" not in projected_raw.decode()

    def test_projects_root_only_ciphertext_to_explicit_portable_markers(self, subtests) -> None:
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

        assert projected_raw is not None, note
        agent, _call, output = json.loads(projected_raw)["input"]
        header, marker = agent["content"].split("\n", 1)
        assert json.loads(header) == {
            "type": "agent_message",
            "author": "planner",
            "recipient": "user",
        }
        assert marker == rewrite.OPAQUE_CONTENT_MARKER
        assert output["output"] == [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}]
        assert "encrypted_blocks=2" in note
        assert "omission_markers=2" in note

        for content in ("", None):
            with subtests.test(root_only_agent_content=content):
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
                assert projected_raw is not None, note
                projected = json.loads(projected_raw)["input"][0]
                assert projected["content"].endswith(rewrite.OPAQUE_CONTENT_MARKER)
