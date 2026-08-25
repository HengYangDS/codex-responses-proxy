## Why

The accepted recovery and native lifecycle corrections need a new immutable
SemVer identity before release assets can be built and published. Reusing
`3.0.4` would make source and artifact provenance ambiguous.

## What Changes

- Advance the release identity from `3.0.4` to `3.0.5`.
- Record the accepted recovery and native lifecycle corrections once in the
  Changelog.
- Keep asset construction, Forge publication, installation, and runtime
  acceptance as separately evidenced post-archive effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. Product behavior is owned by the archived
`proxy-recovery-native-lifecycle` Change. This Change assigns release identity
only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this bounded release Change are modified.
No runtime, protocol, provider, installation, or public CLI behavior is added by
the release commit.
