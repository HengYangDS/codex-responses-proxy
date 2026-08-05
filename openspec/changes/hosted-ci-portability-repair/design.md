## Context

The 2.0.11 branch projection reached both Forges, and all jobs obtained runners.
GitLab then rejected Changelog headings whose tags never existed on that Forge;
GitHub exposed Windows fixture assumptions, a stale release-assets contract,
and Linux branch coverage of 94.57%. Local macOS success therefore did not prove
the hosted matrix.

## Decisions

1. Changelog release headings represent published canonical releases. Candidate
   versions that never reached the canonical Forge are folded forward into the
   next published release instead of being treated as hidden releases.
   Chronology reads the explicitly selected provider remote rather than the
   checkout's ambient local tag namespace.
2. Test construction uses `RuntimeContext` and platform inventory as the source
   of executable names and rendered paths; tests do not concatenate POSIX
   separators or assert POSIX mode changes on Windows.
3. Platform-specific branches receive deterministic tests on the platform where
   they execute. Coverage exclusions or lowered floors are forbidden.
4. Verification workflows test release asset composition through the current
   native release interface; no source-only job fabricates a native asset.
5. Existing failed pipelines and existing remote tags remain immutable.
6. Runner absence is rejected before branch projection. The admission reads
   caller-supplied Forge coordinates, an adopter-supplied GitLab runner tag, and
   live API state; it does not encode a runner label, workstation path, account,
   or credential. GitLab requires an active, online, unpaused project runner
   with that exact tag. GitHub requires Actions and both tracked workflows to be
   active.

## Risks / Trade-offs

- Forward chronology repair changes presentation but preserves every code commit
  in Git history.
- Windows behavior cannot be claimed from mocked POSIX execution; hosted Windows
  jobs remain authoritative.
- Hosted CI remains a separate proof boundary after local gates.

## Migration Plan

Write RED contracts for each hosted failure cluster, repair the smallest
semantic owner, run focused and full local gates including a clean Linux
environment, execute exact-head proof, archive the carrier, land through
candidate and accepted roots, then forward-project both Forge branches and wait
for fresh hosted results.
