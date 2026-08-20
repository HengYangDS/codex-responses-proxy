## 1. Proof contracts

- [x] 1.1 Add failing evaluator tests for incomplete platform inventory, unequal
  checksum/signature bytes, and unequal trust identity; verify the focused test
  fails before implementation.
- [x] 1.2 Make the publication evaluator consume the platform SSOT and compare
  complete asset maps and trust identity; verify focused tests pass.
- [x] 1.3 Add workflow contract tests for non-overlapping review, accepted-branch,
  and tag proof contexts; verify current workflows fail the new contract.

## 2. CI and publication

- [x] 2.1 Partition GitLab and GitHub workflow triggers without duplicating the
  source matrix; verify actionlint and workflow contract tests pass.
- [x] 2.2 Remove per-Forge bundle signing and make both publishers consume the
  same pre-signed complete bundle; verify publisher and asset tests pass.
- [x] 2.3 Reconcile DR-0004 and operations documentation with the single-bundle
  authority; verify documentation and link gates pass.

## 3. Release readiness

- [x] 3.1 Run quick, quality, Python 3.12/3.13/3.14, native release, and
  OpenSpec strict gates on the complete change tree.
- [x] 3.2 Keep reviewed promotion, immutable tag publication, Forge parity, and
  installed-runtime acceptance outside the Change lifecycle. They consume the
  archived source; a defect found there starts a successor Change rather than
  reopening or circularly blocking this one.
