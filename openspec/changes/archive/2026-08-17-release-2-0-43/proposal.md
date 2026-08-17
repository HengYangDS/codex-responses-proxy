## Why

The 2.0.42 source still carries one superseded transitive dependency and two
names for the same GitLab remote. A forward patch release removes that
avoidable supply-chain and authority ambiguity without changing proxy behavior.

## What Changes

- Refresh the complete locked dependency graph; the resolver advances Pygments
  from 2.20.0 to the current stable 2.21.0 release.
- Make `origin` the sole GitLab remote authority in the publication contract.
- Advance the sole version carrier to 2.0.43 and record the release.
- Prove and archive the exact source before independent Forge publication.

## Impact

This patch changes the repository dependency lock, publication metadata,
release identity, and their contract test. It does not change provider routing,
Responses translation, client configuration, credentials, or conversation
state.
