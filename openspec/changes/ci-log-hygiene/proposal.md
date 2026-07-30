## Why

The `v1.0.35` hosted jobs were green while their logs contained a
`BrokenPipeError` traceback, a Python 3.14 `ResourceWarning`, and a GitLab pip
root-user warning. Exit status alone therefore did not prove a clean test run.

## What Changes

- Close failed handoff HTTP responses and bound intentional disconnect handling
  to the loopback fixture.
- Make the canonical runner reject warning and traceback diagnostics and own
  isolated compilation.
- Project that owner consistently to GitLab, GitHub macOS, and GitHub Windows.
- Bind the repository to ETHOS with repository-native proof gates and this
  OpenSpec requirement family.

## Capabilities

### New Capabilities

- `ci-diagnostics`: subject=successful CI diagnostic integrity; reuse=new;
  change=add; facet:lifecycle=validation,release;
  facet:surface=test,quality,ci,docs,openspec;
  facet:authority=source,test,docs,openspec,claim,evidence.

### Modified Capabilities

- None.

## Out of Scope

- Codex transcript, session, model metadata, or AIGW configuration changes.
- Weakening the 95% coverage floor or changing release admission semantics.
- Treating local proof as hosted CI, publication, installation, or runtime proof.

## Impact

Production handoff cleanup, test fixtures, the canonical Python test and quality
runners, both Forge verification projections, release metadata, and governance
documentation change together for release `1.0.36`.
