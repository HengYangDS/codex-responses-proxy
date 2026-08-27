## Context

See [proposal.md](proposal.md). Published compatibility runs the same lifecycle
scenario on macOS, Linux, and Windows. Its fixtures must therefore consume the
product's native path projection and model both supported upgrade strategies:
selected-generation handoff and native-generation replacement.

## Goals / Non-Goals

**Goals:**

- Give command-path projection one implementation owner.
- Model the earliest state at which held requests may safely finish.
- Preserve the final public-product and residue assertions.

**Non-Goals:**

- No platform exception, longer timeout, or alternate lifecycle path.
- No production code or release-contract change.
- No weakening of the accepted traffic or runtime-identity proof.

## Decisions

### Reuse production path projection

`runtime_context_for` delegates executable naming to `inventory` and command
placement to `lifecycle.command`. A test-local path table was rejected because
it duplicated production semantics and had already diverged on Windows.

### Wait for a lifecycle release point

The compatibility test may release held requests when either:

- the exact predecessor release reports `draining=true` and `accepting=false`;
  or
- the exact successor release reports an accepting, non-draining serving state.

This covers native replacement and selected-generation handoff without
predicting which strategy a published predecessor supports. Waiting only for
the successor was rejected because native replacement cannot create it until
the predecessor's held requests finish. Releasing immediately was rejected
because it would no longer prove that traffic overlaps the upgrade transition.

## Risks / Trade-offs

- **An unrelated runtime appears on the test port** → both release identity and
  admission state must match a declared side of the transition.
- **The release point is observed but convergence later fails** → the upgrade
  result, independent status, request bodies, rollback, and zero-residue checks
  remain authoritative and fail the test.

## Migration Plan

Update the existing proposal with one successor commit, rerun both Forge
compatibility jobs, and merge without rewriting the commit. No runtime
migration is required.
