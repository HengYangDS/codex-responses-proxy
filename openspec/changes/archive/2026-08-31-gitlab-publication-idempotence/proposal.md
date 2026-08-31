## Why

GitLab accepts repeated uploads of the same generic-package filename and version
as new package-file records. The publisher currently uploads before checking
the immutable Release, so an otherwise harmless retry creates duplicate remote
state instead of proving or completing the existing publication.

## What Changes

- Make the GitLab Release record the idempotency boundary for one exact tag.
- Verify and reuse already-published asset bytes; upload only missing assets.
- Preserve bounded GitLab HTTP response details when publication fails.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: GitLab publication becomes restartable and exactly
  idempotent for one immutable tag and signed asset bundle.

## Impact

The change is limited to the GitLab publication adapter, its focused tests, and
the release-governance contract. GitHub publication, runtime behavior, and
product protocol are unchanged.
