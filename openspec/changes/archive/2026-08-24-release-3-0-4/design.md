## Context

`VERSION` is the sole package and release-version authority. `CHANGELOG.md`
records published product behavior, while external publication and installation
remain separately evidenced effects.

## Decision

Create the next patch version, `3.0.4`, because the accepted delta repairs
release verification and host lifecycle hygiene without changing the public
feature set. Keep the source Change limited to release metadata and archive it
before candidate and accepted integration.

Do not encode Forge status, release URLs, installed-runtime state, or mutable
host observations in tracked source. Those facts require fresh post-archive
receipts.

## Alternatives Rejected

- Reusing `v3.0.3` would mutate an immutable published identity.
- A minor or major increment would overstate the compatibility impact.
- Delaying the version change until after publication would make source and
  artifact identity circular.

## Risks

- Metadata could imply that publication already occurred. Mitigation: the
  archived task record explicitly separates source acceptance from external
  publication and runtime acceptance.
