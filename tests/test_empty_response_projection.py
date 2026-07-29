#!/usr/bin/env python3
"""Pure projection, validation, and policy contracts for empty-response recovery."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proxy"))
sys.path.insert(0, str(ROOT))

import empty_response as policy
from tests.support.empty_response import body


class EmptyResponseProjectionTests(unittest.TestCase):
    """Exercise deterministic fallback construction without HTTP transport."""

    _body = staticmethod(body)

    def test_no_projection_needed_retries_the_exact_sanitized_bytes_once(self):
        body = self._body(
            {
                "stream": False,
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            }
        )
        fallback, detail = policy.build_fallback(body)

        self.assertEqual(fallback, body)
        self.assertFalse(detail["projected"])

    def test_opaque_reasoning_has_a_fixed_explicit_marker(self):
        body = self._body(
            {
                "input": [
                    {
                        "type": "reasoning",
                        "id": "reasoning-id",
                        "encrypted_content": "must-not-survive",
                        "summary": [],
                    }
                ],
            }
        )

        fallback, _detail = policy.build_fallback(body)

        projected = json.loads(fallback)
        self.assertEqual(projected["input"][0]["role"], "assistant")
        self.assertEqual(projected["input"][0]["phase"], "commentary")
        self.assertEqual(
            projected["input"][0]["content"],
            [{"type": "input_text", "text": policy.OPAQUE_REASONING_MARKER}],
        )
        self.assertNotIn("must-not-survive", fallback.decode())

    def test_output_text_blocks_are_projected_as_input_text_in_each_text_slot(self):
        body = self._body(
            {
                "input": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "visible assistant reply"}],
                    },
                    {
                        "type": "agent_message",
                        "author": "planner",
                        "recipient": "user",
                        "content": [{"type": "output_text", "text": "visible agent reply"}],
                    },
                    {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": "{}"},
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": [{"type": "output_text", "text": "visible tool result"}],
                    },
                ],
            }
        )

        fallback, detail = policy.build_fallback(body)

        self.assertTrue(detail["projected"])
        projected = json.loads(fallback)
        self.assertEqual(
            projected["input"][0]["content"],
            [{"type": "input_text", "text": "visible assistant reply"}],
        )
        self.assertEqual(
            projected["input"][1]["content"][1:],
            [{"type": "input_text", "text": "visible agent reply"}],
        )
        self.assertEqual(
            projected["input"][3]["output"],
            [{"type": "input_text", "text": "visible tool result"}],
        )

    def test_builder_fails_closed_for_unknown_or_unrepresentable_history(self):
        cases = {
            "unknown item": [{"type": "future_item", "value": "opaque"}],
            "orphan output": [
                {"type": "function_call_output", "call_id": "missing", "output": "x"}
            ],
            "non-text agent content": [
                {
                    "type": "agent_message",
                    "author": "agent",
                    "recipient": "user",
                    "content": [{"type": "input_image", "image_url": "https://example.test/a.png"}],
                }
            ],
            "encrypted agent content": [
                {
                    "type": "agent_message",
                    "author": "agent",
                    "recipient": "user",
                    "content": [{"type": "encrypted_content", "encrypted_content": "opaque"}],
                }
            ],
            "duplicate output": [
                {"type": "custom_tool_call", "call_id": "c", "name": "t", "input": "x"},
                {"type": "custom_tool_call_output", "call_id": "c", "output": "one"},
                {"type": "custom_tool_call_output", "call_id": "c", "output": "two"},
            ],
            "invalid message role": [
                {"type": "message", "role": "narrator", "content": "hi"},
            ],
            "phase on a non-assistant message": [
                {"type": "message", "role": "user", "phase": "commentary", "content": "hi"},
            ],
            "unknown phase value": [
                {"type": "message", "role": "assistant", "phase": "final", "content": "hi"},
            ],
            "unknown extra message field": [
                {"type": "message", "role": "user", "content": "hi", "priority": "high"},
            ],
            "unknown extra content-block field": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "hi", "annotations": []},
                    ],
                },
            ],
            "missing call_id": [
                {"type": "function_call", "name": "lookup", "arguments": "{}"},
            ],
            "empty name": [
                {"type": "function_call", "call_id": "c1", "name": "", "arguments": "{}"},
            ],
            "non-string arguments": [
                {"type": "function_call", "call_id": "c1", "name": "lookup", "arguments": {}},
            ],
            "unknown extra call field": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "extra": True,
                },
            ],
            "malformed caller": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "caller": {"type": "direct", "extra": "field"},
                },
            ],
            "malformed namespace": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "namespace": "",
                },
            ],
            "agent_message empty author": [
                {"type": "agent_message", "author": "", "recipient": "user", "content": []},
            ],
            "agent_message unknown field": [
                {
                    "type": "agent_message",
                    "author": "a",
                    "recipient": "user",
                    "content": [],
                    "extra": True,
                },
            ],
            "reasoning with visible summary": [
                {
                    "type": "reasoning",
                    "encrypted_content": "opaque",
                    "summary": [{"type": "summary_text", "text": "visible"}],
                },
            ],
            "reasoning unknown field": [
                {"type": "reasoning", "encrypted_content": "opaque", "unexpected": True},
            ],
        }
        for name, items in cases.items():
            with self.subTest(name=name):
                fallback, detail = policy.build_fallback(self._body({"input": items}))
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

        oversized = self._body(
            {
                "previous_response_id": "remove-me",
                "input": [{"type": "message", "role": "user", "content": "x" * 1000}],
            }
        )
        fallback, detail = policy.build_fallback(oversized, budget=128)
        self.assertIsNone(fallback)
        self.assertEqual(detail["reason"], "budget_exceeded")

        for invalid_budget in (0, -1, 1.5, "128", True):
            # This is an intentional runtime boundary test: preserve values that
            # violate the public type without weakening the production contract.
            fallback, detail = policy.build_fallback(
                self._body({"input": []}), budget=cast("int", cast("object", invalid_budget))
            )
            self.assertIsNone(fallback)
            self.assertEqual(detail["reason"], "invalid_budget")

    def test_agent_message_header_is_deterministically_json_escaped(self):
        body = self._body(
            {
                "input": [
                    {
                        "type": "agent_message",
                        "author": 'planner"; drop table',
                        "recipient": "user\nrecipient",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
            }
        )

        fallback, _detail = policy.build_fallback(body)

        projected = json.loads(fallback)
        header = projected["input"][0]["content"][0]
        self.assertEqual(
            header["text"],
            json.dumps(
                {
                    "type": "agent_message",
                    "author": 'planner"; drop table',
                    "recipient": "user\nrecipient",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        # The header is valid, self-contained JSON: embedded quotes/newlines in
        # author/recipient cannot break out of the fixed envelope.
        json.loads(header["text"])

    def test_string_input_is_preserved_losslessly(self):
        no_op = self._body({"stream": False, "input": "hello there"})
        fallback, detail = policy.build_fallback(no_op)
        self.assertEqual(fallback, no_op)
        self.assertFalse(detail["projected"])

        with_binding = self._body(
            {
                "stream": False,
                "previous_response_id": "remove-me",
                "input": "hello there",
            }
        )
        fallback, detail = policy.build_fallback(with_binding)
        self.assertTrue(detail["projected"])
        projected = json.loads(fallback)
        self.assertEqual(projected["input"], "hello there")
        self.assertNotIn("previous_response_id", projected)

    def test_dialogue_fallback_rejects_non_search_unknown_history(self):
        body = self._body(
            {
                "stream": False,
                "previous_response_id": "provider-history-binding",
                "input": [
                    {"type": "future_item", "opaque": "x" * 256},
                    {"type": "message", "role": "user", "content": "current user request"},
                ],
            }
        )

        fallback, metrics = policy.recover_dialogue(body)

        self.assertIsNone(fallback)
        self.assertIsNone(metrics)

    def test_dialogue_fallback_rejects_unrepresentable_history_with_search_marker(self):
        body = self._body(
            {
                "stream": False,
                "input": [
                    {
                        "type": "web_search_call",
                        "action": {"type": "search", "query": "old query"},
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "input_image", "image_url": "https://example.test/old.png"}
                        ],
                    },
                    {"type": "message", "role": "user", "content": "current user request"},
                ],
            }
        )

        fallback, metrics = policy.recover_dialogue(body)

        self.assertIsNone(fallback)
        self.assertIsNone(metrics)

    def test_dialogue_fallback_rejects_state_after_current_user(self):
        body = self._body(
            {
                "stream": False,
                "input": [
                    {
                        "type": "web_search_call",
                        "action": {"type": "search", "query": "old query"},
                    },
                    {"type": "message", "role": "user", "content": "current user request"},
                    {"type": "message", "role": "assistant", "content": "later assistant state"},
                ],
            }
        )

        fallback, metrics = policy.recover_dialogue(body)

        self.assertIsNone(fallback)
        self.assertIsNone(metrics)

    def test_policy_fingerprint_binds_version_and_sanitized_original_bytes(self):
        self.assertEqual(policy.POLICY_VERSION, "empty-response-fallback-v4")
        first = self._body(
            {
                "previous_response_id": "first",
                "input": [{"type": "message", "role": "user", "content": "same"}],
            }
        )
        second = self._body(
            {
                "previous_response_id": "second",
                "input": [{"type": "message", "role": "user", "content": "same"}],
            }
        )
        first_fallback, _ = policy.build_fallback(first)
        second_fallback, _ = policy.build_fallback(second)
        self.assertEqual(first_fallback, second_fallback)

        first_key = policy.policy_fingerprint(first)
        second_key = policy.policy_fingerprint(second)
        expected = hashlib.sha256(policy.POLICY_VERSION.encode("utf-8") + first).hexdigest()
        self.assertEqual(first_key, expected)
        self.assertNotEqual(first_key, second_key)

    def test_final_answer_phase_is_preserved_and_unknown_values_still_rejected(self):
        body = self._body(
            {
                "input": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": "done",
                    },
                    {
                        "type": "agent_message",
                        "author": "a",
                        "recipient": "b",
                        "phase": "final_answer",
                        "content": [{"type": "input_text", "text": "hi"}],
                    },
                ],
            }
        )
        fallback, detail = policy.build_fallback(body)
        self.assertIsNotNone(fallback)
        projected = json.loads(fallback)
        self.assertEqual(projected["input"][0]["phase"], "final_answer")
        self.assertEqual(projected["input"][1]["phase"], "final_answer")

        # An unknown/unvetted phase remains rejected for both item shapes.
        for items in (
            [{"type": "message", "role": "assistant", "phase": "final", "content": "hi"}],
            [
                {
                    "type": "agent_message",
                    "author": "a",
                    "recipient": "b",
                    "phase": "final",
                    "content": [{"type": "input_text", "text": "hi"}],
                }
            ],
        ):
            with self.subTest(items=items):
                fallback, detail = policy.build_fallback(self._body({"input": items}))
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

    def test_caller_validation_accepts_direct_and_well_formed_program_and_rejects_others(self):
        accepted = self._body(
            {
                "input": [
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "lookup",
                        "arguments": "{}",
                        "caller": {"type": "program", "caller_id": "prog-1"},
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": "ok",
                        "caller": {"type": "program", "caller_id": "prog-1"},
                    },
                ],
            }
        )
        fallback, detail = policy.build_fallback(accepted)
        self.assertIsNotNone(fallback)
        projected = json.loads(fallback)
        self.assertEqual(
            projected["input"][0]["caller"], {"type": "program", "caller_id": "prog-1"}
        )
        self.assertEqual(
            projected["input"][1]["caller"], {"type": "program", "caller_id": "prog-1"}
        )

        rejected_cases = {
            "arbitrary type on call": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "caller": {"type": "indirect"},
                },
            ],
            "program missing caller_id on call": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "caller": {"type": "program"},
                },
            ],
            "program empty caller_id on call": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "caller": {"type": "program", "caller_id": ""},
                },
            ],
            "program extra key on call": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "lookup",
                    "arguments": "{}",
                    "caller": {"type": "program", "caller_id": "p", "extra": "x"},
                },
            ],
            "arbitrary type on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": "ok",
                    "caller": {"type": "indirect"},
                },
            ],
            "program missing caller_id on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": "ok",
                    "caller": {"type": "program"},
                },
            ],
            "program empty caller_id on output": [
                {"type": "custom_tool_call", "call_id": "c1", "name": "t", "input": "x"},
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": "ok",
                    "caller": {"type": "program", "caller_id": ""},
                },
            ],
        }
        for name, items in rejected_cases.items():
            with self.subTest(name=name):
                fallback, detail = policy.build_fallback(self._body({"input": items}))
                self.assertIsNone(fallback)
                self.assertEqual(detail["status"], "rejected")

    def test_non_list_or_non_string_include_entry_is_rejected(self):
        for bad_include in ("reasoning.encrypted_content", ["ok", 5], {"x": 1}):
            with self.subTest(bad_include=bad_include):
                fallback, detail = policy.build_fallback(
                    self._body({"include": bad_include, "input": []})
                )
                self.assertIsNone(fallback)
                self.assertEqual(detail["reason"], "invalid_include")


if __name__ == "__main__":
    unittest.main(verbosity=2)
