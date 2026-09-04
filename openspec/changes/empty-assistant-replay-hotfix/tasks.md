## 1. Replay Semantics

- [x] 1.1 Preserve the observed empty assistant placeholder as a failing
  regression against the accepted source.
- [x] 1.2 Omit only that exact non-semantic item while retaining subsequent
  Provider-portable history in order.
- [x] 1.3 Keep empty scalar, empty list, malformed block, and all-placeholder
  requests rejected before upstream I/O.

## 2. Verification and Delivery

- [x] 2.1 Pass focused protocol tests, the complete Python matrix, and the
  repository quality gate with warnings treated as failures.
- [x] 2.2 Advance the sole release identity to the next SemVer patch and record
  the correction in the Changelog.
- [x] 2.3 Produce a signed Conventional Commit and pass the repository release
  and native-artifact gates against that exact committed source.
