## 1. Contract and failing regressions

- [x] 1.1 Add CLI regressions for rollback discoverability, Human/JSON parity,
      explicit unavailability, and precise invalid-evidence errors; verify the
      focused CLI tests fail before implementation.
- [x] 1.2 Add transaction regressions proving finalize retains exactly one
      predecessor, fresh install retains none, and a second upgrade replaces the
      prior carrier; verify the focused lifecycle tests fail before implementation.
- [x] 1.3 Add lifecycle regressions for exact rollback success, corrupted or
      mismatched evidence, native-service rebind failure with compensation, and an
      unknown reverse-handoff outcome retained for recovery.

## 2. Single-owner implementation

- [x] 2.1 Extend the existing snapshot/state owners with one verified retained
      generation and exact successor binding; verify unit tests cover every carrier
      invariant without a compatibility reader.
- [x] 2.2 Extend the existing transaction and deployment owners to execute and
      compensate one reverse lifecycle transition; verify no parallel lifecycle
      state machine or duplicate payload primitive is introduced.
- [x] 2.3 Add the public rollback command and presentation over the shared result
      model; verify expected failures remain warning-free, traceback-free, and
      machine stable.
- [x] 2.4 Require an explicit repeatable-handoff capability and provide one
      bounded native-generation replacement for verified predecessors that lack it;
      reject incomplete runtime identity before mutation.

## 3. Product evidence and closeout

- [x] 3.1 Update README, architecture, recovery guidance, and CHANGELOG with the
      exact rollback/recover distinction and verify links and rendered Markdown.
- [x] 3.2 Run focused tests, affected static gates, then the full quality and
      Python matrix once; record warning-free results.
- [x] 3.3 Build and exercise isolated native artifacts on macOS, Linux, and
      Windows; prove the complete published-predecessor upgrade, rollback,
      recover, reload, and uninstall journey on macOS without changing the
      formal `127.0.0.1:8792` runtime.
- [x] 3.4 Archive the completed OpenSpec change only after strict validation and
      exact release-candidate acceptance prove one retained generation and zero
      host residue; formal publication remains the release lifecycle's responsibility.

## Requirement To Task To Proof

| Requirement                                                                      | Tasks               | Proof                                                                           |
| -------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------- |
| `product-interface:Small public lifecycle grammar`                               | `1.1`, `2.3`        | `tests/cli/test_lifecycle.py`                                                   |
| `product-interface:Explicit rollback has one public result model`                | `1.1`, `2.3`, `3.1` | `tests/cli/test_lifecycle.py`, rendered operator documentation                  |
| `runtime-upgrade:Successful upgrade retains one exact predecessor`               | `1.2`, `2.1`        | `tests/lifecycle/test_transaction.py`                                           |
| `runtime-upgrade:Explicit rollback is one reverse lifecycle transaction`         | `1.3`, `2.2`, `3.3` | lifecycle, release, and isolated native journey evidence                        |
| `runtime-upgrade:Repeated lifecycle transitions use declared runtime capability` | `1.3`, `2.4`, `3.3` | deployment strategy regressions and published-predecessor compatibility journey |
