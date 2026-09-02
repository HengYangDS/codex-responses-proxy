## Why

The accepted local-shell replay validation is present on `dev` but is not yet
available as an immutable installable release. Published `3.1.12` provenance
must remain unchanged, so the correction requires a new patch release.

## What Changes

- Publish the accepted closed-schema validation for Codex local-shell replay.
- Publish rejection of incomplete local-shell call/output pairs before upstream
  dispatch.
- Advance the release identity and changelog to `3.1.13` without changing the
  accepted protocol behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: require an accepted correction that is absent from the
  latest published release to advance through a new immutable SemVer release;
  a backward-compatible defect correction advances the patch version without
  rewriting earlier provenance.

The protocol behavior is already specified and accepted by the archived
`proxy-local-shell-call-validation` Change; this Change packages that accepted
source.

## Impact

`VERSION`, `CHANGELOG.md`, release metadata, native assets, the signed tag, both
Forge release projections, and the installed native service are affected.
Provider routes, credentials, client configuration, and conversation storage
remain unchanged.
