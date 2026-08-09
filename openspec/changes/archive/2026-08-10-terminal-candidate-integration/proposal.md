# Terminal candidate integration

## Why

The work lane contains one proven and archived supply-chain update that is not
yet represented by `candidate/dev`. Candidate integration requires an explicit
compare-and-swap authority bound to the complete accumulated delta.

## What changes

- Bind the exact archived lane tree to candidate integration authority.
- Permit only an exact fast-forward of `candidate/dev`.

## Non-goals

- No product, provider, protocol, dependency, documentation, or release change.
- No remote publication or accepted-root mutation.
