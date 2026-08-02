## Why

The immutable `v2.0.1` tag exposed a provider-selection defect in the GitHub
tag test driver: it validated GitHub's native tag subset as canonical GitLab
history, emitted a traceback, and prevented both Forge releases from closing.

## What Changes

- Make every GitHub Actions metadata invocation select the GitHub chronology,
  including the already-tagged release path exercised by the regression suite.
- Retain canonical GitLab chronology and exact-tag validation unchanged.
- Publish the repair as `v2.0.2`; retain `v2.0.1` and its failed hosted jobs as
  immutable evidence rather than deleting or rewriting them.
- Require external provider-specific tag trust before either release can pass.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=provider-native release metadata diagnostics;
  reuse=extend; change=modify; release metadata tests select the current Forge
  chronology without emitting an implementation traceback for an expected
  policy failure; facet:lifecycle=validation,release,publication;
  facet:surface=test,quality,ci,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Runtime request behavior, credentials, client configuration, and provider
  availability.
- Rewriting or deleting `v2.0.1`, its tags, or its failed hosted executions.
- Modifying Codex JSONL, SQLite, history, response IDs, or model metadata.

## Impact

The release metadata regression driver, release identity, Changelog, CI
diagnostic contract, OpenSpec carriers, claim, and evidence change together.
GitLab chronology remains the canonical strict history; GitHub remains an
independent native publication plane.
