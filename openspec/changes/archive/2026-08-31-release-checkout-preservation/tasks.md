## 1. Prove the defect

- [x] 1.1 Add a real Git repository regression that proves successful and
      failed release-source verification preserve the active symbolic ref,
      `HEAD`, index, and worktree.

## 2. Remove the mutation

- [x] 2.1 Replace the mutating checkout preparation helper with read-only exact
      tag verification and prove the regression passes.
- [x] 2.2 Delete the redundant public checkout command, reuse release metadata
      validation in CI, and verify generated workflow contracts.

## 3. Verify the atom

- [x] 3.1 Pass strict OpenSpec validation, focused release tests, repository
      quality, and native release verification.

## Post-implementation lifecycle

After the implementation is frozen in one signed commit, run exact-HEAD ETHOS
proof, archive this Change, re-prove the archive commit, and integrate it into
candidate and accepted truth before assigning a new release identity.
