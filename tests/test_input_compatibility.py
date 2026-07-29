#!/usr/bin/env python3
"""Focused contracts for the pure Responses input-compatibility policy."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proxy"))

import input_compatibility


def _exact_error() -> bytes:
    return json.dumps(
        {
            "error": {
                "message": (
                    "invalid request body: Invalid 'input': "
                    "value did not match any expected variant"
                ),
                "type": "invalid_request_error",
                "param": "",
                "code": "validation_error",
            }
        },
        separators=(",", ":"),
    ).encode()


class TestExactErrorContract(unittest.TestCase):
    """Verify that only the complete observed error contract is admitted."""

    def test_matches_complete_contract(self) -> None:
        self.assertTrue(input_compatibility.is_exact_validation_error(400, _exact_error()))

    def test_allows_only_envelope_metadata_outside_the_exact_error_object(self) -> None:
        payload = json.loads(_exact_error())
        payload["request_id"] = "opaque-envelope-metadata"
        self.assertTrue(
            input_compatibility.is_exact_validation_error(400, json.dumps(payload).encode())
        )

    def test_rejects_extra_or_changed_fields(self) -> None:
        payload = json.loads(_exact_error())
        payload["error"]["request_id"] = "unstable"
        self.assertFalse(
            input_compatibility.is_exact_validation_error(400, json.dumps(payload).encode())
        )
        self.assertFalse(input_compatibility.is_exact_validation_error(422, _exact_error()))

    def test_rejects_malformed_or_non_object_error_bodies(self) -> None:
        for body in (b"not-json", b"[]", b'{"error":null}'):
            with self.subTest(body=body):
                self.assertFalse(input_compatibility.is_exact_validation_error(400, body))


class TestInputDiagnostic(unittest.TestCase):
    """Verify bounded diagnostics without content or exact-cardinality fingerprints."""

    def test_non_string_unhashable_types_are_classified_without_raising(self) -> None:
        for value, expected in (({"private": "value"}, "dict"), (["private"], "list")):
            with self.subTest(expected=expected):
                diagnostic = input_compatibility.diagnose(
                    json.dumps({"input": [{"type": value}]}).encode()
                )
                self.assertEqual(diagnostic.item_types, {expected: "1"})
                self.assertEqual(diagnostic.first_incompatible_reason, "missing_item_type")

    def test_unknown_names_and_values_do_not_enter_diagnostic(self) -> None:
        secret = "private-value-never-log"
        diagnostic = input_compatibility.diagnose(
            json.dumps(
                {
                    "input": [
                        {
                            "type": "private-extension-name",
                            "role": "private-role",
                            "private-field": secret,
                        }
                    ]
                }
            ).encode()
        )
        rendered = input_compatibility.format_diagnostic(diagnostic)
        projected = json.dumps(input_compatibility.diagnostic_dict(diagnostic), sort_keys=True)
        self.assertNotIn(secret, rendered + projected)
        self.assertNotIn("private-extension-name", rendered + projected)
        self.assertNotIn("private-field", rendered + projected)

    def test_cardinality_is_bucketed_before_shape_hashing(self) -> None:
        first = cast("dict[str, object]", input_compatibility.structure_shape([1, 2]))
        second = cast("dict[str, object]", input_compatibility.structure_shape([1, 2, 3, 4]))
        self.assertEqual(first["size"], "2-4")
        self.assertEqual(second["size"], "2-4")
        self.assertNotIn("length", first)
        self.assertNotIn("length", second)

    def test_diagnostic_exposes_buckets_and_presence_not_exact_cardinalities(self) -> None:
        def diagnostic_for(repetitions: int) -> input_compatibility.InputDiagnostic:
            items: list[dict[str, object]] = [
                {"type": "message", "role": "user", "content": "current"},
                {"type": "function_call", "call_id": "paired", "name": "f", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "paired", "output": "ok"},
            ]
            for index in range(repetitions):
                call_id = f"unmatched-{index}"
                items.extend(
                    [
                        {
                            "type": "custom_tool_call",
                            "call_id": call_id,
                            "name": "f",
                            "input": "{}",
                        },
                        {"type": "custom_tool_call", "name": "f", "input": "{}"},
                    ]
                )
            return input_compatibility.diagnose(json.dumps({"input": items}).encode())

        expected = (
            (diagnostic_for(2), "2-4"),
            (diagnostic_for(4), "5-16"),
        )
        for diagnostic, item_type_bucket in expected:
            projected = input_compatibility.diagnostic_dict(diagnostic)
            rendered = input_compatibility.format_diagnostic(diagnostic)
            self.assertEqual(projected["input_items_bucket"], "5-16")
            item_types = cast("dict[str, str]", projected["item_types"])
            self.assertEqual(item_types["custom_tool_call"], item_type_bucket)
            self.assertTrue(projected["matched_pairs"])
            self.assertTrue(projected["unmatched_calls"])
            self.assertTrue(projected["missing_call_ids"])
            self.assertNotIn("first_incompatible_index", projected)
            self.assertNotIn("input_items=", rendered)
            self.assertNotRegex(rendered, r"(?:matched_pairs|unmatched_calls|missing_call_ids)=\d")

    def test_shape_hash_ignores_order_and_repetition_within_one_bucket(self) -> None:
        def shape_hash(items: list[dict[str, object]]) -> str:
            return input_compatibility.diagnose(json.dumps({"input": items}).encode()).shape_sha256

        user: dict[str, object] = {
            "type": "message",
            "role": "user",
            "content": "current",
        }
        reasoning: dict[str, object] = {"type": "reasoning", "summary": []}
        first = shape_hash([user, reasoning])
        second = shape_hash([reasoning, user, user, reasoning])
        self.assertEqual(first, second)

    def test_shape_hash_does_not_reveal_exact_top_level_field_count(self) -> None:
        def shape_hash(extra_fields: int) -> str:
            payload: dict[str, object] = {"input": []}
            payload.update({f"private-{index}": "value" for index in range(extra_fields)})
            return input_compatibility.diagnose(json.dumps(payload).encode()).shape_sha256

        self.assertEqual(shape_hash(1), shape_hash(3))

    def test_shape_hash_does_not_reveal_large_exact_collection_size(self) -> None:
        def shape_hash(size: int) -> str:
            payload = {"input": [], "private": ["value"] * size}
            return input_compatibility.diagnose(json.dumps(payload).encode()).shape_sha256

        self.assertEqual(shape_hash(17), shape_hash(33))

    def test_shape_hash_does_not_reveal_exact_unique_shape_count_above_cap(self) -> None:
        def shape_hash(size: int) -> str:
            values = [
                {"type": f"private-{index}", "field": [None] * index} for index in range(size)
            ]
            payload = {"input": [], "private": values}
            return input_compatibility.diagnose(json.dumps(payload).encode()).shape_sha256

        self.assertEqual(shape_hash(33), shape_hash(34))

    def test_tool_search_output_is_validated_by_tools_not_generic_output(self) -> None:
        valid = input_compatibility.diagnose(
            json.dumps(
                {
                    "input": [
                        {
                            "type": "tool_search_call",
                            "call_id": "search",
                            "arguments": {},
                        },
                        {
                            "type": "tool_search_output",
                            "call_id": "search",
                            "tools": [],
                        },
                    ]
                }
            ).encode()
        )
        self.assertEqual(valid.first_incompatible_reason, "")

        invalid = input_compatibility.diagnose(
            json.dumps(
                {
                    "input": [
                        {
                            "type": "tool_search_call",
                            "call_id": "search",
                            "arguments": {},
                        },
                        {
                            "type": "tool_search_output",
                            "call_id": "search",
                            "output": [],
                        },
                    ]
                }
            ).encode()
        )
        self.assertEqual(invalid.first_incompatible_reason, "invalid_tool_search_output")

    def test_reports_invalid_envelopes_and_pair_failures(self) -> None:
        fixtures = (
            (b"not-json", "invalid_json"),
            (b"[]", "request_not_object"),
            (b'{"input":null}', "input_not_list"),
            (json.dumps({"input": [1]}).encode(), "item_not_object"),
            (
                json.dumps(
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
                ).encode(),
                "mismatched_output_type",
            ),
        )
        for body, reason in fixtures:
            with self.subTest(reason=reason):
                diagnostic = input_compatibility.diagnose(body)
                self.assertEqual(diagnostic.first_incompatible_reason, reason)

    def test_reports_duplicate_missing_and_unmatched_pairs(self) -> None:
        diagnostic = input_compatibility.diagnose(
            json.dumps(
                {
                    "input": [
                        {"type": "custom_tool_call_output", "call_id": "early", "output": "x"},
                        {"type": "custom_tool_call", "call_id": "dup", "name": "f", "input": "{}"},
                        {"type": "custom_tool_call", "call_id": "dup", "name": "f", "input": "{}"},
                        {"type": "custom_tool_call_output", "call_id": "dup", "output": "x"},
                        {"type": "custom_tool_call_output", "call_id": "dup", "output": "x"},
                        {"type": "custom_tool_call", "name": "f", "input": "{}"},
                    ]
                }
            ).encode()
        )
        self.assertTrue(diagnostic.outputs_before_calls)
        self.assertTrue(diagnostic.duplicate_calls)
        self.assertTrue(diagnostic.duplicate_outputs)
        self.assertTrue(diagnostic.missing_call_ids)
        self.assertTrue(diagnostic.unmatched_outputs)

    def test_validates_known_message_and_content_shapes(self) -> None:
        fixtures = (
            ({"type": "message", "role": "bogus", "content": "x"}, "invalid_message_role"),
            ({"type": "message", "role": "user", "content": None}, "invalid_message_content"),
            ({"type": "message", "role": "user", "content": []}, "empty_message_content"),
            (
                {"type": "message", "role": "user", "content": [{"type": "input_text"}]},
                "invalid_input_text_block",
            ),
            (
                {"type": "agent_message", "content": [{"type": "encrypted_content"}]},
                "malformed_encrypted_content_block",
            ),
            (
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_image", "detail": "auto"}],
                },
                "invalid_input_image_block",
            ),
        )
        for item, reason in fixtures:
            with self.subTest(reason=reason):
                diagnostic = input_compatibility.diagnose(json.dumps({"input": [item]}).encode())
                self.assertEqual(diagnostic.first_incompatible_reason, reason)


class TestDialogueRecovery(unittest.TestCase):
    """Verify the single strictly smaller current-dialogue recovery projection."""

    def test_preserves_instructions_and_latest_roles_in_original_order(self) -> None:
        payload = {
            "instructions": "top-level policy",
            "previous_response_id": "stale",
            "conversation": {"id": "stale"},
            "prompt_cache_key": "stale",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {"type": "message", "role": "user", "content": "current"},
                {"type": "message", "role": "developer", "content": "late policy"},
                {"type": "custom_tool_call", "call_id": "call", "name": "exec", "input": "{}"},
            ],
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        recovery, metrics = input_compatibility.build_recovery(raw, 512 * 1024)
        self.assertIsNotNone(recovery)
        self.assertIsNotNone(metrics)
        assert recovery is not None
        recovered = json.loads(recovery)
        self.assertEqual(recovered["instructions"], "top-level policy")
        self.assertEqual(
            recovered["input"],
            [payload["input"][0], payload["input"][1]],
        )
        self.assertEqual(recovered["include"], ["other"])
        self.assertNotIn("previous_response_id", recovered)
        self.assertNotIn("conversation", recovered)
        self.assertNotIn("prompt_cache_key", recovered)
        self.assertLess(len(recovery), len(raw))

    def test_latest_role_messages_keep_their_original_relative_order(self) -> None:
        payload = {
            "input": [
                {"type": "message", "role": "user", "content": "old user"},
                {"type": "message", "role": "system", "content": "current system"},
                {"type": "message", "role": "developer", "content": "old developer"},
                {"type": "message", "role": "user", "content": "current user"},
                {"type": "message", "role": "developer", "content": "current developer"},
                {"type": "reasoning", "summary": []},
            ]
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        recovery, _metrics = input_compatibility.build_recovery(raw, len(raw))
        self.assertIsNotNone(recovery)
        assert recovery is not None
        self.assertEqual(
            json.loads(recovery)["input"],
            [payload["input"][1], payload["input"][3], payload["input"][4]],
        )

    def test_duplicate_roles_keep_only_each_latest_message_in_original_order(self) -> None:
        payload = {
            "input": [
                {"type": "message", "role": "system", "content": "old system"},
                {"type": "message", "role": "developer", "content": "old developer"},
                {"type": "message", "role": "user", "content": "old user"},
                {"type": "message", "role": "user", "content": "current user"},
                {"type": "message", "role": "system", "content": "current system"},
                {"type": "message", "role": "developer", "content": "current developer"},
                {"type": "reasoning", "summary": []},
            ]
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        recovery, _metrics = input_compatibility.build_recovery(raw, len(raw))
        self.assertIsNotNone(recovery)
        assert recovery is not None
        self.assertEqual(
            json.loads(recovery)["input"],
            [payload["input"][3], payload["input"][4], payload["input"][5]],
        )

    def test_rejects_serialization_only_shrink(self) -> None:
        raw = json.dumps(
            {"input": [{"type": "message", "role": "user", "content": "current"}]}
        ).encode()
        self.assertEqual(input_compatibility.build_recovery(raw, 512 * 1024), (None, None))

    def test_rejects_invalid_budget_envelope_and_missing_user(self) -> None:
        valid = json.dumps(
            {
                "input": [
                    {"type": "message", "role": "user", "content": "current"},
                    {"type": "reasoning", "summary": []},
                ]
            }
        ).encode()
        for raw, budget in (
            (b"not-json", 100),
            (b"[]", 100),
            (b'{"input":[]}', 100),
            (b'{"input":[{"type":"message","role":"developer","content":"x"}]}', 100),
            (valid, 0),
            (valid, True),
            (valid, 10),
        ):
            with self.subTest(raw=raw, budget=budget):
                self.assertEqual(input_compatibility.build_recovery(raw, budget), (None, None))

    def test_projects_only_nonempty_text_content(self) -> None:
        raw = json.dumps(
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_image", "detail": "auto", "image_url": "https://x"},
                            {"type": "output_text", "text": "current"},
                            {"type": "input_text", "text": ""},
                        ],
                    },
                    {"type": "reasoning", "summary": []},
                ]
            },
            separators=(",", ":"),
        ).encode()
        recovery, _metrics = input_compatibility.build_recovery(raw, len(raw))
        self.assertIsNotNone(recovery)
        assert recovery is not None
        self.assertEqual(
            json.loads(recovery)["input"],
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "current"}],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
