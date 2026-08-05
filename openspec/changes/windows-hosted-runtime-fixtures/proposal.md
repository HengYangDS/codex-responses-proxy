## Why

The first accepted-source GitHub run exposed test fixtures that inferred the
modeled runtime from the runner host.  On Windows this changed generic Linux
artifact and migration fixtures to `.exe` paths, while POSIX Forge harnesses
were incorrectly treated as Windows product behavior.

## What Changes

- Make generic lifecycle fixtures model an explicit non-Windows payload unless
  a test selects Windows semantics.
- Keep native Windows product tests enabled while excluding POSIX-only Forge
  integration harnesses from Windows jobs.
- Make the pre-push hook contract assertion independent of host newline
  projection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=hosted Windows semantic fixture isolation;
  reuse=extend; change=modify; facet:lifecycle=validation;
  facet:surface=test,ci; facet:authority=source,test,openspec,claim,evidence.

## Impact

Only test fixtures and hosted validation semantics change. Production runtime,
provider behavior, release bytes, credentials, and Codex state are unchanged.

## Out of Scope

- Bypassing ETHOS hooks or changing the separately reported ETHOS defect.
- Publishing v2.0.11 before both branch pipelines pass.
