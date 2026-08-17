## Why

The accepted source contains a proved Forge-audit repair that is not present in
2.0.40. A forward patch release gives that exact source an immutable product
identity without rewriting prior tags, Releases, or provider-native history.

## What Changes

- Advance the sole version carrier from 2.0.40 to 2.0.41.
- Record the accepted audit-continuity behavior in the Changelog.
- Prove and archive the exact release source before independent publication.

## Impact

The release changes repository-owned audit tooling, its tests, and operational
documentation. It does not change proxy protocol behavior, provider routing,
client configuration, credentials, or conversation state.
