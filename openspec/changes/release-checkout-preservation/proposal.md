## Why

Release publication currently verifies an annotated tag by detaching the
caller's checkout at the tag target. Verification is a read operation; changing
the active branch makes the publication adapter an accidental repository
lifecycle owner and can make an otherwise valid accepted checkout unusable for
subsequent governed operations.

## What Changes

- Verify the local annotated tag and its exact commit without changing the
  caller's symbolic ref, `HEAD`, index, or worktree.
- Fail closed when the tag is absent, lightweight, or does not resolve to the
  expected commit.
- Delete the misleading `prepare-checkout` command; release publication owns
  its read-only local-object check, while CI reuses the existing release
  metadata verifier instead of adding a parallel command.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: Require release-source verification to preserve the
  caller checkout while binding publication to the exact annotated tag and
  commit.

## Impact

The change is confined to the provider-neutral release command, its GitHub
transport helper, release tests, and this official Change. It adds no runtime
state, compatibility path, dependency, or provider-specific lifecycle rule.
