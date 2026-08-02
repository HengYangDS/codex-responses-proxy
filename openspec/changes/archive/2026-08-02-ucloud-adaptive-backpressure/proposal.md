## Why

The released provider-scoped HTTP 429 cooldown stores one deadline per provider,
but a later concurrent response can overwrite that deadline with a shorter one.
For example, an active 300-second `Retry-After` can be reduced to five seconds
by a near-simultaneous 429 without a header. That reopens upstream traffic
before the strongest observed provider instruction expires and can recreate the
request storm that ended the original Codex thread with `exceeded retry limit`.

## What Changes

- Preserve the later of the existing and newly computed cooldown deadlines for
  the same key.
- Keep expiry purge, capacity eviction, provider isolation, fallback timing,
  and the released one-attempt HTTP 429 relay unchanged.
- Retain the original failed-thread boundary for post-installation acceptance;
  do not edit Codex JSONL, SQLite, transcript history, or model metadata.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider backpressure; reuse=extend;
  change=modify; requires an active cooldown deadline to be monotonic for one
  key under repeated or concurrent provider failures;
  facet:lifecycle=request,recovery,installation,acceptance;
  facet:surface=listener,test,openspec,claim,evidence;
  facet:authority=source,test,openspec,claim,evidence

## Out of Scope

- Reimplementing the already released HTTP 429 one-attempt relay, provider
  scoping, five-second fallback, five-minute cap, or default concurrency of 8.
- Increasing client or proxy retry budgets.
- Claiming an undocumented UCloud service quota.
- Editing consumer control-plane or Codex session state.

## Impact

The shared bounded cooldown owner, its focused unit contract, and exact source
proof are affected. No dependency, credential, route, or persistence surface is
added.
