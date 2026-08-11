# Tasks

- [x] 1.1 Add regressions for complete provider-owned keys and incomplete Windows input.
- [x] 1.2 Preserve original key identity unless POSIX newline repair is required.
- [x] 2.1 Run focused release tests and the locked quick, quality, and Python matrix gates.
- [ ] 2.2 Execute exact-HEAD ETHOS proof, archive the Change, and land the forward fix.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Release signing preserves provider-owned key security` | `1.1` | `tests/release/test_signing.py::test_sign_and_verify_preserves_complete_provider_key_path` |
| `ci-diagnostics:Release signing preserves provider-owned key security` | `1.1` | `tests/release/test_signing.py::test_sign_and_verify_does_not_rewrite_incomplete_windows_key` |
| `ci-diagnostics:Release signing preserves provider-owned key security` | `1.2` | `tools/release/signing.py::_signing_key` |
| `ci-diagnostics:Release signing preserves provider-owned key security` | `2.1` | `uv run --locked --no-sync nox -s quick quality tests-3.12 tests-3.13 tests-3.14` |
