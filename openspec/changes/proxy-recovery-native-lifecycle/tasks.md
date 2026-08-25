## 1. Recovery carrier semantics

- [x] 1.1 Add regressions for missing, symbolic-link, malformed,
  non-canonical, unsupported-schema, and invalid-field journals.
- [x] 1.2 Implement one precise fail-closed classifier in the journal owner and
  prove invalid bytes remain unchanged.
- [x] 1.3 Verify Human and JSON recovery errors retain one stable code and one
  read-only next action.

## 2. Native lifecycle ownership

- [x] 2.1 Reverify macOS service creation and teardown use one exact resolved
  context and leave no noncanonical launchd residue.
- [x] 2.2 Verify Linux systemd-user and Windows Task Scheduler adapters preserve
  the shared lifecycle contract.
- [x] 2.3 Exercise isolated install, status, reload, upgrade, rollback, recover,
  and uninstall without touching the formal runtime.

## 3. Proof and closeout

- [x] 3.1 Run focused lifecycle and CLI tests without warnings.
- [x] 3.2 Run the affected quality, Python compatibility, and release gates.
- [ ] 3.3 Archive the Change, land the exact proved commit, and remove only
  proven obsolete lane and host residue.

## Requirement To Task To Proof

| Requirement                                                          | Task  | Proof                                                                     |
| -------------------------------------------------------------------- | ----- | ------------------------------------------------------------------------- |
| `product-interface:Human and machine interfaces share one result model` | `1.3` | `tests/cli/test_lifecycle.py; tests/lifecycle/test_control.py`             |
| `runtime-upgrade:Recovery binds candidate, rollback, and live runtime`   | `1.1` | `tests/lifecycle/test_transaction.py; isolated recovery journey receipt`  |
| `runtime-upgrade:Native supervision is self-contained and portable`     | `2.1` | `tests/lifecycle/supervision; tests/release/test_native_lifecycle.py`      |
