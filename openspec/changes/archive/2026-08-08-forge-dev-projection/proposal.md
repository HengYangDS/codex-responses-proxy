# Publish both protected Forge branches

## Why

The provider-native projector advances only `main`. Publishing `dev` through a
separate raw Git command bypasses the projector's identity, signature, runner,
forward-only, and atomicity guarantees.

## What Changes

- Each Forge projection atomically advances `main` and `dev` to the same signed
  provider-native commit.
- Projection tests prove both remote refs resolve to that exact commit.
- The operations guide names every branch role according to its actual
  publication boundary.

## Non-goals

- No Forge consumes or authenticates to the other.
- No candidate or work branch is published.
- No product runtime or provider behavior changes.
