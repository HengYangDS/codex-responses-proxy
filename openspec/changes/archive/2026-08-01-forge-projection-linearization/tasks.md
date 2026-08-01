## 1. Contract

- [x] 1.1 Add an incremental-history regression test that fails on quadratic
  Git command growth.
- [x] 1.2 Specify one-fingerprint-per-commit matching without relaxing any
  Forge admission invariant.

## 2. Implementation

- [x] 2.1 Replace nested fingerprint recomputation with two linear indexes and
  one unique join.
- [x] 2.2 Preserve existing mapping output and bounded failure diagnostics.

## 3. Proof

- [x] 3.1 Pass focused Forge tests, strict OpenSpec, release metadata, and
  shell/static checks.
- [x] 3.2 Pass the complete local quality matrix and freeze the source candidate
  for its signed commit. Exact-HEAD proof, landing, and remote projection are
  separately observed lifecycle effects after this change is archived.
