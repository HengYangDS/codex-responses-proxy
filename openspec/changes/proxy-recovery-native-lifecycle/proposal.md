## Why

Recovery already preserves unverifiable transaction state, but several distinct
carrier failures still collapse into broad messages such as “unavailable or
invalid”. That makes safe operator action harder to determine and weakens the
machine contract. Native lifecycle verification must also continue to prove
that isolated services leave no host residue and never disturb the formal
service.

## What Changes

- Classify the transaction root and journal by the exact failed invariant:
  missing carrier, symbolic link, non-directory root, malformed JSON,
  non-canonical JSON, unsupported schema, or invalid current-schema fields.
- Keep every invalid carrier immutable and return the existing stable
  `recovery_state_invalid` error boundary with one read-only next action.
- Retain one native lifecycle and teardown contract across launchd, systemd
  user services, and Windows Task Scheduler.
- Reprove isolated lifecycle cleanup without modifying the formal service or
  listener on `127.0.0.1:8792`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: make invalid recovery evidence precise in Human and JSON
  projections.
- `runtime-upgrade`: strengthen fail-closed transaction-carrier validation and
  exact native-service teardown evidence.

## Impact

The change is limited to recovery-state parsing, public diagnostics, lifecycle
regressions, native teardown verification, and their documentation. It does
not change provider routing, client configuration, Codex private state, or the
formal installed runtime during source development.
