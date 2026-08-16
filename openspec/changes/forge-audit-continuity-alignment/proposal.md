# Align Forge audit with publication continuity

## Why

The read-only audit applies the current trust anchor to unrelated historical
prefixes and treats every branch other than `main` as residue. Both assumptions
contradict the repository's declared topology and explicit publication
continuity model.

## What changes

- Read persistent local and remote branch roles from `.ethos/workspace.toml`.
- Bind each provider audit to the projection receipt for its current `main` tip.
- Verify commit identity and signatures from the receipt's exact continuity
  anchor through the current tip.
- Fail closed when a receipt is missing, stale, malformed, or unreachable.

## Non-goals

- No published-history rewrite or trust exception.
- No release, installation, runtime, provider route, or client mutation.
- No second branch-role or continuity authority.
