## Why

GitLab `v2.0.12` pipeline `4623` passed 595 tests and every quality check except
the strict semantic-package gate: Linux measured `relay` branch coverage at
exactly 95.00 percent. The release remains failed evidence and cannot be
installed.

## What Changes

- Exercise the macOS state-root branch explicitly on every host so platform
  matrix coverage does not depend on the CI runner OS.
- Advance the forward-only release candidate to 2.0.13.
- Preserve the failed v2.0.12 tags, runs, and absent Release records.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=host-independent package coverage; reuse=extend;
  change=modify; facet:lifecycle=validation,release;
  facet:surface=test,changelog; facet:authority=source,test,openspec.

## Impact

One portable test, release metadata, and this atomic Change are affected.
Runtime behavior, provider protocol, installed state, credentials, and Codex
state are unchanged.

## Out of Scope

- Rewriting or deleting v2.0.12 tags or CI runs.
- Changing production runtime code.
- Weakening or rounding the strict coverage gate.
