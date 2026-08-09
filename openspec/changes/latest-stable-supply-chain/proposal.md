# Latest stable supply chain

## Why

The committed lock trails the stable resolver output for two transitive quality
tools. Keeping stale transitive pins adds maintenance and security cost without
preserving a supported product contract.

## What changes

- Regenerate `uv.lock` with the repository-declared uv version.
- Accept only resolver-selected transitive updates.
- Keep `uv.lock` as the sole transitive dependency authority.

## Non-goals

- No product runtime, provider, protocol, public interface, or release-version
  change.
- No new updater, compatibility layer, or duplicate version owner.
