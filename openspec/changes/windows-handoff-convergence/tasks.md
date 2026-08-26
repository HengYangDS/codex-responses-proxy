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

## 3. Verification and release

- [x] 3.1 Pass focused handoff, control, process, and lifecycle tests.
- [x] 3.2 Pass strict OpenSpec, full quality, Python 3.12–3.14, and release gates
      without warnings.
- [ ] 3.3 Publish a new SemVer patch only after macOS, Linux, and Windows native
      lifecycle acceptance and both Forge projections are green.
- [ ] 3.4 Verify the formal 8792 installation remains unchanged until release
      acceptance, then complete installed-runtime and residue proof.
