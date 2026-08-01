## Context

`tools/forge/project.sh` currently recomputes fingerprints inside nested
canonical/projected loops. With `C` canonical and `R` remote commits, it performs
`O(C * R)` fingerprint work even when only one new commit must be appended.

## Decisions

1. Build one canonical index and one projected index in a single helper process
   per invocation.
2. Read Git commit objects in one batch per index and reproduce the existing
   identity-neutral fingerprint byte-for-byte.
3. Join indexes once, retaining the exact zero-match, multiple-match, ambiguous
   projection, identity, signature, tree, and fast-forward failures.
4. Keep one narrow history helper beside the existing projector; it owns batch
   parsing and the unique join but exposes only one map operation. No helper
   package, compatibility wrapper, cache, or persistent state is added.

## Verification

- A red test first records Git invocations for an incremental projection and
  rejects quadratic command growth. A separate Git-command oracle proves that
  the new batch implementation preserves the retired shell fingerprint bytes;
  the oracle does not call the production fingerprint function and includes
  Git's UTC `Z` formatting boundary.
- All forward-only Forge tests pass, including divergence and trust failures.
- Release metadata, shell/static checks, and the full local quality gate pass
  before the source change is archived and committed. Exact-HEAD ETHOS proof,
  landing, and remote projection remain later lifecycle effects, not tasks that
  an uncommitted OpenSpec change can claim to have completed.

## Rollback

Revert the single projector commit before publication. The failed or reverted
invocation cannot update GitHub because the existing forward-only push remains
the final effect.
