## Why

The accepted detached-delivery replay correction needs one new immutable
release identity. Reusing `3.1.7` would bind different source bytes and runtime
behavior to an existing release.

## What Changes

- Advance the release identity from `3.1.7` to `3.1.8`.
- Record the provider-portable replay correction in the Changelog.
- Preserve source proof, Forge publication, installation, and same-task replay
  acceptance as distinct externally verified effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The accepted source already owns the provider-portable behavior; this
Change assigns release identity only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this bounded release Change are modified.
No protocol, provider, installation, or public CLI behavior is added here.
