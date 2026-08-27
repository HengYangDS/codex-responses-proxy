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
- Never overwrite files mapped by a running predecessor process.
- Make one selector the sole active/predecessor authority.
- Bind both PIDs to exact executable roles and process generations.
- Report success only after the predecessor generation is gone and the exact
  successor generation serves finalized runtime identity.

**Non-Goals:**

- No timeout increase, Windows exception, relaxed runtime identity, or second
  lifecycle state machine.
- No change to socket transfer, routing, provider configuration, or client
  state.

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

Shared-listener handoff is admitted only when the predecessor explicitly
declares `selected-generation-handoff`. That capability means the predecessor
resolves the selector-bound candidate executable at request time. Older
protocol-v2 releases that advertise only `repeatable` know how to repeat a
handoff within their own payload root, but cannot launch an immutable candidate
generation; they therefore use the bounded native process-generation
replacement path.

### Reuse one generation predicate everywhere

Normal completion and controller-failure resolution call the same predicate.
Callers capture the predecessor before requesting handoff and pass that exact
identity through both paths. Failure resolution does not reconstruct or guess
past ownership.

### Select immutable payload generations

The installation root is a stable control root. It owns installed state, the
user-command projection, an atomic selector, and a `generations` directory.
Each admitted payload is materialized once under its transaction identity. The
selector names the active generation and at most one predecessor.

Upgrade therefore writes only a new generation while the predecessor may be
running. Activation switches the selector and command projection; finalization
then prunes every generation not named by the selector. Rollback reverses the
same selector rather than manufacturing a second payload copy. Because the
retained predecessor may predate the current handoff capability, explicit
rollback drains the current listener and performs one bounded native-generation
replacement; it never asks the older binary to participate in a newer hot
handoff protocol.

The selector itself has one canonical schema parser shared by the running
service and lifecycle controller. Non-canonical bytes, undeclared fields,
invalid generation names, and incomplete selected payloads fail closed before
either plane follows the selection.

If native replacement fails after the predecessor has drained but before a
successor is proved, rollback is complete only after the surviving predecessor
reopens Responses admission. A restored supervisor without reopened admission
is an unknown deployment outcome retained for recovery, not a successful
rollback.

### Bound legacy migration to one transaction

An installation created before immutable generations has no selector. Its
verified flat payload is snapshotted inside the active transaction before the
new generation is written. The legacy payload files are copied without content
changes except for the secret-free runtime carrier, which is deterministically
reprojected to the predecessor generation so the published executable can
validate and launch from its immutable root. After successor finalization, the
verified flat projection is retired and the selector becomes authoritative.
Recovery either completes that transition or restores the flat payload. The
snapshot disappears with the transaction and cannot become durable product
state.

## Risks / Trade-offs

- **PID reuse** → captured creation time is part of each `OwnedProcess`; later
  liveness checks therefore bind one process generation, not a numeric PID.
- **Finalized health without predecessor exit** → completion remains pending
  and fails closed at the existing bound.
- **Unobservable predecessor identity** → reject before requesting handoff.
- **Interrupted legacy migration** → retain exact transaction evidence until
  recovery either selects the verified generations or restores the verified
  flat payload.
