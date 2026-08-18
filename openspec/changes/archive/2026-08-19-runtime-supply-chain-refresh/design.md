## Context

See `proposal.md`. `uv.lock` is the dependency graph authority, and the
repository already owns one Nox command graph for local proof and CI.

## Goals / Non-Goals

**Goals:**

- Preserve one reproducible locked environment.
- Advance only reviewed stable releases.
- Reuse the existing verification and release sessions.

**Non-Goals:**

- No new framework, wrapper, provider policy, public behavior, or release.

## Decisions

1. Keep exact declarations and the generated lock together so resolution is
   reproducible and reviewable.
2. Reuse the existing Nox sessions; a second runner would create a parallel
   quality authority.
3. Accept the refresh only after OpenSpec, quick, quality, Python matrix, and
   release verification all pass from the locked environment.

## Risks / Trade-offs

- **Diagnostics can change** -> treat every new warning or error as a failure.
- **Release output can change** -> run the existing release session and inspect
  its native artifact checks before landing.

## Migration Plan

Apply the lock refresh, run the complete local command graph, commit the exact
tree, then archive this Change. Reverting that commit restores the prior graph.
