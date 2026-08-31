"""Provider-bound history projection contracts."""

from __future__ import annotations

import json

from codex_responses_proxy.protocol import content as portable_content
from codex_responses_proxy.protocol import request as rewrite
from tests.protocol.history_fixture import HISTORY_PAYLOAD
from tests.protocol.test_request import _body


class ProviderPortableHistoryTests:
    """The normal outbound path owns provider-portable history."""

    def test_projects_standalone_namespaced_tool_delivery_to_message(self) -> None:
        raw = _body(
            {
                "model": "gpt-test",
                "input": [
                    {
                        "type": "function_call_output",
                        "id": "fco_delivery",
                        "name": "send_message_to_thread",
                        "namespace": "codex_app",
                        "output": "<codex_delegation>delivered</codex_delegation>",
                        "internal_chat_message_metadata_passthrough": {"opaque": True},
                    }
                ],
            }
        )

        projection = rewrite.sanitize_responses_body(raw)

        assert projection.status == "projected", projection.diagnostic()
        assert projection.body is not None
        item = json.loads(projection.body)["input"][0]
        assert item == {
            "type": "message",
            "role": "assistant",
            "phase": "commentary",
            "content": '{"type":"tool_delivery","name":"send_message_to_thread","namespace":"codex_app"}\n'
            "<codex_delegation>delivered</codex_delegation>",
        }

    def test_rejects_incomplete_or_hybrid_standalone_tool_delivery(self) -> None:
        invalid_items = (
            {
                "type": "function_call_output",
                "id": "fco_delivery",
                "namespace": "codex_app",
                "output": "delivered",
            },
            {
                "type": "function_call_output",
                "id": "fco_delivery",
                "name": "send_message_to_thread",
                "namespace": "codex_app",
                "call_id": "call_missing",
                "output": "delivered",
            },
        )

        for item in invalid_items:
            projection = rewrite.sanitize_responses_body(
                _body({"model": "gpt-test", "input": [item]})
            )
            assert projection.status == "rejected"

    def test_projects_provider_bound_history_to_closed_portable_grammar(self) -> None:
        raw = _body(HISTORY_PAYLOAD)

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
            {"type": "input_text", "text": portable_content.OPAQUE_CONTENT_MARKER}
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
