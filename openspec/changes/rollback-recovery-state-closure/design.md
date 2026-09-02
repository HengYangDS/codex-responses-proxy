## Context

See [proposal.md](proposal.md) for the incident boundary and
[specs/runtime-upgrade/spec.md](specs/runtime-upgrade/spec.md) for the observable
contract. Two separate defects amplified one operational mistake:

1. rollback expressed direction indirectly through mutable predecessor state, so
   sequential repetition could oscillate releases;
2. recovery demanded rollback-only state before determining that an unselected
   reverse candidate had changed no terminal authority.

The transaction root is durable recovery evidence, not a process lock. Its
atomic creation prevents two fresh transactions from claiming the same path,
but it does not serialize recovery cleanup against a second lifecycle command.
All public lifecycle writers therefore share one cross-platform OS lock outside
the payload root; read-only status and doctor do not acquire it.

## Goals / Non-Goals

**Goals:** bind rollback to one explicit release; make repetition converge; prove
an unchanged terminal generation from current selection, installed state,
command ownership, immutable payload, and accepting runtime; close only the
orphaned transaction; preserve fail-closed recovery for every ambiguous state.

**Non-goals:** adding a force or compatibility mode; changing supervision;
inventing rollback history; weakening identity checks; repairing the live host
before a release artifact has passed isolated lifecycle verification.

## Decisions

### Rollback names the desired terminal release

The public command requires `--to-release <version>`. Control loads the sole
verified predecessor and compares the requested target before invoking the
mutation path:

- if the installed active release already equals the target, return a no-op;
- if the retained predecessor equals the target, execute the existing
  transactional rollback;
- otherwise reject before drain, handoff, selection, command, or filesystem
  mutation.

This is positive target binding, not a blacklist of repeated invocations. It
turns rollback into convergence toward a declared state and makes retry safe.
The existing strict release-version parser remains the single validation
authority.

Alternative rejected: consume or delete rollback history after one invocation.
That prevents one symptom but does not express operator intent and weakens a
legitimate forward recovery path.

The writer lock is not another transaction authority. It carries no recovery
state and makes no lifecycle decision; it only prevents two product commands
from mutating one installation concurrently. The journal remains the sole
durable transaction authority.

### Read restoration state only when restoration is required

Recovery first compares the current selection with the pre-transaction and
candidate selections. If the candidate is selected, it retains the existing
snapshot-backed restoration path. If the prior selection remains active, it
must verify all of the following before snapshot-free closure:

- selection is exactly the pre-transaction selection;
- installed state remains bound to that active generation and release;
- command ownership resolves to that generation's executable;
- the executable has the committed immutable payload identity;
- the accepting runtime matches that payload identity and is not draining.

Only after this proof may recovery remove the unselected candidate and the
transaction carrier. It must not rewrite the selection, command, service, or
listener.

Alternative rejected: synthesize a missing snapshot. That invents history and
creates a second recovery authority.

Alternative rejected: ignore every missing snapshot. A selected candidate still
requires the exact snapshot to restore the displaced command safely.

## Risks / Trade-offs

- **A caller supplies a malformed target** → parse it through the existing
  strict release-version authority before lifecycle inspection or mutation.
- **A valid but unrelated release is requested** → reject it before the apply
  layer; only the active release and verified predecessor are admissible.
- **A foreign command masquerades as a healthy service** → require exact command
  ownership by the prior selected control generation.
- **A missing snapshot hides partial activation** → allow snapshot-free closure
  only for the exact pre-transaction selection with all terminal identities
  agreeing; every other state remains blocked.
- **Two lifecycle commands overlap** → reject the second command before it reads
  transaction state; the first command retains sole responsibility for success,
  rollback, or durable recovery evidence.
- **A process bypasses the product command boundary** → treat it as unsupported
  external mutation rather than duplicating POSIX and Windows handle-specific
  deletion protocols that still cannot police an equal-privilege actor.

## Verification Strategy

1. CLI RED: omission of `--to-release` is rejected; the exact target reaches the
   semantic owner.
2. Control RED: current target is a no-op, predecessor target invokes apply,
   mismatched target fails before apply.
3. Transaction RED: unselected reverse candidate with no unused snapshot closes
   only under full terminal proof; selection, installed, command, payload, or
   runtime drift each fails closed and preserves the transaction.
4. Command-boundary RED: a second lifecycle writer is rejected before its owner
   runs; success and exception paths both release the lock.
5. Focused GREEN, lifecycle modules, strict OpenSpec validation, quick quality,
   Python 3.12–3.14, and the release gate.
6. Build and publish a new signed hotfix. Use an isolated installation root for
   install/update/rollback/recovery/uninstall validation before any controlled
   repair of the formal installation.

## Operational Safety

The formal 3.1.13 service remains read-only until the hotfix artifact completes
isolated lifecycle proof. Formal repair must run from a control plane that does
not depend on the proxy being drained. No `launchctl submit`, `nohup`, ad-hoc
watchdog, or self-restarting script is an accepted verification mechanism.
