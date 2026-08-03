## Why

Route-scoped admission admits one active Responses exchange per provider route.
A client reported `local proxy overloaded: timed out waiting for responses
concurrency slot (8)`. That text named the global process limit, which was not
the binding constraint: one in-flight turn saturates its own route while the
other seven global slots stay free. The message directed diagnosis at the wrong
capacity dimension and never named the saturated route.

Behind that text the route slot itself had no wall-clock ceiling. The stream
relay armed only a per-read idle timeout, so an upstream that returns bytes
before each idle window expires holds its route slot indefinitely, and
pre-content reconnects could stack further idle windows plus backoff on top.
The configured upstream timeout bounded connection establishment only. The
denial was also the one 503 emission on the Responses path that advertised no
retry hint, so a client could not tell a bounded local queue timeout from a
terminal refusal.

## What Changes

- Name the saturated provider route, its route limit, and the process limit in
  the queue-timeout denial.
- Bound one upstream stream by a total wall-clock deadline derived from the
  configured upstream timeout, spanning every pre-content reconnect attempt.
- Release an upstream connection the relay will not read from again instead of
  leaving it for garbage collection.
- Advertise a retry floor on the queue-timeout 503.
- Keep per-route single-flight at one and record why widening it is rejected.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider route slot lifetime;
  reuse=extend; change=modify; a held route slot is now bounded by a total
  stream deadline and its denial names the binding limit and is retryable;
  facet:lifecycle=request,admission,streaming,recovery;
  facet:surface=listener,test,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Widening per-route single-flight above one, or adding a per-provider width
  knob. See [design.md](design.md).
- Changing the released `responses_queue_timeout` default in code. It is
  already an operator knob, and a constant change would reach no installed
  operator; this change documents how to apply the knob instead.
- Changing provider quotas, client retry policy, credentials, URLs, or route
  configuration.
- The AIGW `check` and `catalog` model-listing contract, which is owned by a
  separate concurrent change that rebases onto this one.
- Editing Codex JSONL, SQLite, history, archives, or model metadata.

## Impact

Responses transport orchestration, the SSE relay, the named route-width
constant, focused tests, the diagnosis table, and release notes are affected.
No new dependency, daemon, configuration surface, or persistent state is added,
and `VERSION` is unchanged because the concurrent change owns the next bump.
