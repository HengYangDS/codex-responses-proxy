## Why

The first hosted verification of the 2.0.11 accepted source exposed assumptions
that local macOS proof could not reveal: release chronology depended on
unpublished local-only tags, Windows fixtures modeled POSIX path and permission
semantics, Linux branch coverage fell below the strict floor, and one workflow
contract still invoked an obsolete asset interface. These are source defects,
not runner-capacity failures.

## What Changes

- Make release chronology describe published canonical releases rather than
  local-only candidate tags.
- Make lifecycle and governance fixtures express portable path, executable, and
  permission semantics on Windows, macOS, and Linux.
- Require every hosted quality target to keep statement and branch coverage
  strictly above 95%.
- Keep workflow contract tests aligned with the native release asset owner.
- Refuse branch projection before push when required hosted verification is not
  schedulable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=hosted source-complete portability proof;
  reuse=extend; change=modify; facet:lifecycle=validation,release;
  facet:surface=ci,test,changelog; facet:authority=source,test,openspec,claim,evidence.

## Impact

Release metadata, CI contracts, portable test fixtures, coverage tests, the
Changelog, and their OpenSpec/claim evidence are affected. Provider runtime
behavior, client configuration, credentials, Codex history, and installed
runtime state are unchanged.

## Out of Scope

- Creating or publishing v2.0.11 before both branch pipelines pass.
- Rewriting or deleting any existing remote tag or CI run.
- Modifying Codex JSONL, SQLite, history, session state, or model metadata.
