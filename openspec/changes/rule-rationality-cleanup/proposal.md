# Rationalize Repository Quality Rules

## Why

The quality command treated positive architecture contracts, forbidden-name
lists, and arbitrary source-size ceilings as equivalent merge blockers. Only
the positive topology and dependency rules prove stable ownership. Numeric
source-shape limits created false precision and duplicated the same concern in
policy, checker code, tests, and two canonical specifications.

## What Changes

- Keep one positive package topology and dependency-direction authority.
- Remove forbidden-package lists, logical-statement ceilings, ELOC ceilings,
  function-size ceilings, nesting ceilings, and historical ratchets.
- Retain source-size and nesting measurements only as descriptive review data.
- Remove the obsolete structural-limit requirement from `ci-diagnostics`; the
  `quality-boundaries` capability owns repository structure semantics.
- Require an explicit risk model before a descriptive metric may block merging.

## Boundaries

This change does not alter proxy traffic, provider behavior, retry policy,
resource limits, installation, release identity, runtime state, or client
configuration. It introduces no compatibility parser for retired policy fields.
