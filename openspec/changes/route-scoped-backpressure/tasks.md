## 1. Contract and TDD

- [x] 1.1 Add RED admission tests proving same-route single-flight and
  cross-route concurrency under a global limit greater than one.
- [x] 1.2 Add a RED transport test proving cooldown established while queued
  prevents a second upstream call.
- [x] 1.3 Implement route-scoped admission and the post-queue cooldown check;
  obtain focused GREEN without changing HTTP 429 retry semantics.

## 2. Release candidate

- [x] 2.1 Apply the Linux CI forward fix, update architecture truth, VERSION,
  and CHANGELOG for 2.0.6.
- [x] 2.2 Run strict OpenSpec, focused tests, full quality, statement and branch
  coverage above 95%, and Python 3.12-3.14 behavior gates.
- [ ] 2.3 Commit with the governed identity, execute HEAD-bound ETHOS proof,
  archive this change, land, and close out the accepted-root transition.

## 3. Publication and runtime acceptance

- [ ] 3.1 Publish signed 2.0.6 tags and Releases independently to GitLab and
  GitHub while preserving failed 2.0.5 history.
- [ ] 3.2 Verify hosted CI, signatures, release assets, and cross-Forge asset
  identity before installation.
- [ ] 3.3 Install transactionally, remove the temporary global-one containment,
  and verify same-route protection plus different-route concurrency.
- [ ] 3.4 Verify UCloud, Azure, DMXAPI, replay, empty-response recovery, and
  repeated continuation of the unchanged original Codex task.
