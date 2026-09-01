## Why

The request projection currently recognizes `local_shell_call` but can silently
discard an incomplete pair and accepts fields outside Codex's closed schema.
Malformed replay must fail locally before any provider receives it.

## What Changes

- Validate the complete `local_shell_call` item and nested `exec` action.
- Reject every local shell call without one matching output.
- Keep removing only complete, valid local shell pairs from the portable replay.
- Cover the rejection boundary with focused protocol tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: Close the local shell replay grammar and pair
  completeness contract.

## Impact

- Request-local protocol projection and its focused tests change.
- Malformed local shell history that was previously discarded becomes a local
  client error; no client store, provider configuration, or upstream API is
  modified.
