## Why

A real rollback returned `rolled_back` while both the predecessor and successor
still owned the product port. Runtime health had finalized before native
listener retirement, so the command exposed a false-success interval.

## What Changes

- Require upgrade and rollback handoff success to prove exactly one verified
  product listener: the finalized successor PID.
- Treat finalized health with an old or dual listener set as incomplete until
  bounded convergence succeeds or fails closed.
- Make native compatibility acceptance inspect listener identity immediately
  when rollback returns instead of waiting after the success claim.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: strengthen successful reverse handoff completion to require
  the sole verified successor listener at command return.

## Impact

The change affects only handoff completion proof and its lifecycle and native
compatibility tests. It adds no state, dependency, compatibility path, service
mutation, provider behavior, or client configuration.
