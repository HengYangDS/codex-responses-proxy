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

## 3. Lifecycle writer serialization

- [x] 3.1 Add one deterministic regression proving a second lifecycle writer is
      rejected before it reads or mutates transaction state.
- [x] 3.2 Reuse one mature cross-platform lock at the public lifecycle boundary;
      keep status and doctor read-only, and add no parallel lock registry.
- [x] 3.3 Prove the lock is released after success and exceptions on the supported
      Python/platform matrix.

## 4. Verification and releasable source

- [x] 4.1 Run focused CLI, control, and transaction tests without warnings.
- [x] 4.2 Validate the OpenSpec Change strictly; run lifecycle modules, quick
      static checks, and the locked Python 3.12–3.14 matrix.
- [x] 4.3 Run the release gate once and prove complete local hotfix artifact
      construction from the exact source tree.
- [x] 4.4 In isolated roots, prove fresh install, upgrade, target-bound rollback,
      repeated same-target no-op, interrupted recovery, and uninstall without
      changing the formal installation.
- [x] 4.5 Route documented development and publication commands through the
      repository-locked `mise exec --locked --` boundary; keep uv and Nox
      environment ownership explicit without adding a wrapper script.
