# Align release metadata and the locked CI bootstrap

## Why

The 2.0.15 candidate crossed a UTC date boundary before publication, and the
workstation now provides the next stable uv patch. CI also invoked repository
Python tools outside the locked environment. Finally, tag creation time was
being treated as Changelog authority, coupling publication timing to history
metadata that belongs to the repository.

## What Changes

- Set the pending 2.0.15 Changelog heading to the current UTC date.
- Admit uv 0.12.3 as the repository bootstrap and update its contract test.
- Run every GitLab Python tool through the locked `uv run` environment.
- Validate provider-native tag presence without comparing tag creation dates
  to Changelog dates.
- Encode namespaced GitLab project coordinates before runner-admission API calls.

## Non-goals

- No runtime, provider, protocol, dependency graph, or release version changes.
- No Forge publication or installation occurs in this Change.
