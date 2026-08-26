## Context

The handoff protocol already owns the transition from one admitted listener to
one exact successor process. The controller knows the predecessor PID before
the transition, captures the successor PID from the authenticated READY
response, and reads finalized identity through the transferred listener.

TCP owner tables are useful discovery observations, but their attribution of a
shared socket is platform-dependent. Making that projection authoritative
introduced a Windows-only wait whose two sequential deadlines exceeded the
public command bound.

## Goals / Non-Goals

**Goals:**

- Use one portable completion predicate for reload, upgrade, rollback, and
  failure resolution.
- Bind both PIDs to exact executable roles and process generations.
- Report success only after the predecessor generation is gone and the exact
  successor generation serves finalized runtime identity.

**Non-Goals:**

- No timeout increase, Windows exception, relaxed runtime identity, or second
  lifecycle state machine.
- No change to socket transfer, payload transactions, supervision, routing, or
  provider configuration.

## Decisions

### Separate discovery from transition authority

Before mutation, the controller continues to require one verified product
listener on the configured port. It captures that process generation. After
the protocol crosses FINALIZE, completion uses the captured predecessor and
successor generations plus the exact runtime identity returned through the
listener.

This preserves the invariant that the displaced process has retired while
removing dependence on which PID an operating system assigns to a duplicated
socket.

### Reuse one generation predicate everywhere

Normal completion and controller-failure resolution call the same predicate.
Callers capture the predecessor before requesting handoff and pass that exact
identity through both paths. Failure resolution does not reconstruct or guess
past ownership.

## Risks / Trade-offs

- **PID reuse** → captured creation time is part of each `OwnedProcess`; later
  liveness checks therefore bind one process generation, not a numeric PID.
- **Finalized health without predecessor exit** → completion remains pending
  and fails closed at the existing bound.
- **Unobservable predecessor identity** → reject before requesting handoff.
