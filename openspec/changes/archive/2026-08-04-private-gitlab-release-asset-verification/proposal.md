## Why

The dual-Forge verifier cannot prove a private GitLab release because it fetches
package-backed Release assets anonymously even though all other GitLab API
evidence already uses the authenticated provider CLI. The first complete
`v2.0.2` publication exposed this boundary and must be repaired forward rather
than weakening verification or rewriting the immutable release.

## What Changes

- Fetch GitLab Release assets through the authenticated GitLab API transport.
- Keep the Release-record URL as the exact asset identity and retain byte-level
  cross-Forge digest comparison.
- Publish the repair as a new patch release; preserve `v2.0.2` and its valid
  publication records unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: publication proof authenticates private GitLab asset reads
  without changing tag, pipeline, Release, or asset-parity requirements.

## Out of Scope

- Making private assets anonymous or changing GitLab project visibility.
- Adding credentials to URLs, product source, or release records.
- Replacing provider CLIs, changing installation admission, or modifying Codex
  JSONL, SQLite, history, response identifiers, or model metadata.

## Impact

The GitLab publication adapter, its focused contract test, release identity,
release notes, and `ci-diagnostics` contract change together. Runtime request
behavior, provider routing, installed payload, and consumer configuration do
not change.
