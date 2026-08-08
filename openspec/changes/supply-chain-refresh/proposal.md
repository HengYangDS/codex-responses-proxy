# Supply-chain refresh

## Why

The repository lock and hosted artifact workflow trail audited stable releases.
Leaving those pins stale increases maintenance and security cost without
preserving a supported product contract.

## What changes

- Refresh the locked packaging, lint, environment, and platform helpers.
- Advance GitHub artifact upload and download Actions to immutable current
  stable revisions.
- Keep `uv.lock` and repository workflow contracts as the only version owners.

## Non-goals

- No product runtime, provider, protocol, or release-version change.
- No mutable Action reference or compatibility layer.
