#!/usr/bin/env python3
"""dmx-responses-proxy — strip un-verifiable encrypted reasoning from Codex → dmxapi.

Why this exists
---------------
Codex CLI (closed binary) uses the OpenAI *Responses* wire API. Each turn the model
returns a ``reasoning`` item carrying ``encrypted_content`` (a provider-encrypted
``gAAAAAB...`` Fernet blob). Codex persists these and *replays* them on every later
turn. dmxapi (https://www.dmxapi.cn) encrypts those blobs with its own key and, after
key rotation / backend routing, can no longer decrypt a blob it is handed back →

    HTTP 400 "The encrypted content gAAA... could not be verified.
    Reason: Encrypted content could not be decrypted or parsed."  (invalid_encrypted_content)

Codex has no config switch to stop the replay (verified against the v0.142.5 config
schema), and it is a compiled binary we cannot patch. So we sit a tiny local proxy
between Codex and dmxapi and remove the replayed blobs from each outbound request.
The model still reasons every turn; it just isn't handed stale replayed reasoning
items that the third-party endpoint cannot verify. Typed encrypted-content blocks in
agent messages are preserved because their schema requires the payload. This mirrors
the compatible network-edge approach without rewriting local conversation history.

Design guarantees
-----------------
* Transparent: forwards method, path, query, headers (incl. ``Authorization``) and
  body to the real upstream. Codex's keychain Bearer token passes through untouched.
* Surgical: only mutates JSON bodies of POSTs whose path contains ``/responses``.
  For those it drops (a) top-level replayed ``reasoning`` input items, (b) historical
  ``input_image`` items whose URL cannot be fetched remotely, and (c)
  ``reasoning.encrypted_content`` from the ``include[]`` list. Other typed
  ``encrypted_content`` blocks stay intact because their schema requires the payload.
  SSE output is still stripped before Codex persists it as later history.
* Fail-open: any parse/transform error → the *original* bytes are forwarded unchanged.
  Worst case equals today's behavior; it can never harden into a new failure mode.
* Streaming: the upstream SSE response is streamed back chunk-by-chunk unbuffered.
* Stdlib only: no third-party deps, no build step.
"""

from __future__ import annotations

import json
import os
import sys
import time
import socket
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("DMX_UPSTREAM", "https://www.dmxapi.cn").rstrip("/")
HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
LOG_PATH = os.environ.get("DMX_PROXY_LOG", os.path.expanduser("~/.codex/log/dmx-responses-proxy.log"))
RESPONSES_MAX_CONCURRENCY = int(os.environ.get("DMX_RESPONSES_MAX_CONCURRENCY", "64"))
RESPONSES_QUEUE_TIMEOUT = float(os.environ.get("DMX_RESPONSES_QUEUE_TIMEOUT", "120"))
UPSTREAM_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_TIMEOUT", "900"))
UPSTREAM_READ_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_READ_TIMEOUT", "240"))
# DMX rejects deterministic large replay payloads with an HTTP 400
# ``response_failed`` result. This limit is deliberately conservative: live probes
# on 2026-07-14 accepted pair-valid payloads in the 482--513 KiB range.
RESPONSE_FAILED_COMPACTION_BUDGET = int(
    os.environ.get("DMX_RESPONSE_FAILED_COMPACTION_BUDGET", str(512 * 1024))
)
# Each fallback stage must make a material reduction. A small replay trim often
# remains inside the upstream failure regime, while a half-window suffix was
# accepted by live probes.
RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR = 2
RESPONSE_FAILED_MAX_STAGES = max(0, int(os.environ.get("DMX_RESPONSE_FAILED_MAX_STAGES", "3")))
_RESPONSES_SEM = threading.BoundedSemaphore(max(1, RESPONSES_MAX_CONCURRENCY))
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RESPONSES = 0
_REQUEST_SEQ = 0

# Cross-platform hardening: never route upstream calls through a system/registry/env
# HTTP proxy. On macOS and Windows, urllib.request.getproxies() consults the OS proxy
# settings (System Configuration / registry), so a host behind a corporate proxy could
# silently tunnel our upstream calls. We open every upstream request through an opener
# with an EMPTY ProxyHandler, forcing a direct connection regardless of host config.
# (Same effect on Linux, which only reads env vars — this just makes it explicit.)
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def release_version() -> str:
    """Read the packaged release identity without making startup depend on CWD."""
    candidates = (
        Path(__file__).resolve().parents[1] / "VERSION",
        Path(__file__).resolve().parents[2] / "VERSION",
    )
    for candidate in candidates:
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "0+unknown"


def _urlopen(req, timeout):
    """urlopen that always bypasses any system/env HTTP proxy (see _OPENER)."""
    return _OPENER.open(req, timeout=timeout)

# Headers that belong to *this* hop and must not be relayed verbatim.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "accept-encoding",  # force identity so upstream doesn't gzip past our stream copy
}


class _ResilientProxyServer(ThreadingHTTPServer):
    """Threading HTTP server hardened for subagent fan-out.

    Codex subagents fan out into many concurrent /v1/responses SSE streams. The
    stdlib default listen backlog (``request_queue_size = 5``) means the 6th+
    simultaneous connection can be RST by the OS before ``accept()`` runs — the
    ``ConnectionResetError: [Errno 54] Connection reset by peer`` seen in the log.
    Raise the backlog well above any realistic fan-out, reuse the address for clean
    restarts, and run handler threads as daemons so a dropped client never leaks a
    thread. This addresses the LOCAL connection-stability failure (distinct from
    upstream dmxapi stream flakiness, which the reconnect logic handles).
    """
    request_queue_size = 256
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self):
        # Disable Nagle so SSE chunks flush promptly to the local client.
        super().server_bind()
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

    def handle_error(self, request, client_address):
        # A client that resets/closes mid-stream is normal at subagent turn end;
        # log quietly instead of dumping a full traceback to stderr.
        import sys as _sys
        exc = _sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            _log(f"  client {client_address} reset/closed mid-request ({exc.__class__.__name__})")
            return
        super().handle_error(request, client_address)


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as fh:
            fh.write(line)
    except Exception:
        pass
    sys.stderr.write(line)


