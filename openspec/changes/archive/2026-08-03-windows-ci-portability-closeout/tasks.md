## 1. TDD

- [x] 1.1 Add a failing test proving non-Darwin process discovery consumes one
  batch inventory without per-PID command queries.
- [x] 1.2 Reproduce the hosted Windows path assertion with a platform-native
  expected path.

## 2. Implementation

- [x] 2.1 Reuse inventory command lines on non-Darwin hosts while preserving
  native Darwin argv and signal-time identity revalidation.
- [x] 2.2 Update the 2.0.7 release note with the portable CI closeout.

## 3. Verification and release boundary

- [x] 3.1 Run focused tests, strict OpenSpec validation, full quality, both
  coverage floors, and Python 3.12-3.14 compile/test gates.
- [x] 3.2 Transfer archive, signed commit, HEAD-bound proof, governed landing,
  both Forge main pipelines, tagging, and installation to the post-archive
  lifecycle without claiming any external transition complete.

## Post-archive lifecycle

Official archival, signed commit, HEAD-bound proof, governed landing, both Forge
main pipelines, immutable signed tags and Releases, asset parity, transactional
installation, live provider verification, original-task continuation, and lane
housekeeping remain separate transitions. None is complete without fresh
external evidence.
