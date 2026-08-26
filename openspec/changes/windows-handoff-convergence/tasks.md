## 1. Reproduce and localize

- [x] 1.1 Confirm the Windows native lifecycle failure is stable and isolated
      to `reload` after install, status, doctor, and a real Responses request pass.
- [x] 1.2 Trace the regression to post-FINALIZE TCP-owner equality introduced by
      3.1.1 and record the sequential 125-second and 65-second waits.
- [x] 1.3 Add a regression for finalized successor identity with stale Windows
      TCP-owner attribution and verify RED on 3.1.1 source.

## 2. Portable completion authority

- [x] 2.1 Capture the exact predecessor generation before requesting handoff.
- [x] 2.2 Replace post-transfer TCP-owner authority with predecessor exit,
      successor liveness, and finalized runtime identity.
- [x] 2.3 Reuse the same predicate and captured generation in controller-failure
      resolution, upgrade, rollback, and reload.

## 3. Source acceptance

- [x] 3.1 Pass focused handoff, control, process, and lifecycle tests.
- [x] 3.2 Pass strict OpenSpec, full quality, Python 3.12–3.14, and release gates
      without warnings.
- [x] 3.3 Pass macOS, Linux, and Windows native acceptance for the exact source
      tree, with both Forge projections green.
- [x] 3.4 Verify that the formal 8792 installation remains unchanged before the
      successor release is accepted.

## Post-archive lifecycle

Prepare the next SemVer patch from the accepted source, create and verify one
signed tag object, publish the same complete native asset set independently to
GitLab and GitHub, then upgrade the formal runtime transactionally. Complete
installed-runtime, real-request, rollback, recovery, uninstall, and residue
proof from the released assets. These external effects remain incomplete until
their current receipts exist.
