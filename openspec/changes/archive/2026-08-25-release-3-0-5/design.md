## Context

`VERSION` is the sole package and release-version authority. `CHANGELOG.md`
records published product behavior, while external publication and installation
remain separately evidenced effects.

## Decision

Create patch release `3.0.5` for the accepted recovery-journal and native
lifecycle corrections. A release version is never reused for different source
or artifact bytes.

Archive this Change before constructing the signed release commit. Create one
annotated tag locally and project the unchanged commit, tag, and asset set to
GitLab and GitHub.

## Alternatives Rejected

- Reusing `v3.0.4` would mutate an immutable published identity.
- A minor or major increment would overstate the compatibility impact.
- Encoding mutable Forge or installed-runtime state in tracked source would
  confuse declared release identity with external effects.
