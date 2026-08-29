## Why

The accepted stable-toolchain refresh and strict branch-role policy need one
new immutable SemVer identity. Reusing `3.1.5` would associate different source
and artifact bytes with an existing release.

## What Changes

- Advance the release identity from `3.1.5` to `3.1.6`.
- Record the stable dependency refresh and unified branch-role policy in the
  Changelog.
- Keep proof, publication, installation, and runtime acceptance as separately
  verified effects.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The product and governance behavior is already owned by the accepted
source changes. This Change assigns release identity only.

## Impact

Only `VERSION`, `CHANGELOG.md`, and this bounded release Change are modified.
No runtime, protocol, provider, installation, or public CLI behavior is added.
