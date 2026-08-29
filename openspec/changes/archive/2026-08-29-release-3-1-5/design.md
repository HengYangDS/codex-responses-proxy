## Context

`VERSION` is the sole package and release-version authority. `CHANGELOG.md`
records released changes, while publication, installation, and runtime health
remain external effects that require fresh evidence.

## Decision

Create patch release `3.1.5` for the accepted repository cleanup and
shell-independent predecessor download correction. Archive this Change before
constructing the signed release commit, then project one commit, tag object, and
asset set independently to GitLab and GitHub.

## Alternatives Rejected

- Reusing `v3.1.4` would violate immutable release identity.
- A minor or major increment would overstate compatibility impact.
- Recording mutable Forge or installed-runtime state in tracked source would
  confuse declared identity with external effects.

## Risks

- Release metadata could imply publication already occurred. Mitigation:
  publication, installation, and runtime checks remain explicit post-archive
  acceptance steps.
