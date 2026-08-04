## Context

Two independent constants governed one queue. `DEFAULT_UPSTREAM_TIMEOUT = 900.0`
bounds how long a holder may keep a provider route slot. `DEFAULT_RESPONSES_
QUEUE_TIMEOUT = 120.0` bounded how long the next request may wait for it. Since
the route semaphore is acquired before the process-wide one, a waiter holds no
global slot, so the only cost of waiting longer is the waiter's own latency —
which it has already chosen to spend by waiting.

## Goals / Non-Goals

- Goal: make the denial boundary follow from the deadline it depends on.
- Goal: keep the operator override and its bounds exactly as they are.
- Non-Goal: retune the upstream deadline, the route width, or the global width.
- Non-Goal: introduce an install-time flag; the code default is sufficient
  precisely because it is what an install renders.

## Decisions

### Decision: derive rather than pick a second number

The invariant is that a waiter must not be denied while the holder ahead of it
is still inside its own total deadline. Denying earlier discards work that the
proxy has already committed to finishing. Expressing this as
`DEFAULT_RESPONSES_QUEUE_TIMEOUT = DEFAULT_UPSTREAM_TIMEOUT` makes the
relationship structural: retuning the upstream deadline later moves the queue
wait with it, and no reviewer has to rediscover why 900 was chosen.

The census supports the same value empirically — 900 admits 99.5 percent of the
observed denials — but the census is corroboration, not the derivation. A
magic number that happens to fit one log corpus would not survive the next one.

Rejected alternatives:

- 300 seconds, proposed by `route-slot-lease` from a smaller sample. The full
  census shows it admits 82.4 percent, leaving roughly one denial in six for a
  request whose holder was still legitimately running.
- A separate tunable ratio of the upstream deadline. It adds a configuration
  surface to express a relationship that has only one defensible setting.

### Decision: assert the invariant instead of the value

The unit contract asserts `DEFAULT_RESPONSES_QUEUE_TIMEOUT >=
DEFAULT_UPSTREAM_TIMEOUT`, not `== 900.0`. A future upstream retune stays legal;
reintroducing an unrelated smaller constant does not.

## Risks / Trade-offs

- A client that would rather fail fast than queue now waits longer before its
  503. This is bounded by the same deadline that already bounds a served turn,
  and the operator override remains available to shorten it.
- The listener does not observe the new default until the native unit is
  re-rendered, since the installed unit pins the install-time value. That is a
  property of the existing projection contract, not of this change, and the
  diagnosis table states it.

## Migration Plan

Reinstall re-renders the unit. No state, on-disk format, or client contract
changes, so no data migration exists and rollback is the inverse reinstall.

## Open Questions

None.
