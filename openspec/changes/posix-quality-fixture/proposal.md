## Why

The `v1.0.38` GitHub Windows matrix ran a fixture that models POSIX `sh`
executable-bit lookup. Windows correctly rejected the fake Ruff executable even
though the product matrix itself passed.

## What Changes

- Run the version-selection fixture only on POSIX, where its shell contract exists.
- Keep all Windows product tests enabled.
- Publish a new immutable patch release.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=successful CI diagnostic integrity; reuse=extend;
  change=modify; platform-specific fixtures execute only where their modeled
  contract exists; facet:lifecycle=validation,release;
  facet:surface=test,quality,ci,openspec;
  facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Skipping Windows product behavior or rewriting prior tags.
- Runtime, Codex history, or AIGW changes.

## Impact

Quality contract tests, release metadata, and OpenSpec history only.
