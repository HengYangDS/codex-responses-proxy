## Why

The independently built v2.0.30 Linux releases passed both Forge pipelines but
had different bytes. Installer-local metadata entered the frozen executable,
so the existing reproducibility claim was not actually enforced.

## What Changes

- Normalize installed distribution metadata before native executable freezing.
- Add a regression that models distinct installer-local metadata and requires
  identical frozen inputs.
- Require post-publication digest equality for every platform built by both
  Forge planes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: Strengthen native release reproducibility from archive
  packaging alone to the complete frozen executable input and published asset.

## Impact

The release session and its tests change. Runtime behavior, provider routing,
Forge independence, installation semantics, and failed v2.0.30 records remain
unchanged.
