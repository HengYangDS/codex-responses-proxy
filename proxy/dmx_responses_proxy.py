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
The model still reasons every turn; it just isn't handed a stale encrypted blob it
(or rather the proxy) can't verify. This mirrors the fix the Codex maintainers
recommend (strip encrypted_content before sending) — done at the network edge.

Design guarantees
-----------------
* Transparent: forwards method, path, query, headers (incl. ``Authorization``) and
  body to the real upstream. Codex's keychain Bearer token passes through untouched.
* Surgical: only mutates JSON bodies of POSTs whose path contains ``/responses``.
  For those it drops (a) any ``input[]`` item of type ``reasoning``, (b) any residual
  ``encrypted_content`` keys anywhere in the payload, and (c) ``reasoning.encrypted_content``
  from the ``include[]`` list so the API stops returning new blobs.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("DMX_UPSTREAM", "https://www.dmxapi.cn").rstrip("/")
HOST = os.environ.get("DMX_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DMX_PROXY_PORT", "8791"))
LOG_PATH = os.environ.get("DMX_PROXY_LOG", os.path.expanduser("~/.codex/log/dmx-responses-proxy.log"))
RESPONSES_MAX_CONCURRENCY = int(os.environ.get("DMX_RESPONSES_MAX_CONCURRENCY", "64"))
RESPONSES_QUEUE_TIMEOUT = float(os.environ.get("DMX_RESPONSES_QUEUE_TIMEOUT", "120"))
UPSTREAM_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_TIMEOUT", "900"))
UPSTREAM_READ_TIMEOUT = float(os.environ.get("DMX_UPSTREAM_READ_TIMEOUT", "240"))
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


def _is_transient_upstream(code: int, err_body: bytes) -> bool:
    """Classify an upstream failure's retry disposition.

    Returns one of:
      "full"    — genuine transient (429/5xx); retry up to the full budget.
      "once"    — 400 invalid_payload / "does not match the expected schema".
                  This is dmxapi SERVER-SIDE flakiness, NOT a malformed body:
                  all 11 locally-captured reject-400 bodies, replayed verbatim
                  hours later, returned 200 (11/11) — including with the exact
                  custom_tool_call / web_search_call / encrypted_content items
                  intact. Empirically ~18% of /responses hit this. A single,
                  patient retry recovers most of them (observed gaveup 28 vs the
                  58 a purely-independent model predicts). We retry ONCE (never
                  the storm-amplifying 3x) and rely on the caller's longer backoff
                  to clear the transient window.
      ""        — not retryable (encrypted-content complaint or other genuine 4xx).
    """
    if code in (429, 500, 502, 503, 504):
        return "full"
    if code == 400:
        try:
            low = err_body.lower()
        except Exception:
            return ""
        if b"invalid_encrypted_content" in low or b"could not be verified" in low:
            return ""
        if b"invalid_payload" in low or b"does not match the expected schema" in low:
            return "once"
    return ""


def _strip_encrypted(obj):
    """Recursively delete every ``encrypted_content`` key. Returns count removed."""
    removed = 0
    if isinstance(obj, dict):
        if "encrypted_content" in obj:
            del obj["encrypted_content"]
            removed += 1
        for v in obj.values():
            removed += _strip_encrypted(v)
    elif isinstance(obj, list):
        for v in obj:
            removed += _strip_encrypted(v)
    return removed


def _is_replayable_remote_image_url(value):
    """True only for URL schemes the third-party Responses endpoint accepts."""
    return isinstance(value, str) and value.startswith(("https://", "http://"))


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

    dropped_items = 0
    dropped_images = 0
    stripped_keys = 0

    # (a) Drop replayed reasoning items from the model-visible input history.
    inp = payload.get("input")
    if isinstance(inp, list):
        kept = []
        for item in inp:
            if isinstance(item, dict) and item.get("type") == "reasoning":
                dropped_items += 1
                continue
            kept.append(item)
        if dropped_items:
            payload["input"] = kept

    # (b) Drop local-path / data-URL image replay items that this third-party
    # endpoint rejects. Valid remote http(s) images stay intact.
    dropped_images = _strip_unreplayable_images(payload)

    # (c) Belt-and-suspenders: remove any encrypted_content still nested anywhere.
    stripped_keys = _strip_encrypted(payload)

    # (d) Stop asking the API to return new encrypted reasoning.
    include = payload.get("include")
    include_trimmed = False
    if isinstance(include, list):
        new_inc = [x for x in include if x != "reasoning.encrypted_content"]
        if len(new_inc) != len(include):
            payload["include"] = new_inc
            include_trimmed = True

    if not (dropped_items or dropped_images or stripped_keys or include_trimmed):
        return raw, "clean (nothing to strip)"

    try:
        new_raw = json.dumps(payload).encode("utf-8")
    except Exception as exc:
        return raw, f"passthrough (reserialize failed: {exc.__class__.__name__})"

    return new_raw, (
        f"stripped reasoning_items={dropped_items} local_image_items={dropped_images} "
        f"encrypted_keys={stripped_keys} include_trimmed={include_trimmed}"
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
                removed = _strip_encrypted(obj)
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
    server_version = "dmx-responses-proxy/1.0"

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
        # so this server-side flakiness never reaches Codex. Safe because we
        # re-send the exact same bytes; non-retryable 4xx are relayed immediately.
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
            for attempt in range(max_attempts):
                req = urllib.request.Request(url, data=body if body else None, method=method)
                for k, v in out_headers.items():
                    req.add_header(k, v)
                try:
                    resp = _urlopen(req, timeout=UPSTREAM_TIMEOUT)
                    break
                except urllib.error.HTTPError as e:
                    err_body = e.read()
                    disp = _is_transient_upstream(e.code, err_body)
                    # invalid_payload is dmxapi SERVER-SIDE transient flakiness, NOT a
                    # bad body: replaying all 11 captured reject-400 bodies verbatim
                    # later returned 200 (11/11). Empirically ~18% of /responses fail
                    # this way; a single retry recovers most (observed gaveup 28 vs 58
                    # predicted if independent). So retry ONCE, but wait long enough to
                    # clear the transient window (0.4s was too eager and re-hit the same
                    # blip). Genuine 429/5xx keep the full escalating-backoff budget.
                    retry_ceiling = 1 if disp == "once" else max_attempts - 1
                    if disp and attempt < retry_ceiling:
                        delay = 3.0 if disp == "once" else backoffs[min(attempt, len(backoffs) - 1)]
                        _log(f"  req#{request_id} upstream HTTP {e.code} ({disp}) — retry {attempt+1}/{retry_ceiling} in {delay}s for {self.path}")
                        time.sleep(delay)
                        continue
                    if 400 <= e.code < 500:
                        try:
                            dump = os.path.join(os.path.dirname(LOG_PATH), f"reject-{e.code}-{int(time.time())}.json")
                            with open(dump, "wb") as fh:
                                fh.write(b"=== SENT BODY ===\n")
                                fh.write(body or b"(empty)")
                                fh.write(b"\n=== UPSTREAM ERROR ===\n")
                                fh.write(err_body)
                            _log(f"  req#{request_id} dumped rejected request to {dump}")
                        except Exception:
                            pass
                    self.send_response(e.code)
                    for k, v in e.headers.items():
                        if k.lower() not in _HOP_BY_HOP:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    _log(f"  req#{request_id} upstream HTTP {e.code} ({len(err_body)}b) for {self.path} [gave up after {attempt+1}]")
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
                    req2 = urllib.request.Request(url, data=body if body else None, method=method)
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
