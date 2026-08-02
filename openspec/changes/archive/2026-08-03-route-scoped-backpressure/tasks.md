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
- [x] 2.3 Commit with the governed identity and execute HEAD-bound ETHOS proof.

## 3. Post-archive acceptance boundary

Publication, installation, provider behavior, and unchanged-task continuation
remain active claim evidence after this repository change is archived. They are
not planning-artifact completion criteria and must not be marked complete by
OpenSpec archival.

- Signed 2.0.6 tags and Releases must be published independently to GitLab and
  GitHub while failed 2.0.5 history remains intact.
- Hosted CI, signatures, release assets, and cross-Forge asset identity must be
  verified before installation.
- Transactional installation must remove the temporary global-one containment
  and verify same-route protection plus different-route concurrency.
- UCloud, Azure, DMXAPI, replay, empty-response recovery, and repeated
  continuation of the unchanged original Codex task remain required terminal
  acceptance evidence.
