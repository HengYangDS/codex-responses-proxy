## Why

The installed payload can be native while its supervisor still launches an
older wrapper, and an interrupted pre-mutation install can retain a `prepared`
transaction. The public CLI and release tests also expose inconsistent machine
output and can accidentally observe the canonical listener.

## What Changes

- Close a valid, unmutated `prepared` transaction without touching the payload.
- Reconcile one strictly proved install-owned alternate launcher onto the
  canonical native executable before upgrading the payload.
- Make supervisor reconciliation retry-safe across controller interruption.
- Bind status runtime evidence to the exact listener owned by the selected
  installation.
- Give every public command the same human and JSON output contract.
- Exercise every released command against isolated roots and an isolated port.
- Retire predecessor-owned payload files that are absent from the successor,
  while preserving unknown files and exact rollback.
- Require the shared listener to expose the exact successor identity before
  handoff finalization.
- Prove the forward-only lifecycle against one authentic signed predecessor
  release with concurrent ordinary and streaming requests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: every public command has one tested human and JSON
  contract, and release black-box validation cannot observe the canonical
  installation.
- `runtime-upgrade`: prepared-transaction recovery and one-way native
  supervisor reconciliation precede payload mutation.

## Impact

The change affects only the Proxy CLI, installed lifecycle orchestration,
platform supervisor readers, handoff convergence, release verification, and
their contracts. It
does not change provider routing, request transformation, client configuration,
the handoff wire protocol, or the canonical listener during validation.
