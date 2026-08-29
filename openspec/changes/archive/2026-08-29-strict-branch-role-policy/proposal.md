## Why

The repository still declares a retired transition row and omits two fields
required by the current strict branch-role contract. Source proof can pass, but
candidate closeout then has no parseable accepted policy and cannot advance the
already-proven product commit.

## What Changes

- Declare the complete current branch-role policy in `.ethos/workspace.toml`.
- Make `main` an accepted fast-forward mirror so release and accepted roots
  converge to one Git object.
- Remove the retired transition declaration rather than preserving a
  compatibility shape.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This corrects repository governance metadata; product behavior is
unchanged.

## Impact

Only the tracked ETHOS workspace policy changes. Product source, dependencies,
release assets, and public CLI semantics remain unchanged.
