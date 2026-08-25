## Context

See [proposal.md](proposal.md). The existing transaction already snapshots the
verified predecessor before committing a candidate and can restore that
snapshot while an upgrade is in flight. `finalize` currently removes the whole
transaction root, which also removes the only rollback material. Recovery is
intentionally transaction-bound and must not be widened into an operator
downgrade command.

## Goals / Non-Goals

**Goals:**

- Retain one immutable, self-describing predecessor after successful upgrade.
- Restore payload, installed state, command projection, native service, and
  listener through one bounded lifecycle transaction.
- Make absence, corruption, incompatibility, success, and indeterminate
  outcomes distinct and actionable.
- Keep the retained surface lean and replace the previous predecessor after
  each successful upgrade.

**Non-Goals:**

- No arbitrary-version selection, release download, downgrade history, or
  compatibility reader for obsolete schemas.
- No second payload state machine and no alias from `rollback` to `recover`.
- No modification of provider configuration, client state, or Codex private
  session data.

## Decisions

### Finalization owns one idempotent generation-promotion transition

After successor proof, the transaction atomically promotes its already
verified `rollback/` directory into one sibling retained generation. One
transition owns verification, materialization, atomic selection, superseded
generation cleanup, retry, status projection, and purge ownership. It accepts
only these monotonic intermediate states:

1. the transaction snapshot exists and the target generation does not;
2. the exact target generation exists but is not yet selected;
3. the exact target generation is selected while an older generation awaits
   cleanup;
4. the selected generation is the sole retained generation.

Repeating finalization from any valid intermediate state advances toward the
same terminal state. It never deletes the previously selected generation
before the new selector is durable. While the transaction remains active,
status reports retained rollback as transaction-owned and deferred rather than
giving the incomplete retained store a second, contradictory lifecycle state.
This keeps the same bytes and validation semantics that protected in-flight
rollback and avoids a second snapshot or recovery implementation. Fresh
installation removes any stale carrier because it has no predecessor.

The first release containing this transition drives its own upgrade from the
published predecessor. The predecessor cannot execute a finalization operation
that was absent from its code. This is a bounded bootstrap at the installer
boundary: use the verified successor once, then return to installed-release
ownership for subsequent adjacent upgrades. No legacy carrier is inferred or
migrated.

The alternative—resnapshotting the predecessor after finalization—is invalid:
the live projection is already the successor. Retaining multiple generations
would add policy, storage, selection, and migration complexity without serving
the required one-step operator journey.

### Bind the retained generation to both predecessor and successor

The retained carrier records the exact successor installed-state identity for
which the predecessor is valid. Rollback first verifies the current payload,
installed state, command projection, retained snapshot, and successor binding.
It never applies a snapshot merely because a directory exists.

### Reuse deployment handoff for the reverse transition

Rollback restores the predecessor projection inside the existing transaction
authority, installs the native service for that executable, and uses the same
bounded handoff and runtime identity proof as forward upgrade. If a failure is
proved before handoff completion, the successor is restored and supervision is
rebound. If the outcome cannot be proved, the transaction remains available to
`recover`; no success or rollback claim is guessed.

Handoff eligibility is a positive runtime capability, not an inference from a
protocol number or a completed transaction. A finalized runtime may receive a
shared listener only when its health projection explicitly advertises
`repeatable`. A complete, verified predecessor without that capability uses one
bounded native-generation replacement: commit the candidate, rebind the native
supervisor, terminate the exact captured predecessor generation, then prove the
sole successor listener. Incomplete identity remains unsupported and cannot
enter either path. This is one deployment decision over the existing lifecycle
authority, not a compatibility state machine.

### Keep recovery and rollback semantically disjoint

`recover` resolves an active transaction after interruption. `rollback`
initiates a new transaction from a healthy finalized installation to its one
retained predecessor. This separation keeps each command precise and prevents
ordinary recovery from becoming an implicit downgrade policy.

## Risks / Trade-offs

- **Retained carrier consumes one additional installed payload** → Retain only
  one generation and atomically replace it after successful forward upgrade.
- **Reverse handoff can fail after bytes change** → Snapshot the current
  successor as compensation and reuse the existing recovery-required outcome.
- **A published predecessor can finalize one handoff but cannot repeat it** →
  require an explicit repeatable-handoff capability; otherwise replace its
  exact native process generation with bounded compensation.
- **Finalization can stop between filesystem operations** → Make each promotion
  phase idempotent, keep the active transaction as the recovery authority, and
  select the new generation before deleting the old one.
- **A copied or stale retained directory could target the wrong successor** →
  Bind it to exact installed-state and payload identities and fail closed on
  every mismatch.

## Migration Plan

Existing installations have no retained predecessor, so `rollback` reports
`unavailable` without mutation. The next verified successful upgrade creates
the carrier. No historical state is synthesized. The formal runtime is updated
only after isolated release acceptance proves install, upgrade, rollback,
recover, and uninstall.
