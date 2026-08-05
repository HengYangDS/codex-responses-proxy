## Context

The platform matrix already proves all default roots, but its subtest control
flow covers a different branch per host. Linux therefore lost one `relay`
branch while macOS remained green.

## Decision

Add one host-independent assertion for the Darwin state-root branch. Keep the
existing matrix as the cross-platform contract and add no production branch,
coverage exclusion, compatibility shim, or CI-specific conditional.

## Rejected alternatives

- Lowering or rounding the floor: violates the strict greater-than-95 contract.
- Marking the branch excluded: hides executable behavior.
- Adding Linux-only CI logic: couples product proof to one runner.
