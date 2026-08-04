## Context

`BaseHTTPRequestHandler` decides whether to keep a connection open from the
protocol version and the `Connection` header it observes on the way out. With
`protocol_version = "HTTP/1.1"` and a `Content-Length` response, the default is
to keep it open and read another request. That default is correct only when the
previous request was fully consumed. Every path that reads the body before
answering — projection rejection, cooldown, drain refusal, and every upstream
outcome — already satisfies it. Three paths do not: the two rejections in
`relay` and the drain toggle in `control`.

## Goals / Non-Goals

- Goal: make a refused request cost exactly one response.
- Goal: leave the reusable-connection behavior of consumed requests untouched.
- Non-Goal: change which requests are refused, or with what status.
- Non-Goal: read, bound, or discard a body the listener has already refused.

## Decisions

### Decision: close the connection rather than drain the body

Two designs restore framing. The listener can read and discard the announced
body before answering, or it can declare the connection closed and let the
remainder die with the socket.

Draining is unbounded in the size it must read and undefined for the framing it
cannot decode. A caller controls `Content-Length`, so draining spends real
bandwidth on a request already refused, and a chunked request body cannot be
skipped by length at all — this listener does not decode chunked requests.
Closing is bounded, framing-independent, and costs one reconnection on a path
that already failed. It is also the behavior the HTTP specification provides for
exactly this case.

### Decision: an explicit per-response flag, not a listener-wide rule

Whether the body was consumed is known only to the handler that answered, and
`Connection: close` must be written before the headers end, so it cannot be
decided afterwards by inspecting leftover bytes. A `close` keyword on the two
response writers puts the decision at the site that knows the answer.
`send_status` on `/healthz` deliberately does not set it: a probe endpoint that
consumes nothing and is polled repeatedly should stay reusable.

Setting the header is sufficient; `send_header` records `close_connection` when
it sees `Connection: close`, so no second piece of state is maintained.

### Decision: dedupe the specification instead of correcting the stale copy

The contradiction could be removed by editing the duplicate sentence to mention
catalog targets. That leaves two statements of one rule, and the next admitted
path recreates the contradiction. Removing the duplicate leaves exactly one
requirement that can be wrong, and it is the one named for the job.

## Risks / Trade-offs

- A client that pipelines many requests and expects to survive a rejection now
  reconnects after one. It previously received a spurious `400` for its next
  request on that connection, so no working behavior is lost.
- The reusable-connection scenario is a guard over behavior that already held.
  It was verified by mutation: defaulting the new flag to closed makes it fail,
  so it is not vacuous.

## Migration Plan

No state, on-disk format, or configuration changes. Rollback is the inverse
revert of the source change; the specification dedupe is inert on its own.

## Open Questions

None.
