"""DMX HTTP 477 wire classification, cooldown identity, and exhaustion."""

from __future__ import annotations

import hashlib
import json

POLICY_VERSION = "empty-response-retry-v1"
FAILURE_COOLDOWN_SECONDS = 30
FAILURE_CACHE_CAPACITY = 1024
EXHAUSTED_MESSAGE = "DMX upstream returned empty responses after bounded retries"
EXHAUSTED_CODE = "dmx_empty_response_exhausted"


def is_retryable_failure(status: int, payload: bytes) -> bool:
    """Return whether an upstream response is the exact DMX empty-response error."""
    if status != 477:
        return False
    try:
        document = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    error = document.get("error") if isinstance(document, dict) else None
    return (
        isinstance(error, dict)
        and error.get("type") == "dmx_api_error"
        and error.get("code") == "empty_response"
    )


def request_fingerprint(request: bytes) -> str:
    """Return a policy-versioned identity for one normalized request."""
    return hashlib.sha256(POLICY_VERSION.encode() + request).hexdigest()
