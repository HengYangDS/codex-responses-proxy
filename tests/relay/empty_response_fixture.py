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
    """Return representative history crossing every projection owner."""
    return body(
        {
            "previous_response_id": "stale",
            "conversation": {"id": "stale"},
            "prompt_cache_key": "stale",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {"type": "reasoning", "encrypted_content": "opaque", "summary": []},
                {"type": "message", "role": "developer", "content": "policy"},
                {
                    "type": "agent_message",
                    "author": "planner",
                    "recipient": "user",
                    "content": [{"type": "output_text", "text": "plan"}],
                },
                {
                    "type": "function_call",
                    "call_id": "f",
                    "name": "lookup",
                    "arguments": "{}",
                },
                {"type": "function_call_output", "call_id": "f", "output": "ok"},
                {"type": "custom_tool_call", "call_id": "c", "name": "shell", "input": "pwd"},
                {"type": "custom_tool_call_output", "call_id": "c", "output": "here"},
                {"type": "message", "role": "user", "content": "continue"},
            ],
        }
    )
