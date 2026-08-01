## Why

The GitHub identity projector compares every canonical commit with every
projected commit by repeatedly launching Git. Real repository history therefore
turns one forward-only append into quadratic work and makes a healthy publication
look stalled.

## What Changes

- Compute each canonical and projected commit fingerprint once.
- Join the two fingerprint indexes without weakening unique-base, identity,
  signature, tree, or forward-only admission.
- Add a regression contract that bounds Git command growth during an incremental
  projection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=Forge projection execution cost; reuse=extend;
  change=modify; preserve the existing publication semantics while making
  history matching linear in the number of commits;
  facet:lifecycle=validation,publication;
  facet:surface=forge-script,test,openspec;
  facet:authority=accepted-history,github-history,projection-map.

## Out of Scope

- Changing provider identity, trust anchors, signatures, tags, or Releases.
- Rewriting or force-updating either Forge.
- Changing runtime, installation, provider behavior, or Codex state.

## Impact

Only the GitHub history-matching implementation, its offline contract, and this
OpenSpec carrier change. Remote publication remains a separate observed effect.
