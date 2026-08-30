## Why

The accepted post-3.1.6 governance and lifecycle-test corrections need one new
immutable release identity. Reusing `3.1.6` would bind different source bytes to
an existing release.

## What Changes

- Advance the release identity from `3.1.6` to `3.1.7`.
- Record the removal of obsolete Commitment carriers, the launchd guidance
  correction, and the handoff-test isolation fix in the Changelog.
- Preserve proof, publication, installation, and runtime acceptance as distinct
  externally verified effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The accepted commits already own the relevant repository and test
behavior. This Change assigns release identity only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this bounded release Change are modified.
No protocol, provider, installation, or public CLI behavior is added.
