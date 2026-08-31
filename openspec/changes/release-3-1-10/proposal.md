## Why

The accepted checkout-preservation correction needs a new immutable release
identity. Reusing `3.1.9` would bind different source bytes to an existing
release.

## What Changes

- Advance the release identity from `3.1.9` to `3.1.10`.
- Record that release-tag verification no longer mutates the caller checkout.
- Keep source proof, Forge publication, installation, and runtime acceptance as
  separate verified effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The accepted source already owns the release-verification behavior; this
Change assigns release identity only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this release Change are modified. No
protocol, provider, installation, or public CLI behavior is added.
