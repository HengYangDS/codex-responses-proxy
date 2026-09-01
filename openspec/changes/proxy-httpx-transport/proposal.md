## Why

The upstream relay still reaches through private `urllib` response internals to
shorten a blocked SSE read as its total deadline approaches. An earlier decision
assumed HTTPX could replace that mechanism through public APIs; a focused probe
disproved the assumption before a production dependency was added.

## What Changes

- Amend the existing framework-admission decision with the failed HTTPX
  acceptance evidence.
- Retain the current upstream transport until a candidate proves public
  per-read deadline control, raw bytes, direct routing, frozen portability, and
  net deletion together.
- Remove the premature HTTPX migration promise without adding a fallback,
  wrapper, dependency, or second transport path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This corrects a dependency decision without changing product behavior, so
the Change uses the official `skip_specs` marker rather than inventing a second
behavior contract.

## Impact

Only the existing durable decision and this temporary Change record change.
Runtime code, dependency locks, native artifacts, and product behavior remain
unchanged.
