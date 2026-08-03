## Context

See [proposal.md](proposal.md). `2026-08-03-route-scoped-backpressure` closed
the already-admitted HTTP 429 burst window by giving each provider route a
single-flight slot. That change accepted one risk verbatim: "One long request
delays the same provider route → queue timeout remains bounded and explicit;
unrelated routes retain concurrency." The reported incident is that risk
arriving in production, plus two defects in how it was surfaced: the denial
named the wrong limit, and the hold it blamed was not in fact bounded.

## Goals / Non-Goals

**Goals:**

- Make the denial name the capacity dimension that actually bound the request.
- Give a held route slot a wall-clock ceiling that survives reconnects.
- Free an upstream socket at the moment the relay stops reading it.
- Make the denial retryable in the same shape as its sibling 503 emissions.

**Non-Goals:**

- Widening route concurrency, in general or per provider.
- Cancelling or preempting an in-flight turn to reclaim its slot.
- A new configuration surface; every bound reuses an existing setting.

## Decisions

### The denial names the route and both limits

`RESPONSES_MAX_PER_ROUTE` replaces the bare `1` literal in admission so the
transport can quote the route width it is actually enforcing. The message
carries the provider route name from the registry alongside both limits, so an
operator can tell a saturated route from a saturated process without reading
source. The constant reads through the admission owner, not through
`runtime_config`, because a module-level alias to a peer module's attribute is
a forwarding alias the architecture gate rejects.

### One stream is bounded by a total deadline, not only by idle reads

The relay computes `time.monotonic() + UPSTREAM_TIMEOUT` once per relay and
threads it through every attempt. Before each read it re-arms the socket
timeout to `min(UPSTREAM_READ_TIMEOUT, remaining)`, so a read blocked near the
deadline cannot outlive it by a whole idle interval, and reconnect is refused
once the deadline passes. Reusing the configured upstream timeout was chosen
over a new setting because the operator already declares how long one upstream
exchange may take; a per-read timeout was never a statement about total
duration. A slow but genuinely productive turn is still served — the observed
655-second completion sits inside the configured budget.

### Route width stays at one

Raising `RESPONSES_MAX_PER_ROUTE` to two or three would reopen the burst window
the predecessor closed. The cooldown map is populated only by `remember_failure`
*after* an upstream HTTP 429 is observed, so at width two both simultaneously
admitted same-route requests read `remaining() == 0` and both reach the
provider — which is precisely the failure the predecessor's `## Why` describes.
The post-queue cooldown recheck does not compensate: it protects a request that
*waited*, and at width two the second request does not wait. A per-provider
width knob is additionally rejected under the provider-manifest discipline,
which forbids a new environment variable or branch per provider.

The recurrence lever is therefore the existing operator knob
`CODEX_RESPONSES_PROXY_RESPONSES_QUEUE_TIMEOUT`, whose released default is 120
seconds. Measured against 16836 recorded slot holds, 40 exceeded 120 seconds
and 1 exceeded 300 seconds, so an operator who raises the queue timeout
converts nearly every observed denial into a completed wait without weakening
burst protection. A queued request holds no global slot, because the route
semaphore is acquired first, so waiting is cheap. The released default is left
unchanged here; retuning it is an operator decision, not a code change.

### The retry hint is a floor, not a prediction

The denial sends `Retry-After: 5` as a literal, matching the four existing
sibling emissions rather than introducing a constant for a single call site.
Release time is bounded only by the total upstream deadline, so the value is
deliberately a floor. It is larger than the `1` used for draining and the `3`
used for transient upstream exhaustion because a saturated route clears more
slowly than either.

## Risks / Trade-offs

- **A long legitimate turn is now cut at the total deadline** → the bound is
  the operator's own configured upstream timeout, and the abandonment is
  logged with a `deadline` detail distinct from `timeout`.
- **The retry floor can under-predict release** → documented as a floor in both
  the changelog and the diagnosis table rather than presented as an estimate.
- **Route saturation still denies work at width one** → accepted; the
  alternative reopens a closed rate-limit defect, and the queue timeout is a
  supported operator knob.

## Migration Plan

1. Prove RED for the route-named denial, the total-deadline stop, the refused
   post-deadline reconnect, the released connection, and the retry header.
2. Implement each fix as one minimal change with focused GREEN between them.
3. Run the full quality matrix, statement and branch coverage above 95%, and
   the Python 3.12-3.14 behavior gates.
4. Land after the concurrent AIGW model-catalog change, which overlaps
   `transport/responses.py`, `tests/transport/test_input.py`,
   `tests/listener/proxy_fixture.py`, `CHANGELOG.md`, and `README.md`.
   Rollback is reverting these commits; no state is migrated.
