# Tasks

- [x] 1.1 Scope the missing-newline success integration test to POSIX.
- [x] 1.2 Preserve the Windows provider-owned, fail-closed regression.
- [x] 2.1 Run focused release tests and locked quick, quality, Python-matrix, and release gates.
- [ ] 2.2 Execute exact-HEAD ETHOS proof, archive the Change, and land the correction.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Release signing uses one provider-owned key path` | `1.1` | `tests/release/test_signing.py` |
