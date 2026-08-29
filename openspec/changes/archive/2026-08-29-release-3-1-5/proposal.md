## Why

The accepted OpenSpec entity cleanup and release-predecessor portability fix
need a new immutable SemVer identity before release assets can be built and
published. Reusing `3.1.4` would map different source and artifact bytes to an
existing release identity.

## What Changes

- Advance the release identity from `3.1.4` to `3.1.5`.
- Record the accepted repository cleanup and shell-independent predecessor
  download correction in the Changelog.
- Keep asset construction, Forge publication, installation, and runtime
  acceptance as separately verified post-archive effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. Product behavior is already owned by the accepted source changes. This
Change assigns release identity only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this bounded release Change are modified.
No runtime, protocol, provider, installation, or public CLI behavior is added by
the release commit.
