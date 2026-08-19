## Why

Validation and rollback must be able to install a candidate beside the live
service. Reusing the canonical native service identity lets a temporary install
unload or replace production supervision even when its HOME is different.

## What Changes

- Preserve the public service identity for the default installation root.
- Derive a deterministic identity from every alternate installation root.
- Use that identity consistently for native supervision, status, uninstall, and
  exact process ownership.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: alternate installation roots receive isolated native
  supervision identities while the default lifecycle remains unchanged.

## Impact

The change is limited to lifecycle context, native supervision adapters, focused
identity tests, and this OpenSpec record. The default listener, installed
payload shape, handoff protocol, and client control planes remain unchanged.
