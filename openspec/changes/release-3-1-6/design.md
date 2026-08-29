## Context

`VERSION` is the sole package and release-version authority. `CHANGELOG.md`
records released changes, while Forge publication, installation, and runtime
health remain external effects that require fresh evidence.

## Decision

Create patch release `3.1.6` for the accepted stable-toolchain refresh and
strict branch-role policy. Archive this Change before constructing the signed
release commit, then project one commit, annotated tag object, and asset set
independently to GitLab and GitHub.

## Alternatives Rejected

- Reusing `v3.1.5` would violate immutable release identity.
- A minor or major increment would overstate compatibility impact.
- Encoding mutable Forge or installed-runtime state in tracked source would
  confuse declared identity with external effects.

## Risks

- Release metadata could imply publication already occurred. Publication,
  installation, and runtime checks therefore remain explicit post-archive
  acceptance steps.
