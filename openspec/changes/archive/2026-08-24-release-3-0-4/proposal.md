## Why

The accepted publication-proof and macOS host-residue corrections need one
SemVer patch identity before immutable assets can be built and published.

## What Changes

- Advance the release identity from `3.0.3` to `3.0.4`.
- Record the accepted user-visible corrections in the Changelog.
- Transfer asset construction, Forge publication, installation, and runtime
  acceptance to the post-archive lifecycle, where fresh external receipts are
  required.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This Change assigns release metadata to behavior already accepted by the
archived `publication-proof-host-residue` Change.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this OpenSpec lifecycle record change. No
runtime, protocol, provider, installation, or public CLI behavior changes.
