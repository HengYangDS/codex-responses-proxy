"""Provider-bound history payload for projection contracts."""

from __future__ import annotations

HISTORY_PAYLOAD = {
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
                {"type": "output_text", "text": "visible answer", "annotations": [], "logprobs": []}
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
            "output": [{"type": "encrypted_content", "encrypted_content": "only-secret"}],
            "internal_chat_message_metadata_passthrough": {"opaque": True},
        },
        {"type": "message", "role": "user", "content": "continue here"},
    ],
}
