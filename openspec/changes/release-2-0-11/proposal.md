## Why

The accepted source identifies version 2.0.11 and has passed exact-head proof,
but its user-visible changes remain under `Unreleased`. A signed tag or Forge
Release must not exist until that chronology is finalized on a clean, proven
release commit.

## What Changes

- Move the current 2.0.11 user-visible changes from `Unreleased` into a dated
  release heading using the current UTC date.
- Revalidate the canonical release-preparation contract on the exact commit.
- Preserve dual-Forge publication, installation, runtime acceptance, and lane
  retirement as separately evidenced post-archive transitions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=2.0.11 release chronology; reuse=extend;
  change=modify; facet:lifecycle=release,validation;
  facet:surface=changelog,metadata,openspec;
  facet:authority=source,test,openspec,claim,evidence.

## Impact

Only release chronology and its lifecycle carriers change. Runtime behavior,
provider protocol, client configuration, credentials, and installed state do
not change.

## Out of Scope

- Creating or pushing either Forge tag or branch.
- Publishing a Forge Release record or assets.
- Installing, reloading, rolling back, or uninstalling the runtime.
- Modifying Codex JSONL, SQLite, conversation history, or model metadata.
