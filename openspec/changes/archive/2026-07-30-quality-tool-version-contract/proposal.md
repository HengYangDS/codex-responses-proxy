## Why

The `v1.0.39` GitHub quality job installed `ty 0.0.64`, whose stable release
now reports informational build metadata after the semantic version. The
repository owner required the entire display string to equal `ty 0.0.64`, so a
valid pinned tool was rejected.

## What Changes

- Compare the required tool name and semantic version while allowing only a
  space-delimited informational suffix.
- Reject version prefixes, different versions, and malformed suffixes.
- Publish the repair as a new immutable patch release; retain `v1.0.39` as
  historical failed-release evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=quality tool admission; reuse=extend; change=modify;
  pinned stable tools may append informational build metadata without weakening
  the exact semantic-version requirement; facet:lifecycle=validation,release;
  facet:surface=quality,test,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Changing pinned tool versions or weakening lint, type, coverage, identity,
  signature, publication, or installation gates.
- Rewriting existing tags, Releases, CI history, Codex state, or AIGW state.

## Impact

The repository-owned quality runner, its behavioral tests, release metadata,
and CI diagnostic specification change together. Runtime behavior does not.
