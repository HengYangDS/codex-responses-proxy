"""Fixtures shared by empty-response projection and transport contracts."""

from __future__ import annotations

import json

EMPTY_RESPONSE = (
    b'{"error":{"message":"official provider returned an empty response",'
    b'"type":"dmx_api_error","code":"empty_response"}}'
)
UNKNOWN_477 = b'{"error":{"type":"dmx_api_error","code":"other"}}'
SUCCESS = b'{"id":"resp_recovered","status":"completed"}'


def body(payload: object) -> bytes:
    """Encode one deterministic UTF-8 JSON request body."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def semantic_body() -> bytes:
    """Build representative provider-bound history for projection contracts."""
    return body(
        {
            "model": "gpt-5.6-terra",
            "stream": False,
            "previous_response_id": "resp_provider_state",
            "conversation": {"id": "conversation_provider_state"},
            "prompt_cache_key": "cache_provider_state",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {
                    "type": "reasoning",
                    "id": "reasoning_provider_state",
                    "encrypted_content": "opaque_provider_state",
                    "summary": [],
                },
                {
                    "type": "message",
                    "id": "message_provider_id",
                    "status": "completed",
                    "role": "developer",
                    "content": "current policy",
                },
                {
                    "type": "agent_message",
                    "id": "agent_provider_id",
                    "author": "planner",
                    "recipient": "user",
                    "phase": "commentary",
                    "content": [
                        {"type": "input_text", "text": "第一段 🧭"},
                        {"type": "input_text", "text": "second segment"},
                    ],
                },
                {
                    "type": "function_call",
                    "id": "function_provider_id",
                    "status": "completed",
                    "call_id": "function-1",
                    "name": "lookup",
                    "arguments": '{"city":"杭州"}',
                    "namespace": "weather",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "function_call_output",
                    "id": "function_output_provider_id",
                    "status": "completed",
                    "call_id": "function-1",
                    "output": "晴朗",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "custom_tool_call",
                    "id": "custom_provider_id",
                    "status": "completed",
                    "call_id": "custom-1",
                    "name": "terminal",
                    "input": "printf ok",
                    "namespace": "local",
                    "caller": {"type": "direct"},
                },
                {
                    "type": "custom_tool_call_output",
                    "id": "custom_output_provider_id",
                    "status": "completed",
                    "call_id": "custom-1",
                    "output": [
                        {"type": "input_text", "text": "line one"},
                        {"type": "input_text", "text": "第二行"},
                    ],
                    "caller": {"type": "direct"},
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "continue from the tool results",
                },
            ],
        }
    )
