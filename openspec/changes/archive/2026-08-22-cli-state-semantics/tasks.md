## 1. Define lifecycle states

- [x] 1.1 Reproduce idle `recover` misclassifying an absent transaction as an invalid journal with a failing focused test.
- [x] 1.2 Add pristine-installation regressions for status, doctor, reload, uninstall, purge, Human output, JSON output, exit status, and next actions.
- [x] 1.3 Add invalid-carrier regressions proving existing unverifiable state remains fail closed and unchanged.

## 2. Converge implementation

- [x] 2.1 Implement one explicit no-transaction result and verify focused transaction tests pass.
- [x] 2.2 Make status and doctor classify absence, recovery, and degradation precisely and verify Human/JSON parity.
- [x] 2.3 Make uninstall and purge idempotent only for true absence and verify unknown content remains preserved.
- [x] 2.4 Tighten help and state-specific next actions and verify the complete public command matrix.

## 3. Prove and close

- [x] 3.1 Run focused CLI/lifecycle tests without warnings.
- [x] 3.2 Run `uv run --locked --no-sync nox -s full` and `uv run --locked --no-sync nox -s release`.
- [x] 3.3 Run `mise exec --locked -- openspec validate --all --strict` before lifecycle archival.
