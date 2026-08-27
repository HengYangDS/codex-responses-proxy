## Why

Hosted compatibility exposed two test-model defects: Windows fixtures invented
a POSIX command path, while Linux waited for the successor before releasing
requests that the native-generation strategy must drain first. Both defects
made a valid portable lifecycle appear broken.

## What Changes

- Derive the isolated executable and command paths through the same platform
  owners used by production.
- Release held requests when either the exact predecessor has closed admission
  for native replacement or the exact successor is already accepting traffic.
- Retain the final upgrade, runtime-identity, request-success, rollback, and
  residue assertions as the acceptance proof.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The runtime-upgrade specification already requires portable, bounded,
lossless convergence; this change corrects the release-test model.

## Impact

Only release acceptance fixtures and tests change. Product behavior, public
interfaces, dependencies, and runtime state are unchanged.
