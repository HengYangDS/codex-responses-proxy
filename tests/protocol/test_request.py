"""Provider-portable request projection contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from codex_responses_proxy.protocol import request as rewrite

ROOT = Path(__file__).resolve().parents[2]


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _request_body(input_items: object, **extra: object) -> bytes:
    return _body({"input": input_items, **extra})


class ProviderPortableRequestTests:
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

        assert projected_raw is not None, note
        projected = json.loads(projected_raw)
        for field in ("previous_response_id", "conversation", "prompt_cache_key"):
            assert field not in projected
        assert projected["include"] == ["other"]
        assert projected["store"] is False
        assert [item["type"] for item in projected["input"]] == [
            "message",
            "message",
            "function_call",
            "function_call_output",
            "custom_tool_call",
            "custom_tool_call_output",
            "message",
        ]
        assistant = projected["input"][0]
        assert assistant["phase"] == "final_answer"
        assert assistant["content"] == "visible answer"
        agent = projected["input"][1]
        assert (agent["role"], agent["phase"]) == ("assistant", "commentary")
        header, visible = agent["content"].split("\n", 1)
        assert json.loads(header) == {
            "type": "agent_message",
            "author": "planner",
            "recipient": "user",
        }
        assert visible == "visible agent text"
        function_call, function_output = projected["input"][2:4]
        assert function_call["call_id"] == function_output["call_id"]
        assert function_output["output"] == [
            {"type": "input_text", "text": "visible function output"}
        ]
        custom_call, custom_output = projected["input"][4:6]
        assert custom_call["call_id"] == custom_output["call_id"]
        assert custom_output["output"] == [
            {"type": "input_text", "text": rewrite.OPAQUE_CONTENT_MARKER}
        ]
        serialized = projected_raw.decode()
        for forbidden in (
            "rs_provider_bound",
            "rs_stored_reference",
            "opaque-reasoning",
            "agent-secret",
            "tool-secret",
            "only-secret",
            "internal_chat_message_metadata_passthrough",
        ):
            assert forbidden not in serialized
        assert "provider_bindings=3" in note
        assert "reasoning_items=1" in note

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

        assert projection.body is not None, projection.diagnostic()
        assert json.loads(projection.body)["input"] == [
            {"type": "message", "role": "user", "content": "compact this"},
            {"type": "compaction_trigger"},
        ]
        assert projection.status == "projected"

    def test_rejects_compaction_trigger_with_unknown_fields(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body({"input": [{"type": "compaction_trigger", "unexpected": True}]})
        )

        assert projection.body is None
        assert projection.diagnostic() == "rejected unknown_compaction_trigger_field"

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

        assert projected_raw is not None, _note
        assert json.loads(projected_raw) == {"input": "hello", "store": False}

    def test_preserves_bare_compaction_trigger_as_portable_control_input(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body(
                {
                    "input": [
                        {"type": "compaction_trigger"},
                        {"type": "message", "role": "user", "content": "continue"},
                    ]
                }
            )
        )

        assert projection.body is not None, projection.diagnostic()
        projected = json.loads(projection.body)
        assert projected["input"] == [
            {"type": "compaction_trigger"},
            {"type": "message", "role": "user", "content": "continue"},
        ]

    def test_forces_stateless_responses_even_when_store_is_absent_or_true(self, subtests) -> None:
        for supplied in (False, True, None):
            with subtests.test(store=supplied):
                payload = {"input": "continue"}
                if supplied is not None:
                    payload["store"] = supplied

                _projection = rewrite.sanitize_responses_body(_body(payload))
                projected_raw = _projection.body
                note = _projection.diagnostic()

                assert projected_raw is not None, note
                assert json.loads(projected_raw) == {
                    "input": "continue",
                    "store": False,
                }
                if supplied is True:
                    assert "store_normalized=True" in note

    def test_marks_paired_empty_tool_outputs_without_admitting_empty_dialogue(
        self, subtests
    ) -> None:
        cases = (
            ("function_call", "arguments", "function_call_output"),
            ("custom_tool_call", "input", "custom_tool_call_output"),
        )
        for call_type, argument_field, output_type in cases:
            with subtests.test(call_type=call_type):
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

                assert projected_raw is not None, note
                projected = json.loads(projected_raw)["input"]
                assert projected[0]["call_id"] == projected[1]["call_id"]
                assert projected[1]["output"] == rewrite.EMPTY_TOOL_OUTPUT_MARKER
                assert "empty_tool_outputs=1" in note

        _projection = rewrite.sanitize_responses_body(
            _body({"input": [{"type": "message", "role": "assistant", "content": ""}]})
        )
        projected = _projection.body
        note = _projection.diagnostic()
        assert projected is None
        assert note == "rejected empty_text_content"

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
            with subtests.test(output=label):
                assert projected is None
                assert note == "rejected invalid_content"

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

        assert projected_raw is not None, note
        content = [item["content"] for item in json.loads(projected_raw)["input"]]
        assert content == [
            [{"type": "input_text", "text": "system"}],
            [{"type": "input_text", "text": "developer"}],
            [{"type": "input_text", "text": "user"}],
            "answerdeclined",
        ]

    def test_fails_closed_for_unknown_or_malformed_replay_shapes(self, subtests) -> None:
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
            with subtests.test(name=name):
                _projection = rewrite.sanitize_responses_body(raw)
                projected = _projection.body
                note = _projection.diagnostic()
                assert projected is None
                assert note.startswith("rejected "), note


class RequestSanitizationContracts:
    def test_strips_reasoning_and_encrypted(self):
        body = _request_body(
            [
                {"type": "reasoning", "encrypted_content": "gAAAA_secret"},
                {"type": "message", "role": "user", "content": "hello"},
            ],
            include=["reasoning.encrypted_content", "other"],
        )
        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        _ = _projection.diagnostic()
        obj = json.loads(cast("bytes", out))
        assert obj["input"] == [{"type": "message", "role": "user", "content": "hello"}]
        assert "reasoning.encrypted_content" not in obj["include"]

    def test_projects_agent_message_and_removes_encrypted_content(self):
        body = json.dumps(
            {
                "input": [
                    {"type": "reasoning", "encrypted_content": "gAAAA_replay_only"},
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
        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        note = _projection.diagnostic()
        obj = json.loads(cast("bytes", out))
        assert len(obj["input"]) == 1
        agent = obj["input"][0]
        assert (agent["role"], agent["phase"]) == ("assistant", "commentary")
        header, content = agent["content"].split("\n", 1)
        assert json.loads(header) == {
            "type": "agent_message",
            "author": "agent",
            "recipient": "user",
        }
        assert content == "reply"
        assert "required_agent_message_payload" not in cast("bytes", out).decode()
        assert "encrypted_blocks=1" in note
        assert "reasoning_items=1" in note
        assert "reasoning.encrypted_content" not in obj["include"]

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
                ]
            }
        ).encode()
        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        note = _projection.diagnostic()
        obj = json.loads(cast("bytes", out))
        assert "encrypted_blocks=2" in note
        _header, content = obj["input"][0]["content"].split("\n", 1)
        assert content == "beforeafter"
        assert "valid_required_payload" not in cast("bytes", out).decode()

    def test_rejects_unknown_fields_that_resemble_encrypted_content(self):
        body = json.dumps(
            {"input": [{"type": "custom_tool_call", "payload": {"type": "encrypted_content"}}]}
        ).encode()
        _projection = rewrite.sanitize_responses_body(body)
        out = _projection.body
        note = _projection.diagnostic()
        assert out is None
        assert note == "rejected unknown_call_field"

    def test_fail_closed_on_non_json(self):
        raw = b"not json at all"
        _projection = rewrite.sanitize_responses_body(raw)
        out = _projection.body
        note = _projection.diagnostic()
        assert out is None
        assert note == "rejected invalid_json"

    def test_fail_closed_on_json_values_that_are_not_response_objects(self, subtests):
        for raw in (b"[]", b"null", b'"text"'):
            with subtests.test(raw=raw):
                _projection = rewrite.sanitize_responses_body(raw)
                out = _projection.body
                note = _projection.diagnostic()
                assert out is None
                assert note == "rejected request_not_object"

    def test_request_sanitizer_fails_closed_when_mutation_cannot_be_serialized(self, *, mocker):
        raw = b'{"input":[{"type":"reasoning","encrypted_content":"opaque"},{"type":"message","role":"user","content":"continue"}]}'
        mocker.patch.object(rewrite.json, "dumps", side_effect=TypeError("unsupported"))
        _projection = rewrite.sanitize_responses_body(raw)
        out = _projection.body
        note = _projection.diagnostic()
        assert out is None
        assert note == "rejected serialization_failed"

    def test_deep_request_fails_closed(self) -> None:
        nested = '{"x":' * 496 + "0" + "}" * 496
        raw = ('{"input":[{"type":"message","role":"user","content":' + nested + "}]}").encode()
        projection = rewrite.sanitize_responses_body(raw)
        assert projection.body is None
        assert projection.diagnostic().startswith("rejected ")
