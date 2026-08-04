"""Provider-portable stream projection contracts."""

from __future__ import annotations

import json
from pathlib import Path

from codex_responses_proxy.protocol import request as request_projection
from codex_responses_proxy.protocol import response as rewrite
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class ProviderPortableStreamTests:
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

        assert removed == 1
        assert b"agent-secret" not in rewritten
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        assert payload["item"]["content"] == [{"type": "output_text", "text": "visible"}]

    def test_marks_encrypted_only_tool_output(self) -> None:
        event = self._event(
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": [{"type": "encrypted_content", "encrypted_content": "tool-secret"}],
            }
        )

        rewritten, removed = rewrite.sanitize_sse_event(event)

        assert removed == 1
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        assert payload["item"]["output"] == [
            {"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}
        ]

    def test_marks_encrypted_only_agent_output_with_output_text(self) -> None:
        event = self._event(
            {
                "type": "agent_message",
                "content": [{"type": "encrypted_content", "encrypted_content": "agent-secret"}],
            }
        )

        rewritten, removed = rewrite.sanitize_sse_event(event)

        assert removed == 1
        payload = json.loads(
            next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
        )
        assert payload["item"]["content"] == [
            {"type": "output_text", "text": rewrite.OPAQUE_CONTENT_MARKER}
        ]

    def test_removes_root_ciphertext_with_non_block_content(self, subtests) -> None:
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
            with subtests.test(item_type=item["type"]):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                assert removed == 1
                assert b"secret" not in rewritten

    def test_marks_root_only_ciphertext_in_nested_and_item_events(self, subtests) -> None:
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
            with subtests.test(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(event)
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                item = payload.get("item") or payload["response"]["output"][0]
                assert removed == 1
                assert item[field] == [{"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}]

    def test_marks_ciphertext_when_only_empty_text_blocks_remain(self, subtests) -> None:
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
            with subtests.test(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                assert removed == 1
                assert payload["item"][field] == [
                    {"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}
                ]

    def test_marks_root_ciphertext_when_content_has_only_empty_text_blocks(self, subtests) -> None:
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
            with subtests.test(field=field):
                rewritten, removed = rewrite.sanitize_sse_event(self._event(item))
                payload = json.loads(
                    next(line[6:] for line in rewritten.splitlines() if line.startswith(b"data: "))
                )
                assert removed == 1
                assert payload["item"][field] == [
                    {"type": block_type, "text": rewrite.OPAQUE_CONTENT_MARKER}
                ]

    def test_sse_event_with_unrecognized_ciphertext_text_is_unchanged(self) -> None:
        event = self._event({"type": "message", "content": "encrypted_content"})

        rewritten, removed = rewrite.sanitize_sse_event(event)

        assert (rewritten, removed) == (event, 0)

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

        assert removed == 2
        assert b"secret" not in projected
        response = json.loads(projected)
        assert response["status"] == "completed"
        assert "encrypted_content" not in response["output"][0]
        assert response["output"][1]["content"] == [{"type": "output_text", "text": "visible"}]

    def test_non_stream_response_requires_valid_terminal_json(self, subtests) -> None:
        invalid = (
            b"",
            b"not-json",
            _body([]),
            _body({"id": "resp_missing_status", "output": []}),
            _body({"id": "resp_running", "status": "in_progress", "output": []}),
            _body({"id": "resp_failed", "status": "failed", "output": []}),
        )

        for raw in invalid:
            with subtests.test(raw=raw), pytest.raises(ValueError):
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

        with pytest.raises(ValueError, match="unproved_provider_ciphertext"):
            rewrite.sanitize_json_response(raw)


class ResponseSanitizationContracts:
    def test_sanitize_sse_event_strips_reasoning_and_agent_ciphertext(self):
        raw = b'event: response.completed\ndata: {"type":"response.completed","response":{"output":[{"type":"reasoning","encrypted_content":"replay","id":"r"},{"type":"agent_message","content":[{"type":"encrypted_content","encrypted_content":"required"}]}]}}\n\n'
        out, removed = rewrite.sanitize_sse_event(raw)
        event = json.loads(out.split(b"data: ", 1)[1])
        output = event["response"]["output"]
        assert removed == 2
        assert "encrypted_content" not in output[0]
        assert output[1]["content"] == [
            {"type": "output_text", "text": request_projection.OPAQUE_CONTENT_MARKER}
        ]

    def test_sse_sanitizer_passes_non_json_and_non_target_events_unchanged(self, subtests):
        events = (
            b"data: [DONE]\n\n",
            b'data: {"encrypted_content":\n\n',
            b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n',
        )
        for raw in events:
            with subtests.test(raw=raw):
                assert rewrite.sanitize_sse_event(raw) == (raw, 0)

    def test_sse_sanitizer_fails_open_when_mutation_cannot_be_serialized(self, *, mocker):
        raw = b'data: {"type":"response.completed","response":{"output":[{"type":"reasoning","encrypted_content":"opaque"}]}}\n\n'
        mocker.patch.object(request_projection.json, "dumps", side_effect=TypeError("unsupported"))
        assert rewrite.sanitize_sse_event(raw) == (raw, 0)

    def test_deep_sse_projection_remains_atomic(self) -> None:
        event = (
            "data: "
            + '{"x":' * 997
            + '{"type":"reasoning","encrypted_content":"opaque"}'
            + "}" * 997
            + "\n\n"
        ).encode()
        assert rewrite.sanitize_sse_event(event) == (event, 0)
