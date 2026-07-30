## Why

The `v1.0.37` GitLab tag pipeline exposed a false release failure: the quality
owner had been correctly generalized, but a release test still required its
obsolete shell spelling. The same hosted logs also retained Debian frontend
warnings during package bootstrap.

## What Changes

- Test the quality owner's version-selection behavior and stable version
  constants instead of a private shell implementation string.
- Make every GitLab Debian bootstrap explicitly noninteractive and quiet.
- Extend the CI diagnostic contract so dependency bootstrap warnings cannot be
  accepted as clean release evidence.
- Publish the repair as a new immutable patch release; retain `v1.0.37` as
  historical failed-release evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: release gates validate semantic owner behavior and hosted
  dependency bootstrap is warning-free.

## Impact

The release-metadata regression owner, GitLab projection, CI diagnostic spec,
release metadata, and local evidence carrier change together. Runtime behavior,
Codex history, AIGW configuration, credentials, and provider identities do not.
