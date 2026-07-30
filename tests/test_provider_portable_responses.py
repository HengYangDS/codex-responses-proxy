#!/usr/bin/env python3
"""Provider-portable request, stream, and route contracts."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_dmx_proxy.listener import responses  # noqa: E402
from codex_dmx_proxy.listener import rewrite  # noqa: E402
from codex_dmx_proxy.listener import state  # noqa: E402
from tests.support.proxy_http import request  # noqa: E402
from tests.support.proxy_http import running_proxy  # noqa: E402


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

        projected_raw, note = rewrite.sanitize_responses_body(raw)

        self.assertIsNotNone(projected_raw, note)
        projected = json.loads(cast("bytes", projected_raw))
        for field in ("previous_response_id", "conversation", "prompt_cache_key"):
            self.assertNotIn(field, projected)
        self.assertEqual(projected["include"], ["other"])
        self.assertTrue(projected["store"])
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

    def test_preserves_clean_string_input_while_removing_top_level_bindings(self) -> None:
        raw = _body(
            {
                "input": "hello",
                "previous_response_id": "provider-response",
                "conversation": "provider-conversation",
            }
        )

        projected_raw, _note = rewrite.sanitize_responses_body(raw)

        self.assertEqual(json.loads(cast("bytes", projected_raw)), {"input": "hello"})

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

        projected_raw, note = rewrite.sanitize_responses_body(raw)

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
                projected, note = rewrite.sanitize_responses_body(raw)
                self.assertIsNone(projected)
                self.assertTrue(note.startswith("rejected "), note)

    def test_fails_closed_at_each_portable_grammar_boundary(self) -> None:
        cases = {
            "empty input": ({"input": ""}, "rejected empty_input"),
            "invalid include": ({"input": "hello", "include": [1]}, "rejected invalid_include"),
            "invalid item": ({"input": ["not-an-item"]}, "rejected invalid_item"),
            "only provider-bound items": (
                {"input": [{"type": "reasoning"}]},
                "rejected empty_portable_input",
            ),
            "empty message text": (
                {"input": [{"type": "message", "role": "user", "content": ""}]},
                "rejected empty_text_content",
            ),
            "invalid content block": (
                {"input": [{"type": "message", "role": "user", "content": [1]}]},
                "rejected invalid_content_block",
            ),
            "invalid text block": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": 1}],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "input text has unknown metadata": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "x", "unknown": True}],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "input text has invalid cache breakpoint": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "x",
                                    "prompt_cache_breakpoint": {"mode": "future"},
                                }
                            ],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "output text has unknown metadata": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "x", "unknown": True}],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "output text annotations are not a list": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "x", "annotations": {}}],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "output text logprobs are not a list": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "x", "logprobs": {}}],
                        }
                    ]
                },
                "rejected invalid_text_block",
            ),
            "invalid refusal block": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "refusal", "refusal": 1}],
                        }
                    ]
                },
                "rejected invalid_refusal_block",
            ),
            "refusal on input role": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "refusal", "refusal": "no"}],
                        }
                    ]
                },
                "rejected invalid_refusal_role",
            ),
            "malformed refusal on input role": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "refusal", "refusal": 1}],
                        }
                    ]
                },
                "rejected invalid_refusal_block",
            ),
            "image on assistant role": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": "https://example.test/image.png",
                                }
                            ],
                        }
                    ]
                },
                "rejected unsupported_assistant_image",
            ),
            "non-string agent root ciphertext": (
                {
                    "input": [
                        {
                            "type": "agent_message",
                            "author": "planner",
                            "recipient": "user",
                            "content": [],
                            "encrypted_content": 1,
                        }
                    ]
                },
                "rejected invalid_encrypted_content",
            ),
            "assistant scalar content": (
                {"input": [{"type": "message", "role": "assistant", "content": 1}]},
                "rejected invalid_content",
            ),
            "assistant non-object block": (
                {"input": [{"type": "message", "role": "assistant", "content": [1]}]},
                "rejected invalid_content_block",
            ),
            "assistant unknown block": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "future_content"}],
                        }
                    ]
                },
                "rejected unknown_content_type",
            ),
            "assistant empty typed text": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": ""}],
                        }
                    ]
                },
                "rejected empty_portable_content",
            ),
            "non-string tool root ciphertext": (
                {
                    "input": [
                        {
                            "type": "function_call",
                            "call_id": "c",
                            "name": "f",
                            "arguments": "{}",
                        },
                        {
                            "type": "function_call_output",
                            "call_id": "c",
                            "output": [],
                            "encrypted_content": 1,
                        },
                    ]
                },
                "rejected invalid_encrypted_content",
            ),
            "invalid image field": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": "https://example.test/image.png",
                                    "unexpected": True,
                                }
                            ],
                        }
                    ]
                },
                "rejected invalid_image_block",
            ),
            "invalid image detail": (
                {
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": "https://example.test/image.png",
                                    "detail": "future",
                                }
                            ],
                        }
                    ]
                },
                "rejected invalid_image_detail",
            ),
            "invalid message role": (
                {"input": [{"type": "message", "role": "tool", "content": "x"}]},
                "rejected invalid_message_role",
            ),
            "invalid message phase": (
                {
                    "input": [
                        {"type": "message", "role": "user", "phase": "commentary", "content": "x"}
                    ]
                },
                "rejected invalid_message_phase",
            ),
            "invalid agent identity": (
                {"input": [{"type": "agent_message", "author": "planner", "content": "x"}]},
                "rejected invalid_agent_message",
            ),
            "invalid agent phase": (
                {
                    "input": [
                        {
                            "type": "agent_message",
                            "author": "planner",
                            "recipient": "user",
                            "phase": "future",
                            "content": "x",
                        }
                    ]
                },
                "rejected invalid_agent_phase",
            ),
            "invalid call id": (
                {
                    "input": [
                        {"type": "function_call", "call_id": "", "name": "f", "arguments": "{}"}
                    ]
                },
                "rejected invalid_call_id",
            ),
            "invalid call": (
                {
                    "input": [
                        {"type": "function_call", "call_id": "c", "name": "", "arguments": "{}"}
                    ]
                },
                "rejected invalid_call",
            ),
            "invalid namespace": (
                {
                    "input": [
                        {
                            "type": "function_call",
                            "call_id": "c",
                            "name": "f",
                            "arguments": "{}",
                            "namespace": "",
                        }
                    ]
                },
                "rejected invalid_namespace",
            ),
            "invalid call caller": (
                {
                    "input": [
                        {
                            "type": "function_call",
                            "call_id": "c",
                            "name": "f",
                            "arguments": "{}",
                            "caller": "not-an-object",
                        }
                    ]
                },
                "rejected invalid_caller",
            ),
            "duplicate output": (
                {
                    "input": [
                        {"type": "function_call", "call_id": "c", "name": "f", "arguments": "{}"},
                        {"type": "function_call_output", "call_id": "c", "output": "first"},
                        {"type": "function_call_output", "call_id": "c", "output": "second"},
                    ]
                },
                "rejected duplicate_output",
            ),
            "invalid output caller": (
                {
                    "input": [
                        {"type": "function_call", "call_id": "c", "name": "f", "arguments": "{}"},
                        {
                            "type": "function_call_output",
                            "call_id": "c",
                            "output": "x",
                            "caller": "not-an-object",
                        },
                    ]
                },
                "rejected invalid_caller",
            ),
        }
        for name, (payload, expected_note) in cases.items():
            with self.subTest(name=name):
                projected, note = rewrite.sanitize_responses_body(_body(payload))
                self.assertIsNone(projected)
                self.assertEqual(note, expected_note)

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

        projected_raw, note = rewrite.sanitize_responses_body(raw)

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

        projected_raw, note = rewrite.sanitize_responses_body(raw)

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
                projected_raw, note = rewrite.sanitize_responses_body(
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
                self.assertIsNotNone(projected_raw, note)
                projected = json.loads(cast("bytes", projected_raw))["input"][0]
                self.assertTrue(projected["content"].endswith(rewrite.OPAQUE_CONTENT_MARKER))


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


class ProviderRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        state.reset_for_test()

    def test_accepts_only_absolute_https_upstream_origins(self) -> None:
        self.assertEqual(
            responses.validate_upstream_origin("TEST_UPSTREAM", "https://example.test/"),
            "https://example.test",
        )
        self.assertEqual(
            responses.validate_upstream_origin("TEST_UPSTREAM", "https://example.test:8443"),
            "https://example.test:8443",
        )

        invalid = (
            "http://example.test",
            "https://user:secret@example.test",
            "https://example.test/v1",
            "https://example.test?route=other",
            "https://example.test#fragment",
            "https://example.test:bad",
            "not-a-url",
        )
        for value in invalid:
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(
                    ValueError, "^TEST_UPSTREAM must be an absolute HTTPS origin$"
                ),
            ):
                responses.validate_upstream_origin("TEST_UPSTREAM", value)

    def test_resolves_only_canonical_provider_routes_and_bounded_dmx_migration(self) -> None:
        expected = {
            "/dmxapi/v1/responses": ("dmxapi", f"{responses.DMXAPI_UPSTREAM}/v1/responses"),
            "/ucloud/v1/responses?stream=true": (
                "ucloud",
                f"{responses.UCLOUD_UPSTREAM}/v1/responses?stream=true",
            ),
            "/aihubmix/v1/models": ("aihubmix", f"{responses.AIHUBMIX_UPSTREAM}/v1/models"),
            "/v1/responses": ("dmxapi", f"{responses.DMXAPI_UPSTREAM}/v1/responses"),
        }
        for path, route in expected.items():
            with self.subTest(path=path):
                self.assertEqual(responses.resolve_upstream(path), route)

        for path in (
            "/unknown/v1/responses",
            "/dmxapi/other",
            "/ucloud/v2/responses",
            "https://attacker.invalid/v1/responses",
        ):
            with self.subTest(path=path):
                self.assertIsNone(responses.resolve_upstream(path))

    def test_all_three_routes_forward_the_same_portable_body(self) -> None:
        raw = _body(
            {
                "previous_response_id": "provider-response",
                "include": ["reasoning.encrypted_content"],
                "input": [
                    {"type": "reasoning", "id": "rs_old", "encrypted_content": "opaque"},
                    {
                        "type": "message",
                        "id": "msg_old",
                        "status": "completed",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "prior answer",
                                "annotations": [],
                            },
                            {"type": "refusal", "refusal": "prior refusal"},
                        ],
                    },
                    {"type": "message", "role": "user", "content": "continue"},
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "lookup",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": [{"type": "output_text", "text": "tool result"}],
                    },
                ],
            }
        )
        success = b'{"id":"resp_ok","status":"completed"}'

        with running_proxy([(200, success), (200, success), (200, success)]) as (port, received):
            for route in ("dmxapi", "ucloud", "aihubmix"):
                with (
                    self.subTest(route=route),
                    request(port, raw, path=f"/{route}/v1/responses") as response,
                ):
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 3)
        for forwarded in received:
            payload = json.loads(forwarded)
            self.assertNotIn("previous_response_id", payload)
            self.assertEqual(payload["include"], [])
            assistant, user, call, output = payload["input"]
            self.assertEqual(
                assistant,
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": "prior answerprior refusal",
                },
            )
            self.assertEqual(user, {"type": "message", "role": "user", "content": "continue"})
            self.assertEqual(call["call_id"], output["call_id"])
            self.assertEqual(output["output"], [{"type": "input_text", "text": "tool result"}])

    def test_unknown_route_and_unknown_replay_shape_never_reach_upstream(self) -> None:
        with running_proxy([]) as (port, received):
            for path, body, expected_code in (
                ("/unknown/v1/responses", _body({"input": "hello"}), 404),
                (
                    "/ucloud/v1/responses",
                    _body({"input": [{"type": "future_item", "opaque": True}]}),
                    400,
                ),
            ):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as raised:
                    request(port, body, path=path)
                with raised.exception as error:
                    self.assertEqual(error.code, expected_code)
            self.assertEqual(received, [])

    def test_dmx_empty_response_cooldown_does_not_block_ucloud(self) -> None:
        empty = _body(
            {
                "error": {
                    "message": "official provider returned an empty response",
                    "type": "dmx_api_error",
                    "code": "empty_response",
                }
            }
        )
        success = b'{"id":"resp_ucloud","status":"completed"}'
        body = _body({"input": [{"type": "message", "role": "user", "content": "same"}]})

        with running_proxy([(477, empty), (477, empty), (200, success)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body, path="/dmxapi/v1/responses")
            with raised.exception as error:
                self.assertEqual(error.code, 503)
            with request(port, body, path="/ucloud/v1/responses") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 3)

    def test_non_dmx_http_477_is_not_given_dmx_recovery(self) -> None:
        empty = _body(
            {
                "error": {
                    "message": "official provider returned an empty response",
                    "type": "dmx_api_error",
                    "code": "empty_response",
                }
            }
        )
        body = _body({"input": [{"type": "message", "role": "user", "content": "same"}]})

        with running_proxy([(477, empty)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body, path="/aihubmix/v1/responses")
            with raised.exception as error:
                self.assertEqual(error.code, 477)
                self.assertEqual(error.read(), empty)

        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
