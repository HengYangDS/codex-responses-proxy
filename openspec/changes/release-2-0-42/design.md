## Context

The complete product change is already accepted and proved. This Change assigns
that exact tree a forward SemVer identity; it does not add a second behavior or
policy owner.

## Decision

Use one patch release with `VERSION` as the version SSOT and `CHANGELOG.md` as
the user-facing chronicle. Keep GitLab and GitHub independent: each receives a
provider-native signed tag, builds its own assets, and publishes its own Release
from an equal source tree.

## Safety

- Do not rewrite or retag 2.0.41 or older releases.
- Do not reintroduce deleted `evidence/claims` or `evidence/chronicle` content.
- Do not modify runtime, provider, client, credential, or session-state code.
- Reject publication unless release metadata and exact-HEAD proof pass.