def _next_request_id() -> int:
    global _REQUEST_SEQ
    with _ACTIVE_LOCK:
        _REQUEST_SEQ += 1
        return _REQUEST_SEQ


def _is_transient_upstream(code: int, err_body: bytes) -> str:
    """Classify an upstream failure's retry disposition.

    Returns one of:
      "full"    — genuine transient (429/5xx or a classified upstream empty
                  response); retry up to the full budget.
      "once"    — a transient validation failure (``invalid_payload`` or a
                  schema mismatch). The request body is preserved and retried
                  once after a bounded delay.
      "full"    — an explicit upstream Responses ``response_failed`` execution
                  error. HTTP 400 proves that this request was not accepted as a
                  response; it can use the ordinary bounded retry budget.
      ""        — not retryable (encrypted-content complaint or other genuine 4xx).
    """
    if code in (429, 500, 502, 503, 504, 524):
        return "full"
    if code == 477:
        try:
            payload = json.loads(err_body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        # DMX uses non-standard HTTP 477 when its selected upstream returns no
        # output. It is not a client validation failure: the same preserved
        # request may succeed when retried, so treat only the explicit
        # ``empty_response`` contract as a bounded transient. Other unknown
        # 477 responses remain visible to the caller unchanged.
        error = payload.get("error") if isinstance(payload, dict) else None
        if (
            isinstance(error, dict)
            and error.get("type") == "dmx_api_error"
            and error.get("code") == "empty_response"
        ):
            return "full"
        return ""
    if code == 400:
        try:
            low = err_body.lower()
        except Exception:
            return ""
        if b"invalid_encrypted_content" in low or b"could not be verified" in low:
            return ""
        # Some upstream gateways collapse a failed Responses execution into
        # HTTP 400 even when the request has passed validation. The exact
        # ``response_failed`` payload was observed on 2026-07-14. HTTP 400 means
        # the request was rejected before a response was accepted, so it may use
        # the same bounded retry budget as other upstream execution failures.
        if b"response_failed" in low or b"openai responses stream failed" in low:
            return "full"
        if b"invalid_payload" in low or b"does not match the expected schema" in low:
            return "once"
    return ""


def _dmx_empty_response_exhausted(attempts: int) -> bytes:
    """Return a stable local 503 after DMX exhausts empty-response retries.

    HTTP 477 is an upstream-specific extension. Once the proxy has classified
    it and exhausted its bounded recovery budget, preserve the retryable
    semantics with standard HTTP 503 rather than exposing an unknown status to
    the client. The response contains no upstream payload or request content.
    """
    return json.dumps({
        "error": {
            "message": "DMX upstream returned empty responses after bounded retries",
            "type": "upstream_unavailable",
            "code": "dmx_empty_response_exhausted",
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()


def _response_failed_recovery_exhausted(attempts: int) -> bytes:
    """Return a retryable local failure after bounded response recovery.

    An upstream ``response_failed`` is an execution failure, not a client-side
    schema rejection.  Returning the original HTTP 400 teaches Codex to treat
    the failed turn as an invalid request and prevents its own retry loop from
    taking over.  Once the proxy has exhausted its deliberately bounded,
    semantics-preserving recovery options, expose a standard retryable status
    instead.  Do not include the upstream body or request content.
    """
    return json.dumps({
        "error": {
            "message": "DMX upstream rejected bounded Responses recovery; retry the turn",
            "type": "upstream_unavailable",
            "code": "response_failed_recovery_exhausted",
            "attempts": attempts,
        },
    }, separators=(",", ":")).encode()


def _strip_reasoning_encrypted_content_from_sse_event(obj):
    """Remove only reasoning replay state from a streamed provider response.

    The Responses schema uses ``encrypted_content`` in more than one typed item.
    It is safe to remove from a ``reasoning`` output item because the next request
    drops that top-level item. It is *not* safe to remove from a typed
    ``encrypted_content`` block inside an agent message: that field is required
    when the block is replayed. Traverse the event but mutate only reasoning items.
    """
    removed = 0
    if isinstance(obj, dict):
        if obj.get("type") == "reasoning" and "encrypted_content" in obj:
            del obj["encrypted_content"]
            removed += 1
        for value in obj.values():
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    elif isinstance(obj, list):
        for value in obj:
            removed += _strip_reasoning_encrypted_content_from_sse_event(value)
    return removed


def _drop_malformed_encrypted_content_blocks(obj):
    """Drop only legacy typed blocks missing their required payload.

    Earlier proxy builds recursively erased encrypted payloads from streamed agent
    messages, leaving ``{"type": "encrypted_content"}`` in local history. The
    upstream rightfully rejects that invalid schema. Repair the replay at the
    network boundary by removing just blocks *without* an ``encrypted_content``
    field; valid typed blocks remain byte-for-byte represented in the JSON object.
    """
    dropped = 0
    if isinstance(obj, dict):
        for field in ("content", "output"):
            items = obj.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "encrypted_content"
                    and "encrypted_content" not in item
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                obj[field] = kept
        for value in obj.values():
            dropped += _drop_malformed_encrypted_content_blocks(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _drop_malformed_encrypted_content_blocks(value)
    return dropped


def _strip_replayed_reasoning_items(payload):
    """Remove replayable reasoning items without touching typed message content.

    ``encrypted_content`` is overloaded in the Responses schema. It is stale
    provider-owned replay state on a top-level ``reasoning`` input item, but it is
    a *required payload field* for ``{"type": "encrypted_content"}`` blocks in
    ``agent_message.content``. A generic recursive deletion destroys the latter
    and turns a valid agent message into an invalid one. Drop the whole top-level
    reasoning item instead; retain every other encrypted-content block verbatim.
    """
    dropped_items = 0
    preserved_agent_blocks = 0
    inp = payload.get("input")
    if not isinstance(inp, list):
        return dropped_items, preserved_agent_blocks

    kept = []
    for item in inp:
        if isinstance(item, dict) and item.get("type") == "reasoning":
            dropped_items += 1
            continue
        if isinstance(item, dict) and item.get("type") == "agent_message":
            content = item.get("content")
            if isinstance(content, list):
                preserved_agent_blocks += sum(
                    1
                    for block in content
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "encrypted_content"
                        and "encrypted_content" in block
                    )
                )
        kept.append(item)
    if dropped_items:
        payload["input"] = kept
    return dropped_items, preserved_agent_blocks


_TOOL_CALL_TYPES = frozenset(("custom_tool_call", "function_call"))
_TOOL_OUTPUT_TYPES = frozenset(("custom_tool_call_output", "function_call_output"))


def _tool_pair_boundary_is_safe(items, start):
    """True if a retained input suffix has no orphaned tool-call relationship.

    Responses inputs encode custom/function tool calls and their outputs as
    separate adjacent history items. A raw byte or item-count suffix can retain an
    output whose call was discarded, which the upstream correctly rejects. We only
    remove a contiguous oldest prefix, and admit a suffix when every retained
    call/output pair is internally complete. A call with no output is allowed: it
    may be the live continuation of a pending call, but a retained output without
    its call is never valid.
    """
    calls = set()
    for item in items[start:]:
        if not isinstance(item, dict):
            continue
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        item_type = item.get("type")
        if item_type in _TOOL_CALL_TYPES:
            calls.add(call_id)
        elif item_type in _TOOL_OUTPUT_TYPES:
            # A Responses replay output is meaningful only after its matching
            # call. Checking ordering, not just set membership, also rules out a
            # malformed retained suffix that happens to repeat a call id later.
            if call_id not in calls:
                return False
    return True


def _compact_response_failed_request(raw: bytes, budget: int | None = None):
    """Build one pair-safe compact fallback after an explicit upstream failure.

    This is intentionally not a general context-window implementation. It runs
    only in the HTTP-400 ``response_failed`` branch, keeps the newest contiguous
    input suffix, and removes *only* the oldest prefix. The compact copy removes
    ``prompt_cache_key`` because it refers to the full historical prompt. The
    original request bytes remain untouched for the primary attempt and for every
    other error type.

    ``budget`` is an internal retry-stage ceiling. Each successive stage must be
    no larger than half the preceding request, preventing no-op fallbacks such as
    a one-item trim of an already sub-512-KiB failed replay.

    Return ``(compact_bytes, metrics)`` only when a pair-valid suffix including
    the final input item fits the requested full-request budget. Otherwise return
    ``(None, None)`` and let the original upstream response pass through.
    """
    if budget is None:
        budget = RESPONSE_FAILED_COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    # A fallback must reduce the request materially even when it is already below
    # the normal ceiling. Without this gate an explicit response_failed at 485 KiB
    # would only drop one ancient item and reproduce the same upstream failure.
    budget = min(budget, max(1, len(raw) // RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR))
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or len(original_items) < 2:
        return None, None

    # The fallback must retain the latest user context, even when later tool
    # plumbing consumes most of the budget. If it cannot, the safe answer is no
    # fallback rather than silently changing the user's current request.
    latest_user_index = max(
        (
            index
            for index, item in enumerate(original_items)
            if (
                isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    # Begin with the oldest safe boundary that meets the full JSON-byte budget.
    # Moving the boundary right removes more *oldest* state and is the only allowed
    # recovery action. A copied dict is used so the original payload object/bytes
    # cannot be mutated by the failed fallback construction.
    smallest = None
    for start in range(1, latest_user_index + 1):
        if not _tool_pair_boundary_is_safe(original_items, start):
            continue
        candidate = dict(payload)
        candidate["input"] = original_items[start:]
        candidate.pop("prompt_cache_key", None)
        try:
            compact = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
        except Exception:
            return None, None
        metrics = {
                "original_bytes": len(raw),
                "budget_bytes": budget,
                "compact_bytes": len(compact),
                "removed_inputs": start,
                "retained_inputs": len(original_items) - start,
                "prompt_cache_key_removed": "prompt_cache_key" in payload,
        }
        if len(compact) <= budget:
            return compact, metrics
        # A trailing sequence of complete tool outputs can itself exceed the
        # desired byte target. It is still safer and more useful to send the
        # smallest pair-valid suffix than to repeat a known rejected request.
        # We retain the candidate only after confirming it is an actual reduction.
        if len(compact) < len(raw) and (smallest is None or len(compact) < len(smallest[0])):
            smallest = (compact, metrics)
    if smallest is not None:
        compact, metrics = smallest
        metrics["budget_met"] = False
        return compact, metrics
    return None, None


def _recover_response_failed_dialogue(raw: bytes, budget: int | None = None):
    """Build the final, text-only recovery request for ``response_failed``.

    This is intentionally narrower than general context compaction.  It runs
    only after the pair-safe suffix fallback has itself been explicitly rejected
    by the upstream.  It preserves the newest developer/system instruction and
    the latest user request while omitting replayed assistant and tool state.
    The stored Codex history is never changed; this is a one-request network
    fallback for an upstream that rejected both the original and pair-safe
    replay forms.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    original_items = payload.get("input")
    if not isinstance(original_items, list) or not original_items:
        return None, None

    latest_user_index = max(
        (
            index
            for index, item in enumerate(original_items)
            if (
                isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("role") == "user"
            )
        ),
        default=-1,
    )
    if latest_user_index < 0:
        return None, None

    # Keep only the most recent instruction anchor before the active user
    # request.  Older instructions and all replay/tool state were already
    # rejected by the upstream; retaining them would turn this into an
    # unbounded history rewrite rather than a bounded recovery attempt.
    start = latest_user_index
    for index in range(latest_user_index, -1, -1):
        item = original_items[index]
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") in ("developer", "system")
        ):
            start = index
            break

    # This final fallback is intentionally a two-message envelope, not a
    # shortened transcript.  Keeping intervening user messages would recreate
    # a history replay by another name and would make its semantics harder to
    # reason about.  The instruction anchor is optional because a valid
    # Responses request can consist of the user's current request alone.
    dialogue = []
    if start != latest_user_index:
        dialogue.append(original_items[start])
    dialogue.append(original_items[latest_user_index])

    candidate = dict(payload)
    candidate["input"] = dialogue
    candidate.pop("prompt_cache_key", None)
    try:
        recovery = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
    except Exception:
        return None, None

    if budget is None:
        budget = RESPONSE_FAILED_COMPACTION_BUDGET
    if not isinstance(budget, int) or budget <= 0:
        return None, None
    budget = min(budget, max(1, len(raw) // RESPONSE_FAILED_COMPACTION_RATIO_DENOMINATOR))
    if len(recovery) > budget or len(recovery) >= len(raw):
        return None, None
    return recovery, {
        "original_bytes": len(raw),
        "recovery_bytes": len(recovery),
        "budget_bytes": budget,
        "retained_messages": len(dialogue),
        "dropped_input_items": len(original_items) - len(dialogue),
        "prompt_cache_key_removed": "prompt_cache_key" in payload,
    }

def _is_replayable_remote_image_url(value):
    """True only for URL schemes the third-party Responses endpoint accepts."""
    if not isinstance(value, str) or not value:
        return False
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        # Accessing .port validates an explicit port and raises ValueError when
        # it is non-numeric or outside the valid TCP range.
        _ = parsed.port
    except ValueError:
        return False
    return True


def _strip_unreplayable_images(obj):
    """Drop historical input images that cannot be replayed to the provider.

    Codex preserves local tool-output images in history. Third-party Responses
    endpoints validate image_url as a remotely fetchable URL, so local paths and
    data URLs reject the whole next turn. Keep only http(s) images and retain all
    neighboring text/tool output.
    """
    dropped = 0
    if isinstance(obj, dict):
        for field in ("output", "content"):
            items = obj.get(field)
            if not isinstance(items, list):
                continue
            kept = []
            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "input_image"
                    and not _is_replayable_remote_image_url(item.get("image_url"))
                ):
                    dropped += 1
                    continue
                kept.append(item)
            if len(kept) != len(items):
                obj[field] = kept
        for value in obj.values():
            dropped += _strip_unreplayable_images(value)
    elif isinstance(obj, list):
        for value in obj:
            dropped += _strip_unreplayable_images(value)
    return dropped


def sanitize_responses_body(raw: bytes) -> tuple[bytes, str]:
    """Return (possibly-rewritten body, note). Fail-open: on any error return raw."""
    try:
        payload = json.loads(raw)
    except Exception as exc:  # not JSON we understand → leave untouched
        return raw, f"passthrough (non-json: {exc.__class__.__name__})"

    if not isinstance(payload, dict):
        return raw, "passthrough (json not object)"

    # (a) Drop replayed top-level reasoning items. Do not recursively delete
    # encrypted_content: agent_message encrypted-content blocks require it.
    dropped_items, preserved_agent_blocks = _strip_replayed_reasoning_items(payload)

    # (b) Repair only malformed typed encrypted-content blocks created by old
    # local proxy versions. Valid agent-message blocks remain intact.
    dropped_malformed_encrypted_blocks = _drop_malformed_encrypted_content_blocks(payload)

    # (c) Drop local-path / data-URL image replay items that this third-party
    # endpoint rejects. Valid remote http(s) images stay intact.
    dropped_images = _strip_unreplayable_images(payload)

    # (d) Stop asking the API to return new replayed reasoning state.
    include = payload.get("include")
    include_trimmed = False
    if isinstance(include, list):
        new_inc = [x for x in include if x != "reasoning.encrypted_content"]
        if len(new_inc) != len(include):
            payload["include"] = new_inc
            include_trimmed = True

    if not (
        dropped_items
        or dropped_malformed_encrypted_blocks
        or dropped_images
        or include_trimmed
    ):
        return raw, "clean (nothing to strip)"

    try:
        new_raw = json.dumps(payload).encode("utf-8")
    except Exception as exc:
        return raw, f"passthrough (reserialize failed: {exc.__class__.__name__})"

    return new_raw, (
        f"stripped reasoning_items={dropped_items} "
        f"malformed_encrypted_blocks={dropped_malformed_encrypted_blocks} "
        f"local_image_items={dropped_images} "
        f"agent_message_encrypted={preserved_agent_blocks} "
        f"include_trimmed={include_trimmed}"
    )




def sanitize_sse_event(raw_event: bytes) -> tuple[bytes, int]:
    """Strip encrypted_content from one SSE event block; preserve SSE framing."""
    if b"encrypted_content" not in raw_event:
        return raw_event, 0
    out_lines = []
    removed_total = 0
    for line in raw_event.splitlines(keepends=True):
        if line.startswith(b"data: "):
            prefix = b"data: "
            suffix = b"\n" if line.endswith(b"\n") else b""
            data = line[len(prefix):]
            if suffix:
                data = data[:-1]
            if data.strip() == b"[DONE]":
                out_lines.append(line)
                continue
            try:
                obj = json.loads(data)
                removed = _strip_reasoning_encrypted_content_from_sse_event(obj)
                if removed:
                    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                    line = prefix + data + suffix
                    removed_total += removed
            except Exception:
                pass
        out_lines.append(line)
    return b"".join(out_lines), removed_total


def _read_one_sse_stream(handler, resp, path, request_id, on_first_write):
    """Relay a single upstream SSE stream to the client, stripping encrypted_content.

    Returns a dict describing how the stream ended:
      {"terminal": <event|None>, "events": int, "wrote_downstream": bool,
       "detail": "completed"|"failed"|"incomplete"|"timeout"|"incomplete_read"|"eof",
       "error": <exc|None>}

    Retry-safety strategy: the leading prelude events (response.created /
    response.in_progress) are IDENTICAL for every attempt and carry no content, so
    we BUFFER them and only flush once the stream proves healthy — i.e. once a
    substantive event (anything past the prelude) or a terminal event arrives. If
    the stream dies while still in the prelude, nothing was written downstream
    (`wrote_downstream` stays False) and the caller can safely reconnect without
    the client ever seeing a duplicate response.created. `on_first_write()` fires
    once, right before the first real downstream byte, so headers are sent lazily.
    """
    import http.client
    buf = b""
    stripped_events = 0
    stripped_keys = 0
    event_count = 0
    terminal_event = None
    upstream_incomplete = False
    upstream_timeout = False
    upstream_error = None
    wrote_downstream = False
    prelude = []          # buffered created/in_progress events, not yet flushed
    prelude_flushed = False

    _PRELUDE_TYPES = (b'"type":"response.created"', b'"type": "response.created"',
                      b'"type":"response.in_progress"', b'"type": "response.in_progress"')

    def _raw_write(data: bytes):
        nonlocal wrote_downstream
        if not wrote_downstream:
            on_first_write()
            wrote_downstream = True
        handler.wfile.write(b"%X\r\n%s\r\n" % (len(data), data))

    def _flush_prelude():
        nonlocal prelude_flushed
        if prelude_flushed:
            return
        for e in prelude:
            _raw_write(e)
        prelude.clear()
        prelude_flushed = True

    def _emit(data: bytes):
        # Retry-safety: while the prelude is unflushed we hold back the events that
        # are identical & content-free across attempts — created / in_progress — AND
        # a bare response.failed (dmxapi's transient turn-start failure). Holding
        # failed keeps `wrote_downstream` False so the caller can reconnect. Any
        # SUBSTANTIVE event (delta/output/completed/incomplete/etc.) proves the
        # stream healthy → flush the prelude in order, then write this event.
        if not prelude_flushed:
            held = (any(t in data for t in _PRELUDE_TYPES)
                    or b'"type":"response.failed"' in data
                    or b'"type": "response.failed"' in data)
            if held:
                prelude.append(data)
                return
        _flush_prelude()
        _raw_write(data)

    try:
        resp.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
    except Exception:
        try:
            resp.fp.raw._fp.fp.raw._sock.settimeout(UPSTREAM_READ_TIMEOUT)
        except Exception:
            pass

    while True:
        try:
            chunk = resp.read(8192)
        except http.client.IncompleteRead as ir:
            chunk = ir.partial
            upstream_incomplete = True
        except socket.timeout as exc:
            upstream_timeout = True
            upstream_error = exc
            break
        except TimeoutError as exc:
            upstream_timeout = True
            upstream_error = exc
            break
        except Exception as exc:
            upstream_error = exc
            break
        if not chunk:
            break
        buf += chunk
        while True:
            idx_lf = buf.find(b"\n\n")
            idx_crlf = buf.find(b"\r\n\r\n")
            candidates = [x for x in (idx_lf, idx_crlf) if x != -1]
            if not candidates:
                break
            idx = min(candidates)
            sep_len = 4 if idx == idx_crlf else 2
            event = buf[:idx + sep_len]
            buf = buf[idx + sep_len:]
            new_event, removed = sanitize_sse_event(event)
            if removed:
                stripped_events += 1
                stripped_keys += removed
            if b"event:" in new_event or b"data:" in new_event:
                event_count += 1
                if b'"type":"response.completed"' in new_event or b'"type": "response.completed"' in new_event:
                    terminal_event = "response.completed"
                elif b'"type":"response.failed"' in new_event or b'"type": "response.failed"' in new_event:
                    terminal_event = "response.failed"
                elif b'"type":"response.incomplete"' in new_event or b'"type": "response.incomplete"' in new_event:
                    terminal_event = "response.incomplete"
            _emit(new_event)
    if buf:
        new_event, removed = sanitize_sse_event(buf)
        if removed:
            stripped_events += 1
            stripped_keys += removed
        if b"event:" in new_event or b"data:" in new_event:
            event_count += 1
            if b'"type":"response.completed"' in new_event or b'"type": "response.completed"' in new_event:
                terminal_event = "response.completed"
            elif b'"type":"response.failed"' in new_event or b'"type": "response.failed"' in new_event:
                terminal_event = "response.failed"
            elif b'"type":"response.incomplete"' in new_event or b'"type": "response.incomplete"' in new_event:
                terminal_event = "response.incomplete"
        _emit(new_event)

    # A legitimate terminal (completed/incomplete) means the prelude belongs to the
    # client — flush it so a created→completed stream isn't dropped. A bare
    # response.failed is left UNFLUSHED on purpose: with zero bytes committed the
    # caller can still retry it as a transient turn-start failure; only if retries
    # are exhausted does the caller flush+relay it.
    if terminal_event in ("response.completed", "response.incomplete") and not prelude_flushed:
        _flush_prelude()

    if stripped_keys:
        _log(f"  req#{request_id} inbound SSE stripped encrypted_content events={stripped_events} keys={stripped_keys} for {path}")

    detail = (terminal_event.split(".")[-1] if terminal_event
              else ("timeout" if upstream_timeout
                    else ("incomplete_read" if upstream_incomplete else "eof")))
    return {
        "terminal": terminal_event,
        "events": event_count,
        "wrote_downstream": wrote_downstream,
        "detail": detail,
        "error": upstream_error,
    }


def stream_sanitized_sse(handler, resp, path, request_id, reopen=None, send_headers=None):
    """Stream upstream SSE to the client, with reconnect-on-premature-EOF.

    Codex treats an SSE EOF before a terminal Responses event as:

        stream disconnected before completion: stream closed before response.completed

    Root cause is dmxapi tearing the stream at turn start (observed: ~82% of these
    end at events<=4 with zero substantive content). Since nothing has been written
    downstream yet in that window, we can transparently re-issue the identical
    upstream request and start the client stream fresh — Codex only ever sees one
    clean 200 stream. Once any downstream byte is written we can no longer retry
    (headers/events already sent), so we relay whatever we get and stop.

    `send_headers()` sends the HTTP 200 + chunked headers exactly once (lazy, so a
    dead-on-arrival stream stays retryable). `reopen()` returns a fresh upstream
    `resp` for the identical request, or None if it failed.
    """
    headers_sent = {"done": False}

    def _on_first_write():
        if send_headers is not None and not headers_sent["done"]:
            send_headers()
            headers_sent["done"] = True

    # Retry budget applies only to the pre-first-byte window (safe: nothing sent
    # to the client yet). dmxapi tears streams intermittently at turn start and the
    # outage can last ~15-30s (observed req#63 02:31:45→02:32:00 span). Give the
    # reconnect enough attempts + escalating backoff to ride across a short upstream
    # outage instead of giving up after ~4s. This does NOT fix the upstream flakiness
    # (that's dmxapi service quality), only maximizes local recovery.
    max_stream_attempts = 6 if reopen is not None else 1
    stream_backoffs = [1.0, 2.0, 4.0, 6.0, 8.0]

    current = resp
    result = None
    for attempt in range(max_stream_attempts):
        result = _read_one_sse_stream(handler, current, path, request_id, _on_first_write)
        # Stop if the client has already received bytes (can't un-send), or the
        # stream ended in a way that's legitimate to relay: response.completed /
        # response.incomplete. A bare response.failed with ZERO downstream bytes
        # written is dmxapi's transient turn-start failure (99% of observed
        # failures are events<=3, zero content) — since the prelude is still
        # buffered and unseen by the client, it's as safe to retry as a raw EOF.
        committed = result["wrote_downstream"]
        term = result["terminal"]
        clean_end = term in ("response.completed", "response.incomplete")
        retryable = (not committed) and (term is None or term == "response.failed")
        if committed or clean_end or not retryable:
            break
        # Premature/failed end with zero client bytes written → safe to retry fresh.
        if attempt < max_stream_attempts - 1 and reopen is not None:
            why = term if term else result["detail"]
            _log(f"  req#{request_id} SSE died pre-content ({why}) events={result['events']} — reconnect {attempt+1}/{max_stream_attempts-1} for {path}")
            time.sleep(stream_backoffs[min(attempt, len(stream_backoffs) - 1)])
            try:
                current = reopen()
            except Exception as exc:
                _log(f"  req#{request_id} SSE reconnect failed: {exc}")
                current = None
            if current is None:
                break
            continue
        break

    # If nothing was ever written (all attempts died pre-content), we still must
    # send headers + close the chunked body so the client gets a clean empty 200
    # rather than a hang. Codex will surface its own "no completion" but at least
    # the proxy didn't leak a half-open socket.
    if not headers_sent["done"] and send_headers is not None:
        send_headers()
        headers_sent["done"] = True
    handler.wfile.write(b"0\r\n\r\n")

    if result and result["terminal"]:
        _log(f"  req#{request_id} SSE terminal={result['terminal']} events={result['events']} for {path}")
    else:
        detail = result["detail"] if result else "eof"
        err = result["error"] if result else None
        suffix = f": {err}" if err else ""
        _log(f"  req#{request_id} SSE ended without terminal event ({detail}{suffix}) events={result['events'] if result else 0} for {path}")

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"dmx-responses-proxy/{release_version()}"

    def log_message(self, *a):  # silence default stderr spam; we log ourselves
        pass

    def _relay(self, method: str):
        request_id = _next_request_id()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        note = ""
        if body and method == "POST" and "/responses" in self.path:
            body, note = sanitize_responses_body(body)
            # Diagnostic (opt-in via DMX_DUMP_BODIES=1): record post-sanitize body
            # size and, optionally, the full body — so we can capture a SUCCESSFUL
            # large request as a counter-example when hunting the invalid_payload
            # trigger. Outcome (200 vs 400) is logged later, so pairing size+result
            # is enough to falsify the "size limit" hypothesis. Zero effect when off.
            if os.environ.get("DMX_DUMP_BODIES") == "1":
                try:
                    dump = os.path.join(os.path.dirname(LOG_PATH), f"body-{request_id}-{int(time.time())}.json")
                    with open(dump, "wb") as fh:
                        fh.write(body)
                    _log(f"req#{request_id} body dumped ({len(body)}b) -> {os.path.basename(dump)}")
                except Exception:
                    pass
            else:
                # Log size only for large bodies (the invalid_payload regime is
                # all 600KB+); avoids a noisy line on every small request.
                if len(body) >= 400_000:
                    _log(f"req#{request_id} outgoing body {len(body)}b (large) for {self.path}")

        url = UPSTREAM + self.path
        out_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in _HOP_BY_HOP
        }
        out_headers["Accept-Encoding"] = "identity"

        if note:
            _log(f"req#{request_id} {method} {self.path} -> {note}")
        if os.environ.get("DMX_DUMP_HEADERS") == "1" and "/responses" in self.path:
            hdrs = {k: v for k, v in self.headers.items()
                    if k.lower() not in ("authorization", "content-length", "host")}
            _log(f"req#{request_id} HEADERS {json.dumps(hdrs, ensure_ascii=False)}")

        # dmxapi intermittently returns 400 invalid_payload / 5xx / 429 for
        # provably-valid requests (~6% observed; identical replay succeeds).
        # Transparently retry the identical request a few times before giving up,
        # so this server-side flakiness never reaches Codex. An explicit 400
        # ``response_failed`` receives one *additional*, pair-safe compact
        # fallback: some large replay contexts are deterministically rejected.
        # Non-retryable 4xx are relayed immediately.
        is_responses = method == "POST" and "/responses" in self.path
        max_attempts = 4 if is_responses else 1
        backoffs = [0.4, 1.0, 2.0]

        acquired = False
        global _ACTIVE_RESPONSES
        if is_responses:
            acquired = _RESPONSES_SEM.acquire(timeout=RESPONSES_QUEUE_TIMEOUT)
            if not acquired:
                msg = json.dumps({
                    "error": {
                        "message": (
                            "dmx local proxy overloaded: timed out waiting for "
                            f"responses concurrency slot ({RESPONSES_MAX_CONCURRENCY})"
                        )
                    }
                }).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                _log(f"  req#{request_id} local queue timeout for {self.path}")
                return
            with _ACTIVE_LOCK:
                _ACTIVE_RESPONSES += 1
                active_now = _ACTIVE_RESPONSES
            _log(f"  req#{request_id} responses slot acquired active={active_now}/{RESPONSES_MAX_CONCURRENCY}")

        try:
            resp = None
            last_err = None
            compact_response_failed_metrics = None
            used_response_failed_compaction = False
            response_failed_stages = 0
            max_response_failed_stages = RESPONSE_FAILED_MAX_STAGES if is_responses else 0
            attempt_body = body
            used_response_failed_dialogue_recovery = False
            dialogue_recovery_metrics = None
            # Ordinary transient retries retain their previous bounded policy.
            # Explicit ``response_failed`` has its own staged, pair-safe
            # compaction path and must never loop the same bytes.
            for attempt in range(max_attempts + max_response_failed_stages):
                req = urllib.request.Request(url, data=attempt_body if attempt_body else None, method=method)
                for k, v in out_headers.items():
                    req.add_header(k, v)
                try:
                    resp = _urlopen(req, timeout=UPSTREAM_TIMEOUT)
                    if used_response_failed_dialogue_recovery and dialogue_recovery_metrics:
                        m = dialogue_recovery_metrics
                        _log(
                            f"  req#{request_id} response_failed dialogue recovery accepted "
                            f"bytes={m['original_bytes']}->{m['recovery_bytes']} "
                            f"messages={m['retained_messages']} retained/"
                            f"{m['dropped_input_items']} input items dropped "
                            f"after={response_failed_stages} pair-safe stages"
                        )
                    elif used_response_failed_compaction and compact_response_failed_metrics:
                        m = compact_response_failed_metrics
                        _log(
                            f"  req#{request_id} response_failed compact fallback accepted "
                            f"bytes={m['original_bytes']}->{m['compact_bytes']} "
                            f"inputs={m['removed_inputs']} removed/{m['retained_inputs']} retained"
                        )
                    break
                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read()
                        status_code = e.code
                        error_headers = e.headers
                    finally:
                        e.close()
                    disp = _is_transient_upstream(status_code, err_body)
                    # A deterministic replay failure cannot be fixed by retrying
                    # the same bytes. After the upstream has *explicitly* named
                    # ``response_failed``, make up to three strictly smaller,
                    # pair-safe suffix attempts. Each retains the latest user
                    # context and complete call/output pairs. This precedes
                    # ordinary retries so users do not wait through known-identical
                    # rejections.
                    if (
                        is_responses
                        and status_code == 400
                        and disp == "full"
                        and response_failed_stages < max_response_failed_stages
                    ):
                        compact, metrics = _compact_response_failed_request(attempt_body)
                        if compact is not None and metrics is not None and len(compact) < len(attempt_body):
                            response_failed_stages += 1
                            metrics["stage"] = response_failed_stages
                            compact_response_failed_metrics = metrics
                            used_response_failed_compaction = True
                            previous_bytes = len(attempt_body)
                            attempt_body = compact
                            _log(
                                f"  req#{request_id} upstream response_failed — compact fallback "
                                f"stage={response_failed_stages}/{max_response_failed_stages} "
                                f"bytes={previous_bytes}->{metrics['compact_bytes']} budget={metrics['budget_bytes']} "
                                f"inputs={metrics['removed_inputs']} removed/{metrics['retained_inputs']} retained "
                                f"cache_key_removed={metrics['prompt_cache_key_removed']} "
                                f"budget_met={metrics.get('budget_met', True)} for {self.path}"
                            )
                            continue
                    # If pair-safe suffixes have exhausted their useful range, make
                    # one final dialogue-only recovery attempt.  This is deliberately
                    # after pair-safe compaction: tool call/output replay is retained
                    # whenever it is accepted, and only an explicitly rejected replay
                    # can reach this bounded last resort.
                    if (
                        is_responses
                        and status_code == 400
                        and disp == "full"
                        and not used_response_failed_dialogue_recovery
                    ):
                        # Recover from the original request rather than the latest
                        # pair-safe suffix: a suffix may already have discarded the
                        # newest developer instruction to preserve a later tool pair.
                        # The dialogue-only recovery can safely retain that current
                        # instruction because it omits the rejected tool replay.
                        recovery, metrics = _recover_response_failed_dialogue(body)
                        if recovery is not None and metrics is not None and len(recovery) < len(attempt_body):
                            used_response_failed_dialogue_recovery = True
                            dialogue_recovery_metrics = metrics
                            previous_bytes = len(attempt_body)
                            attempt_body = recovery
                            _log(
                                f"  req#{request_id} upstream response_failed — dialogue recovery "
                                f"bytes={previous_bytes}->{metrics['recovery_bytes']} "
                                f"messages={metrics['retained_messages']} retained/"
                                f"{metrics['dropped_input_items']} input items dropped "
                                f"cache_key_removed={metrics['prompt_cache_key_removed']} for {self.path}"
                            )
                            continue
                    # invalid_payload is dmxapi SERVER-SIDE transient flakiness, NOT a
                    # bad body: replaying all 11 captured reject-400 bodies verbatim
                    # later returned 200 (11/11). Empirically ~18% of /responses fail
                    # this way; a single retry recovers most (observed gaveup 28 vs 58
                    # predicted if independent). So retry ONCE, but wait long enough to
                    # clear the transient window (0.4s was too eager and re-hit the same
                    # blip). Genuine 429/5xx keep the full escalating-backoff budget.
                    # ``response_failed`` has already consumed this response in
                    # the staged compaction branch above. Never let it fall
                    # through to the ordinary transient retry policy.
                    if is_responses and status_code == 400 and disp == "full":
                        attempts = response_failed_stages + int(used_response_failed_dialogue_recovery) + 1
                        msg = _response_failed_recovery_exhausted(attempts)
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Retry-After", "3")
                        self.send_header("Content-Length", str(len(msg)))
                        self.end_headers()
                        self.wfile.write(msg)
                        detail = "with dialogue recovery" if used_response_failed_dialogue_recovery else "without dialogue recovery"
                        _log(
                            f"  req#{request_id} response_failed recovery exhausted after {attempts} attempts "
                            f"({response_failed_stages} pair-safe stages, {detail}); normalized upstream HTTP "
                            f"{status_code} to 503 for {self.path}"
                        )
                        return
                    retry_ceiling = 1 if disp == "once" else max_attempts - 1
                    transient_retries_used = attempt - response_failed_stages
                    if (
                        disp
                        and transient_retries_used < retry_ceiling
                        and not (status_code == 400 and disp == "full")
                    ):
                        delay = 3.0 if disp == "once" else backoffs[min(attempt, len(backoffs) - 1)]
                        _log(f"  req#{request_id} upstream HTTP {status_code} ({disp}) — retry {attempt+1}/{retry_ceiling} in {delay}s for {self.path}")
                        time.sleep(delay)
                        continue
                    if status_code == 477 and disp == "full":
                        msg = _dmx_empty_response_exhausted(attempt + 1)
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Retry-After", "3")
                        self.send_header("Content-Length", str(len(msg)))
                        self.end_headers()
                        self.wfile.write(msg)
                        _log(
                            f"  req#{request_id} DMX empty_response exhausted after "
                            f"{attempt + 1} attempts; normalized upstream HTTP 477 to 503 "
                            f"for {self.path}"
                        )
                        return
                    if 400 <= status_code < 500:
                        try:
                            dump = os.path.join(os.path.dirname(LOG_PATH), f"reject-{status_code}-{int(time.time())}.json")
                            with open(dump, "wb") as fh:
                                fh.write(b"=== SENT BODY ===\n")
                                fh.write(attempt_body or b"(empty)")
                                fh.write(b"\n=== UPSTREAM ERROR ===\n")
                                fh.write(err_body)
                            _log(f"  req#{request_id} dumped rejected request to {dump}")
                        except Exception:
                            pass
                    self.send_response(status_code)
                    for k, v in error_headers.items():
                        if k.lower() not in _HOP_BY_HOP:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    _log(f"  req#{request_id} upstream HTTP {status_code} ({len(err_body)}b) for {self.path} [gave up after {attempt+1}]")
                    return
                except Exception as e:
                    last_err = e
                    if attempt < max_attempts - 1:
                        _log(f"  req#{request_id} upstream transport error (retry {attempt+1}): {e}")
                        time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                        continue
                    msg = json.dumps({"error": {"message": f"proxy upstream error: {e}"}}).encode()
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    _log(f"  req#{request_id} proxy 502 for {self.path}: {e}")
                    return

            if resp is None:
                msg = json.dumps({"error": {"message": f"proxy upstream error: {last_err}"}}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return

            # Stream the response back. Use chunked so we don't need a length up-front.
            ctype = resp.headers.get("Content-Type", "")
            is_sse = is_responses and "text/event-stream" in ctype.lower()

            def _send_stream_headers(r):
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in _HOP_BY_HOP or k.lower() == "content-length":
                        continue
                    self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

            if is_sse:
                # SSE: send headers lazily (on first downstream byte) so a stream
                # that dies before producing content can be transparently retried.
                def _reopen():
                    # Preserve the exact request that produced this upstream SSE.
                    # A recovered ``response_failed`` may be using a compact
                    # suffix; reopening the original oversized history would
                    # regress the repair during a pre-content reconnect.
                    req2 = urllib.request.Request(url, data=attempt_body if attempt_body else None, method=method)
                    for k, v in out_headers.items():
                        req2.add_header(k, v)
                    return _urlopen(req2, timeout=UPSTREAM_TIMEOUT)

                try:
                    stream_sanitized_sse(
                        self, resp, self.path, request_id,
                        reopen=_reopen,
                        send_headers=lambda: _send_stream_headers(resp),
                    )
                except (BrokenPipeError, ConnectionResetError):
                    _log(f"  req#{request_id} downstream client closed stream for {self.path}")
                except Exception as e:
                    _log(f"  req#{request_id} stream note for {self.path}: {e}")
            else:
                _send_stream_headers(resp)
                try:
                    import http.client
                    while True:
                        try:
                            chunk = resp.read(8192)
                        except http.client.IncompleteRead as ir:
                            chunk = ir.partial  # flush whatever arrived, then finish cleanly
                            if chunk:
                                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                            break
                        if not chunk:
                            break
                        self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.write(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    # Client (Codex) closed the stream early — normal at turn end.
                    _log(f"  req#{request_id} downstream client closed stream for {self.path}")
                except Exception as e:
                    _log(f"  req#{request_id} stream note for {self.path}: {e}")
        finally:
            if acquired:
                with _ACTIVE_LOCK:
                    _ACTIVE_RESPONSES -= 1
                    active_now = _ACTIVE_RESPONSES
                _RESPONSES_SEM.release()
                _log(f"  req#{request_id} responses slot released active={active_now}/{RESPONSES_MAX_CONCURRENCY}")

    def do_POST(self):
        self._relay("POST")

    def do_GET(self):
        self._relay("GET")

    def do_DELETE(self):
        self._relay("DELETE")

    def do_PATCH(self):
        self._relay("PATCH")

    def do_PUT(self):
        self._relay("PUT")


def main():
    _log(
        f"starting dmx-responses-proxy on http://{HOST}:{PORT} -> {UPSTREAM} "
        f"(responses_max_concurrency={RESPONSES_MAX_CONCURRENCY}, "
        f"upstream_timeout={UPSTREAM_TIMEOUT}, read_timeout={UPSTREAM_READ_TIMEOUT})"
    )
    httpd = _ResilientProxyServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
