## Why

The OpenSpec tree retains legacy summaries, scope inventories, and capability
descriptors that OpenSpec does not consume and whose meaning already belongs to
official change artifacts, canonical specifications, or Git history. These
parallel carriers obscure authority and increase maintenance without changing
product behavior.

## What Changes

- **BREAKING** Remove archived Change summaries and scope inventories after
  confirming that every Change retains its official proposal and Git history.
- **BREAKING** Remove capability descriptors whose normative content is owned
  by canonical specifications and repository documentation.
- Remove the empty specification index; OpenSpec itself remains the discovery
  surface for specifications.
- Define positive admission criteria for any non-schema carrier: it must own a
  current, non-overlapping invariant, have a named consumer, and state when it
  retires.
- Keep ETHOS Commitment carriers unchanged until their owning system removes or
  relocates its current runtime dependency.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `repository-organization`: Make the official OpenSpec schema the sole product
  intent model and admit additional carriers only for a current, unique,
  consumed invariant with a bounded lifetime.

## Impact

This change removes repository-only historical files under `openspec/` and
strengthens the existing repository-organization contract. It changes no
runtime API, release asset, dependency, or installed service state.
