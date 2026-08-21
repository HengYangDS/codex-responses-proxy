## 1. Repair ownership

- [x] 1.1 Remove native-supervisor mutation from the handoff child and verify focused CLI and protocol tests pass.
- [x] 1.2 Rebind and read back native supervision before listener handoff, then verify installation ordering, rollback, and unknown-outcome tests pass.
- [x] 1.3 Update the runtime-upgrade contract, architecture, governance, and Changelog to name the single transaction owner; verify strict OpenSpec validation passes.

## 2. Prove the product

- [x] 2.1 Run `uv run --locked --no-sync nox -s quick quality` and verify both sessions pass without warnings.
- [x] 2.2 Run `uv run --locked --no-sync nox -s tests-3.12 tests-3.13 tests-3.14` and verify the supported Python matrix passes.
- [x] 2.3 Run the complete macOS and Linux native release flows from the exact candidate tree and verify frozen install, handoff, teardown, and zero host residue.
- [x] 2.4 Run native macOS, Linux, and Windows product acceptance on the signed proposal commit, not only its interpreter matrix; verify every hosted job binds to the exact product commit.
- [x] 2.5 Collapse pytest discovery and warning policy into root-native `pytest.ini`; remove explicit configuration plumbing and verify focused, quick, quality, and strict OpenSpec gates.
