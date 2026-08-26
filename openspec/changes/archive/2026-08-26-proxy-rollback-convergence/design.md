## Context

See [proposal.md](proposal.md). Handoff already has one controller loop and one
successor identity predicate. The defect is that the predicate trusts process
liveness plus finalized runtime health without binding the same observation to
the verified listener set.

## Goals / Non-Goals

**Goals:**

- Make the existing completion predicate own process, listener, and runtime
  identity together.
- Reuse one listener observation per poll in normal and failure-resolution
  paths.
- Fail closed when health finalizes before listener retirement.

**Non-Goals:**

- No new state machine, timeout, cleanup command, compatibility reader, or
  supervisor behavior.
- No change to payload transactions, routing, provider configuration, or the
  formal service during source verification.

## Decisions

### Extend the existing finalization predicate

Pass the listener set already observed by each controller iteration into the
single successor-finalization predicate. Completion requires exactly the child
PID, captured-process liveness, and matching finalized runtime identity.

This is preferable to a rollback-only wait because forward upgrade and reverse
rollback share the same handoff authority. It is also preferable to rereading
listener state inside the predicate because one explicit observation avoids a
second race and keeps tests deterministic.

### Make release acceptance synchronous with the command contract

The native compatibility test asserts listener uniqueness immediately after
`rollback` returns. A post-return polling helper would preserve the defect by
allowing the test to repair the product's completion semantics externally.

## Risks / Trade-offs

- **Slow predecessor retirement can extend command duration** → reuse the
  existing bounded convergence deadline and fail closed when it expires.
- **OS listener observation can lag runtime health** → require both facts from
  the same polling iteration; neither is sufficient alone.
