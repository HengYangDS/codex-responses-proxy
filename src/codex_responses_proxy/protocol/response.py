"""Validate live Responses payloads without changing their bytes.

Provider portability is enforced when a later request replays prior output.
The live response must retain encrypted control data until Codex has completed
the current turn's decryption and tool dispatch.
"""

from __future__ import annotations

import json

_JSON_TERMINALS = frozenset(("completed", "incomplete"))


def validate_sse_event(raw_event: bytes) -> bytes:
    """Validate JSON-bearing SSE data lines and return the exact event bytes."""
    for line in raw_event.splitlines():
        if not line.startswith(b"data: "):
            continue
        data = line[6:]
        if data == b"[DONE]":
            continue
        try:
            json.loads(data)
        except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
            raise ValueError("invalid_responses_event") from exc
    return raw_event


def validate_json_response(raw_response: bytes) -> bytes:
    """Require a terminal Responses document and return its exact bytes."""
    try:
        payload = json.loads(raw_response)
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("invalid_responses_success_body") from exc
    if not isinstance(payload, dict) or payload.get("status") not in _JSON_TERMINALS:
        raise ValueError("invalid_responses_success_body")
    return raw_response
