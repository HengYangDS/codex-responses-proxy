## Context

`VERSION` is already 2.0.11 and accepted source proof is current. The remaining
source transition is chronology finalization: one empty `Unreleased` heading
followed by the dated 2.0.11 section on the exact release commit.

## Decisions

1. `CHANGELOG.md` remains the only user-visible release chronology.
2. The release heading uses the current UTC date, 2026-08-04.
3. `tools/release/metadata.py --provider gitlab --prepare-release` is the
   semantic release-preparation verifier before any tag exists.
4. The carrier is archived and the archive HEAD is proved before candidate and
   accepted landing.
5. Forge publication and runtime deployment are post-archive transitions owned
   by the active terminal closeout claim.

## Risks / Trade-offs

- Publication after UTC midnight would require a new forward-only release
  commit with the then-current UTC date; an already-published tag is never
  rewritten.
- The source carrier does not prove hosted CI, Release records, asset identity,
  installation, or live provider behavior.

## Migration Plan

Finalize the heading, pass release metadata and strict OpenSpec validation,
commit and execute exact-head proof, archive, prove the archive HEAD, then land
through candidate and accepted-root closeout before Forge publication.
