#!/usr/bin/env python3
"""Provider-portable request projection contracts."""

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


class ProviderPortableRequestTests(unittest.TestCase):
    """The normal outbound path, not an error fallback, owns portability."""

    def test_projects_provider_bound_history_to_closed_portable_grammar(self) -> None:
        raw = _body(
            {
                "model": "gpt-5.6-terra",
                "stream": True,
                "store": True,
                "previous_response_id": "resp_from_other_provider",
                "conversation": {"id": "conv_from_other_provider"},
                "prompt_cache_key": "provider-cache-key",
                "include": ["reasoning.encrypted_content", "other"],
                "input": [
                    {
                        "type": "reasoning",
                        "id": "rs_provider_bound",
                        "encrypted_content": "opaque-reasoning",
                        "summary": [],
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "web_search_call",
                        "id": "ws_provider_bound",
                        "status": "completed",
                        "action": {"type": "search", "query": "old"},
                    },
                    {"type": "item_reference", "id": "rs_stored_reference"},
                    {
                        "type": "message",
                        "id": "msg_provider_bound",
                        "status": "completed",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "visible answer",
                                "annotations": [],
                                "logprobs": [],
                            }
                        ],
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "agent_message",
                        "id": "amsg_provider_bound",
                        "author": "planner",
                        "recipient": "user",
                        "phase": "commentary",
                        "content": [
                            {"type": "encrypted_content", "encrypted_content": "agent-secret"},
                            {"type": "input_text", "text": "visible agent text"},
                        ],
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "function_call",
                        "id": "fc_provider_bound",
                        "call_id": "call_function",
                        "name": "lookup",
                        "arguments": "{}",
                        "namespace": "tools",
                        "status": "completed",
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "function_call_output",
                        "id": "fco_provider_bound",
                        "call_id": "call_function",
                        "output": [
                            {"type": "input_text", "text": "visible function output"},
                            {"type": "encrypted_content", "encrypted_content": "tool-secret"},
                        ],
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "custom_tool_call",
                        "id": "ctc_provider_bound",
                        "call_id": "call_custom",
                        "name": "exec",
                        "input": "{}",
                        "status": "completed",
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {
                        "type": "custom_tool_call_output",
                        "id": "ctco_provider_bound",
                        "call_id": "call_custom",
                        "output": [
                            {"type": "encrypted_content", "encrypted_content": "only-secret"}
                        ],
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    },
                    {"type": "message", "role": "user", "content": "continue here"},
                ],
            }
        )

        _projection = rewrite.sanitize_responses_body(raw)
        projected_raw = _projection.body
        note = _projection.diagnostic()

        self.assertIsNotNone(projected_raw, note)
        projected = json.loads(cast("bytes", projected_raw))
        for field in ("previous_response_id", "conversation", "prompt_cache_key"):
            self.assertNotIn(field, projected)
        self.assertEqual(projected["include"], ["other"])
        self.assertIs(projected["store"], False)
        self.assertEqual(
            [item["type"] for item in projected["input"]],
            [
                "message",
                "message",
                "function_call",
                "function_call_output",
                "custom_tool_call",
                "custom_tool_call_output",
                "message",
            ],
        )
        assistant = projected["input"][0]
        self.assertEqual(assistant["phase"], "final_answer")
        self.assertEqual(assistant["content"], "visible answer")
        agent = projected["input"][1]
        self.assertEqual((agent["role"], agent["phase"]), ("assistant", "commentary"))
        header, visible = agent["content"].split("\n", 1)
        self.assertEqual(
            json.loads(header),
            {"type": "agent_message", "author": "planner", "recipient": "user"},
        )
        self.assertEqual(visible, "visible agent text")
        function_call, function_output = projected["input"][2:4]
        self.assertEqual(function_call["call_id"], function_output["call_id"])
        self.assertEqual(
            function_output["output"],
            [{"type": "input_text", "text": "visible function output"}],
        )
        custom_call, custom_output = projected["input"][4:6]
        self.assertEqual(custom_call["call_id"], custom_output["call_id"])
        self.assertEqual(
            custom_output["output"],
            [{"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}],
        )
        serialized = cast("bytes", projected_raw).decode()
        for forbidden in (
            "rs_provider_bound",
            "rs_stored_reference",
            "opaque-reasoning",
            "agent-secret",
            "tool-secret",
            "only-secret",
            "internal_chat_message_metadata_passthrough",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("provider_bindings=3", note)
        self.assertIn("reasoning_items=1", note)

    def test_preserves_remote_compaction_trigger_as_a_request_control(self) -> None:
        raw = _body(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "compact this"},
                    {"type": "compaction_trigger"},
                ]
            }
        )

        projection = rewrite.sanitize_responses_body(raw)

        self.assertEqual(
            json.loads(cast("bytes", projection.body))["input"],
            [
                {"type": "message", "role": "user", "content": "compact this"},
                {"type": "compaction_trigger"},
            ],
        )
        self.assertEqual(projection.status, "projected")

    def test_rejects_compaction_trigger_with_unknown_fields(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body({"input": [{"type": "compaction_trigger", "unexpected": True}]})
        )

        self.assertIsNone(projection.body)
        self.assertEqual(projection.diagnostic(), "rejected unknown_compaction_trigger_field")

    def test_preserves_clean_string_input_while_removing_top_level_bindings(self) -> None:
        raw = _body(
            {
                "input": "hello",
                "previous_response_id": "provider-response",
                "conversation": "provider-conversation",
            }
        )

        _projection = rewrite.sanitize_responses_body(raw)
        projected_raw = _projection.body
        _note = _projection.diagnostic()

        self.assertEqual(
            json.loads(cast("bytes", projected_raw)),
            {"input": "hello", "store": False},
        )

    def test_forces_stateless_responses_even_when_store_is_absent_or_true(self) -> None:
        for supplied in (False, True, None):
            with self.subTest(store=supplied):
                payload = {"input": "continue"}
                if supplied is not None:
                    payload["store"] = supplied

                _projection = rewrite.sanitize_responses_body(_body(payload))
                projected_raw = _projection.body
                note = _projection.diagnostic()

                self.assertEqual(
                    json.loads(cast("bytes", projected_raw)),
                    {"input": "continue", "store": False},
                )
                if supplied is True:
                    self.assertIn("store_normalized=True", note)

    def test_marks_paired_empty_tool_outputs_without_admitting_empty_dialogue(self) -> None:
        cases = (
            ("function_call", "arguments", "function_call_output"),
            ("custom_tool_call", "input", "custom_tool_call_output"),
        )
        for call_type, argument_field, output_type in cases:
            with self.subTest(call_type=call_type):
                _projection = rewrite.sanitize_responses_body(
                    _body(
                        {
                            "input": [
                                {
                                    "type": call_type,
                                    "call_id": "empty-result",
                                    "name": "bounded-test-tool",
                                    argument_field: "{}",
                                },
                                {
                                    "type": output_type,
                                    "call_id": "empty-result",
                                    "output": "",
                                },
                            ]
                        }
                    )
                )
                projected_raw = _projection.body
                note = _projection.diagnostic()

                self.assertIsNotNone(projected_raw, note)
                projected = json.loads(cast("bytes", projected_raw))["input"]
                self.assertEqual(projected[0]["call_id"], projected[1]["call_id"])
                self.assertEqual(projected[1]["output"], rewrite.EMPTY_TOOL_OUTPUT_MARKER)
                self.assertIn("empty_tool_outputs=1", note)

        _projection = rewrite.sanitize_responses_body(
            _body({"input": [{"type": "message", "role": "assistant", "content": ""}]})
        )
        projected = _projection.body
        note = _projection.diagnostic()
        self.assertIsNone(projected)
        self.assertEqual(note, "rejected empty_text_content")

        for label, output in (("missing", None), ("null", None)):
            item = {"type": "function_call_output", "call_id": "empty-result"}
            if label == "null":
                item["output"] = output
            _projection = rewrite.sanitize_responses_body(
                _body(
                    {
                        "input": [
                            {
                                "type": "function_call",
                                "call_id": "empty-result",
                                "name": "bounded-test-tool",
                                "arguments": "{}",
                            },
                            item,
                        ]
                    }
                )
            )
            projected = _projection.body
            note = _projection.diagnostic()
            with self.subTest(output=label):
                self.assertIsNone(projected)
                self.assertEqual(note, "rejected invalid_content")

    def test_normalizes_typed_dialogue_content_by_projected_role(self) -> None:
        raw = _body(
            {
                "input": [
                    {
                        "type": "message",
                        "role": "system",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "system",
                                "annotations": [],
                            }
                        ],
                    },
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "output_text", "text": "developer", "logprobs": []}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "user",
                                "prompt_cache_breakpoint": {"mode": "explicit"},
                            }
                        ],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "answer",
                                "prompt_cache_breakpoint": {"mode": "explicit"},
                            },
                            {"type": "refusal", "refusal": "declined"},
                        ],
                    },
                ]
            }
        )

        _projection = rewrite.sanitize_responses_body(raw)
        projected_raw = _projection.body
        note = _projection.diagnostic()

        self.assertIsNotNone(projected_raw, note)
        content = [item["content"] for item in json.loads(cast("bytes", projected_raw))["input"]]
        self.assertEqual(
            content,
            [
                [{"type": "input_text", "text": "system"}],
                [{"type": "input_text", "text": "developer"}],
                [{"type": "input_text", "text": "user"}],
                "answerdeclined",
            ],
        )

    def test_fails_closed_for_unknown_or_malformed_replay_shapes(self) -> None:
        cases = {
            "invalid json": b"{",
            "non object": b"[]",
            "invalid input": _body({"input": {"type": "message"}}),
            "unknown item": _body({"input": [{"type": "future_item", "opaque": True}]}),
            "unknown block": _body(
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "future_content", "value": "opaque"}],
                        }
                    ]
                }
            ),
            "orphan output": _body(
                {"input": [{"type": "function_call_output", "call_id": "missing", "output": "x"}]}
            ),
            "mismatched output": _body(
                {
                    "input": [
                        {
                            "type": "function_call",
                            "call_id": "c",
                            "name": "f",
                            "arguments": "{}",
                        },
                        {"type": "custom_tool_call_output", "call_id": "c", "output": "x"},
                    ]
                }
            ),
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                _projection = rewrite.sanitize_responses_body(raw)
                projected = _projection.body
                note = _projection.diagnostic()
                self.assertIsNone(projected)
                self.assertTrue(note.startswith("rejected "), note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
