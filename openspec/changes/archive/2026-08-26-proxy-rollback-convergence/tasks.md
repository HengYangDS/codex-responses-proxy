## 1. Completion contract

- [x] 1.1 Add a regression proving transient dual listeners delay success until
  the successor is the sole listener; verify it fails on the released source.
- [x] 1.2 Add a regression proving finalized health without listener convergence
  fails closed; verify it does not emit success.

## 2. Single-owner repair

- [x] 2.1 Bind the existing successor-finalization predicate to the current
  verified listener observation without adding state or a second wait loop.
- [x] 2.2 Apply the same predicate to controller-failure resolution and verify
  the focused deployment, control, and release tests pass.

## 3. Acceptance and release

- [x] 3.1 Make native compatibility acceptance require listener uniqueness at
  rollback return rather than polling afterward.
- [x] 3.2 Run strict OpenSpec validation, full quality, Python matrix, and
  release gates without warnings.
- [x] 3.3 Build the patch release candidate and prove the isolated native macOS
  upgrade, two-way rollback, recover, reload, uninstall, and reinstall journey.
