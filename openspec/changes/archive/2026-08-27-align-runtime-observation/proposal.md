## Why

Hosted Windows and macOS acceptance exposed two duplicate observations that
contradicted the lifecycle authority they were intended to verify. `doctor`
reinterpreted process inventory after `status` had already proved the runtime,
while the compatibility fixture spent its convergence budget on candidate
materialization before the upgrade transition could become observable.

## What Changes

- Make `doctor` consume the runtime identity already admitted by `status`.
- Release held compatibility traffic after the transaction reaches its durable
  activated boundary, then retain the exact successor, traffic, rollback, and
  residue assertions as terminal proof.
- Add focused regressions for platform inventory lag and lifecycle-boundary
  ordering.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The public product and runtime-upgrade requirements already require these
semantics; this change removes duplicate test and diagnostic interpretation.

## Impact

The CLI diagnostic composition and native release acceptance fixture change.
Public commands, runtime protocol, dependencies, configuration, and installed
state remain unchanged.
