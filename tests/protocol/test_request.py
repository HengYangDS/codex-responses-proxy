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

    def test_reports_recognized_unimplemented_standard_item_as_schema_drift(
        self,
    ) -> None:
        projection = rewrite.sanitize_responses_body(_body({"input": [{"type": "shell_call"}]}))

        assert projection.body is None
        assert projection.diagnostic() == "rejected schema_drift"

    def test_drops_current_codex_local_shell_history_as_one_pair(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body(
                {
                    "input": [
                        {
                            "type": "local_shell_call",
                            "id": "lsh_1",
                            "call_id": "call_1",
                            "status": "completed",
                            "action": {
                                "type": "exec",
                                "command": ["printf", "ok"],
                                "timeout_ms": 0,
                                "working_directory": "workspace",
                                "env": {"MODE": "test"},
                                "user": "runner",
                            },
                        },
                        {
                            "type": "function_call_output",
                            "call_id": "call_1",
                            "output": "ok",
                        },
                        {"type": "message", "role": "user", "content": "continue"},
                    ]
                }
            )
        )

        assert projection.body is not None, projection.diagnostic()
        assert json.loads(projection.body)["input"] == [
            {"type": "message", "role": "user", "content": "continue"}
        ]
        assert projection.metrics.changed_items == 2

    def test_rejects_unpaired_local_shell_call(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body(
                {
                    "input": [
                        {
                            "type": "local_shell_call",
                            "call_id": "call_1",
                            "status": "completed",
                            "action": {"type": "exec", "command": ["printf", "ok"]},
                        },
                        {"type": "message", "role": "user", "content": "continue"},
                    ]
                }
            )
        )

        assert projection.body is None
        assert projection.diagnostic() == "rejected incomplete_local_shell_pair"

    def test_rejects_invalid_local_shell_call_fields(self, subtests) -> None:
        cases = {
            "missing status": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "action": {"type": "exec", "command": ["printf", "ok"]},
            },
            "invalid status": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "done",
                "action": {"type": "exec", "command": ["printf", "ok"]},
            },
            "unknown action field": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["printf", "ok"],
                    "future": True,
                },
            },
            "boolean timeout": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["printf", "ok"],
                    "timeout_ms": True,
                },
            },
            "negative timeout": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["printf", "ok"],
                    "timeout_ms": -1,
                },
            },
            "overflow timeout": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["printf", "ok"],
                    "timeout_ms": 2**64,
                },
            },
            "invalid environment": {
                "type": "local_shell_call",
                "call_id": "call_1",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["printf", "ok"],
                    "env": {"COUNT": 1},
                },
            },
        }
        output = {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "ok",
        }

        for name, call in cases.items():
            with subtests.test(name=name):
                projection = rewrite.sanitize_responses_body(_body({"input": [call, output]}))

                assert projection.body is None
                assert projection.diagnostic() == "rejected invalid_local_shell_call"

    def test_rejects_compaction_trigger_with_unknown_fields(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body({"input": [{"type": "compaction_trigger", "unexpected": True}]})
        )

        assert projection.body is None
        assert projection.diagnostic() == "rejected unknown_compaction_trigger_field"

    def test_preserves_clean_string_input_while_removing_top_level_bindings(
        self,
    ) -> None:
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

    def test_projects_namespaced_function_output_without_forwarding_namespace(
        self,
    ) -> None:
        projection = rewrite.sanitize_responses_body(
            _body(
                {
                    "input": [
                        {
                            "type": "function_call",
                            "call_id": "namespaced-call",
                            "name": "read_resource",
                            "namespace": "workspace",
                            "arguments": "{}",
                        },
                        {
                            "type": "function_call_output",
                            "call_id": "namespaced-call",
                            "name": "read_resource",
                            "namespace": "workspace",
                            "output": "available",
                        },
                    ]
                }
            )
        )

        assert projection.body is not None, projection.diagnostic()
        assert json.loads(projection.body)["input"] == [
            {
                "type": "function_call",
                "call_id": "namespaced-call",
                "name": "read_resource",
                "namespace": "workspace",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": "namespaced-call",
                "output": "available",
            },
        ]

    def test_rejects_namespace_on_custom_tool_output(self) -> None:
        projection = rewrite.sanitize_responses_body(
            _body(
                {
                    "input": [
                        {
                            "type": "custom_tool_call",
                            "call_id": "custom-call",
                            "name": "apply_patch",
                            "input": "patch",
                        },
                        {
                            "type": "custom_tool_call_output",
                            "call_id": "custom-call",
                            "namespace": "workspace",
                            "output": "done",
                        },
                    ]
                }
            )
        )

        assert projection.body is None
        assert projection.diagnostic() == "rejected unknown_output_field"

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
                {
                    "input": [
                        {
                            "type": "function_call_output",
                            "call_id": "missing",
                            "output": "x",
                        }
                    ]
                }
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
                        {
                            "type": "custom_tool_call_output",
                            "call_id": "c",
                            "output": "x",
                        },
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
            {
                "input": [
                    {
                        "type": "custom_tool_call",
                        "payload": {"type": "encrypted_content"},
                    }
                ]
            }
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
