## Context

The repository has two durable evidence meanings: machine-readable claims and
human-readable chronicles. `evidence/parity/` contains no artifact and explicitly
states that generic parity is not configured. Cross-Forge parity already has one
runtime owner in `tools/forge/audit.py`.

## Decisions

1. Delete the placeholder instead of documenting an unused capability.
2. Keep the positive allowlist beside the existing repository structure gates.
3. Inspect tracked or physical top-level directories without prescribing file
   internals already owned by claims and chronicles.
4. Report an unknown root deterministically; do not silently delete it.

## Risks / Trade-offs

- A future evidence family requires one deliberate gate update. This is desired:
  new semantic roots must have an explicit project owner.
- The gate validates ownership boundaries, not the truth of individual evidence;
  existing claim and evidence verification retains that responsibility.

## Migration Plan

1. Add and observe a failing regression for the absent layout gate.
2. Implement the positive root contract and remove `evidence/parity/`.
3. Run the focused contract test, repository quality checks, and exact-HEAD proof.
