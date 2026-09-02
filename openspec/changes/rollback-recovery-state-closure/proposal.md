## Why

A rollback command currently means “switch to whichever predecessor is retained.”
After one successful rollback, that predecessor can become the release that was
just left. Repeating the same command can therefore reverse direction again,
causing another drain and generation handoff instead of converging on the
operator's intended release.

The incident also left a materialized reverse transaction whose candidate was
never selected. The original generation remained selected, projected, and
serving, but recovery read a command snapshot before proving whether restoration
was needed. A missing, unused snapshot then stranded a healthy installation in
`recovery_required`.

## What Changes

- Require rollback to name its intended release explicitly.
- Treat an already-active requested release as a proven idempotent no-op.
- Permit a transition only when the requested release is the one verified
  retained predecessor; reject every other target before drain or mutation.
- For an unselected reverse candidate, prove the unchanged prior terminal state
  from selection, installed state, command ownership, immutable payload, and
  accepting runtime before closing the orphaned transaction without an unused
  snapshot.
- Serialize public lifecycle writers before transaction inspection or mutation;
  keep status and doctor read-only.
- Keep every ambiguous or partially activated transaction fail closed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: Make the public rollback grammar and result model expose
  the exact desired release and its idempotent terminal outcome.
- `runtime-upgrade`: Make rollback target-bound, repeat-safe, and recoverable
  when an unactivated reverse candidate did not alter terminal state.

## Impact

- `src/codex_responses_proxy/cli/application.py`
- `src/codex_responses_proxy/lifecycle/control.py`
- `src/codex_responses_proxy/lifecycle/transaction.py`
- focused CLI, control, transaction, and release lifecycle tests
- `openspec/specs/product-interface/spec.md`
- `openspec/specs/runtime-upgrade/spec.md`

No compatibility alias, parallel state machine, lock registry, release format,
or direct mutation of an installed runtime is introduced. One mature
cross-platform file-lock dependency provides the process boundary; the journal
remains the sole durable transaction authority.
