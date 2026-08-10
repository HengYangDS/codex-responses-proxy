## Why

The active evidence contract still names a retired directory as a negative
example and duplicates its admitted roots inside the quality implementation.
The repository needs one positive taxonomy that states what durable evidence
means without preserving obsolete terminology.

## What Changes

- Define the two durable evidence families and their meanings in one canonical
  specification.
- Make the repository quality gate consume that taxonomy rather than maintain
  a second allowlist.
- Replace the historical example in active tests with a neutral unknown family.
- Keep historical OpenSpec archives unchanged as immutable development facts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `evidence-layout`: Define a positive, machine-readable durable evidence
  taxonomy and its single-owner validation behavior.

## Impact

Only evidence documentation, its specification, and the repository quality
gate change. Runtime behavior, release behavior, and historical archives do not.
