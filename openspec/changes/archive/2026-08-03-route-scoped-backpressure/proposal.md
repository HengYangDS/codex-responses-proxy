## Why

The released global Responses admission limit permits several simultaneous
requests to the same constrained provider route. A provider-scoped cooldown can
stop later requests only after the first HTTP 429 is observed, so requests
already admitted in the same burst still reach the provider and reproduce the
rate-limit failure.

## What Changes

- Serialize active Responses exchanges within each provider route.
- Preserve concurrency between different provider routes, subject to the
  existing global process limit.
- Recheck provider cooldown after a queued request acquires its route slot so a
  preceding HTTP 429 stops that request before remote I/O.
- Preserve one upstream attempt for HTTP 429 and the existing response relay.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider route backpressure;
  reuse=extend; change=modify; provider rate-limit protection now closes the
  already-admitted burst window by combining route-scoped single-flight with a
  post-queue cooldown check;
  facet:lifecycle=request,admission,recovery,installation,acceptance;
  facet:surface=listener,test,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Changing provider quotas, client retry policy, credentials, URLs, or route
  configuration.
- Globally serializing unrelated providers in the released design.
- Persisting admission or cooldown state across process restarts.
- Editing Codex JSONL, SQLite, history, archives, or model metadata.
- Expanding AIGW or JetBrains responsibilities.

## Impact

The process-local admission owner, Responses transport orchestration, focused
tests, runtime contract, release notes, and 2.0.6 release train are affected.
No new dependency, daemon, configuration surface, or persistent state is added.
