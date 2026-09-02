## 1. Target-bound rollback

- [x] 1.1 Add CLI regressions proving `--to-release` is required and delivered
  unchanged to the lifecycle owner.
- [x] 1.2 Add control regressions for active-target no-op, verified-predecessor
  execution, and mismatched-target rejection before apply.
- [x] 1.3 Implement the minimal CLI and control changes using the existing strict
  release-version authority; add no compatibility command or parallel state.

## 2. Interrupted reverse recovery

- [x] 2.1 Add a regression for an unselected materialized reverse transaction
  with no unused rollback snapshot and prove the current implementation fails.
- [x] 2.2 Add negative regressions for selection, installed state, command,
  immutable payload, and accepting-runtime drift; each must preserve the
  transaction and selected terminal state.
- [x] 2.3 Implement exact prior-terminal proof and delay snapshot loading until a
  selected candidate actually requires restoration.

## 3. Verification and hotfix delivery

- [x] 3.1 Run focused CLI, control, and transaction tests without warnings.
- [x] 3.2 Validate the OpenSpec Change strictly; run lifecycle modules, quick
  static checks, and the locked Python 3.12–3.14 matrix.
- [ ] 3.3 Run the release gate once, build the next signed hotfix, and verify the
  complete artifact set on both Forges at one exact commit and tree.
- [x] 3.4 In isolated roots, prove fresh install, upgrade, target-bound rollback,
  repeated same-target no-op, interrupted recovery, and uninstall without
  changing the formal installation.
- [ ] 3.5 From an independent control plane, repair the formal transaction and
  install the proven hotfix; verify status and doctor are healthy and the
  listener remains usable.
- [ ] 3.6 Archive the completed Change, close the Work Lane, delete delivery
  branches after acceptance, and record the incident lessons in the existing
  canonical decision/evidence surfaces without creating parallel authorities.
