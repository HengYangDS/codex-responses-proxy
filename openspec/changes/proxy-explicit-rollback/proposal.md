## Why

A completed successful upgrade currently deletes the only verified predecessor
snapshot, so an operator cannot intentionally return a healthy installation to
its immediately preceding release. Recovery cannot fill that role because it
correctly owns only interrupted or indeterminate transactions.

## What Changes

- Retain exactly one verified predecessor generation after a successful
  upgrade; a later successful upgrade atomically replaces it.
- Add a public `rollback` command that restores only that retained predecessor
  and rebinds the command, native service, and accepting listener as one
  transaction.
- Keep `recover` limited to unresolved installation transactions and make
  `rollback` return an explicit unavailable result when no predecessor exists.
- Fail closed without mutation when retained rollback evidence or the current
  installed generation cannot be verified.
- Preserve one lifecycle authority by reusing the existing snapshot,
  transaction, handoff, identity, and native-service owners.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: expose a distinct, discoverable operator rollback
  command with one Human/JSON result model.
- `runtime-upgrade`: retain one verified predecessor and restore it through the
  existing transactional native lifecycle.

## Impact

The change affects the installed lifecycle command surface, finalized
installation state, rollback retention, native handoff orchestration, tests,
and operator documentation. It does not change provider routing, client
configuration, Codex private state, or the formal service on port `8792`
during source development.
