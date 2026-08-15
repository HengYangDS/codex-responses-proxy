# Why

Explicit Forge continuity currently scans unrelated history before its exact
base. Repeated identity-neutral fingerprints in that retired prefix therefore
block an otherwise exact, forward-only recovery.

# What Changes

- Treat the supplied canonical base and provider anchor as the sequence cut.
- Map only successors after that cut.
- Keep ambiguity after the cut fail-closed.
- Preserve ordinary projection and exact provider-tip CAS unchanged.

# Non-goals

- Rewriting published refs or tags.
- Weakening ordinary projection.
- Trusting a tree-only match without the three explicit coordinates.
