## Context

The inventory already records effective lines, function size, and nesting, but
the implementation skipped those checks for paths below `tests/` and permitted
an 800-statement test ceiling.

## Decision

Make the same positive limits apply to every tracked Python owner in the
configured source and test roots. Keep the limits in the architecture policy;
the checker reads them rather than owning another copy. Resolve current gaps by
moving tests into semantic modules, not by adding exceptions.

## Rejected Alternatives

- Keeping a looser test policy: it preserves the observed blind spot.
- Adding per-file ratchets: it fossilizes accidental complexity.
- Rewriting the checker in a second tool: it creates a competing quality owner.
