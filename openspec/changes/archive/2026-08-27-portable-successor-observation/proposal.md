## Why

Windows completed the published-predecessor upgrade and preserved live request
handoff, yet acceptance failed because host process enumeration did not expose
the listening socket as one exact PID within an additional polling window.

## What Changes

- Compare the upgrade result with the product's immediate read-only status,
  using the full runtime identity already verified by the lifecycle contract.
- Remove the redundant platform-dependent listener enumeration assertion.
- Keep product behavior, lifecycle state, and public interfaces unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The current `runtime-upgrade` specification already requires exact
successor identity and bounded lifecycle convergence; this change corrects its
cross-platform acceptance implementation.

## Impact

Only published-predecessor compatibility acceptance changes. No product source,
dependency, runtime state, compatibility path, or public API is added.
