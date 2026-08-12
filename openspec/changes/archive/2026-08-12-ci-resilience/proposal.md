## Why

GitLab verification installed the native release builder in every quality job.
A transient PyInstaller download timeout therefore failed an otherwise valid
Python quality run. The registered runner also accepted architecture-ambiguous
container jobs while claiming Linux x86_64 evidence.

## What Changes

- Keep release-only build tools out of the verification dependency set.
- Install the locked release group only in native release builds.
- Pin every GitLab Linux job to `linux/amd64` through one default plus explicit
  floor and native-image overrides.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: make hosted verification dependency-minimal and
  platform-true.

## Impact

Only repository quality and GitLab workflow contracts change. Product runtime,
provider protocol, Forge independence, installed state, credentials, and Codex
session storage remain unchanged.

## Out of Scope

- Retrying or rewriting the failed historical pipeline.
- Coupling GitLab publication to GitHub or vice versa.
- Changing the product runtime or release artifact format.
