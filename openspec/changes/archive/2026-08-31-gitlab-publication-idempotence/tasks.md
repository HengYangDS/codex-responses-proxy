## 1. Contract and regression

- [x] 1.1 Add focused regressions proving complete and partial GitLab retries
      do not create duplicate package-file records.
- [x] 1.2 Add a focused regression proving bounded GitLab HTTP response details
      remain visible.

## 2. Implementation

- [x] 2.1 Make existing exact asset bytes reusable and upload only missing
      assets.
- [x] 2.2 Validate an existing exact Release before mutation and after a create
      race.

## 3. Verification

- [x] 3.1 Pass strict OpenSpec validation, focused tests, and the affected
      release gate.
- [x] 3.2 Pass the complete repository verification matrix for the immutable
      patch-release candidate.
