## Why

Version 2.0.34 predates the accepted GitLab publication repair. The repaired
source must advance under one new SemVer identity instead of rewriting the
failed release.

## What Changes

- Advance the sole release identity to 2.0.35.
- Record that GitLab publication uses the immutable repository runtime and
  performs no mutable operating-system package installation.
- Publish GitLab and GitHub independently from equivalent source trees.

## Capabilities

### Modified Capabilities

- `ci-diagnostics`: Bind the next patch release to the accepted immutable
  GitLab publication runtime.

## Impact

Only release identity, Changelog, and this Change contract are modified.
Provider routing, proxy behavior, client configuration, and release payload
construction remain unchanged.
