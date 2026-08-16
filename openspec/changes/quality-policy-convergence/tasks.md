## 1. Coverage authority

- [x] 1.1 Define aggregate and semantic package as the blocking risk scopes.
- [x] 1.2 Make the TOML policy the sole threshold owner.
- [x] 1.3 Record risk, measurement, false-positive cost, remediation, and review semantics.

## 2. Implementation

- [x] 2.1 Keep admission at aggregate and semantic-package scope.
- [x] 2.2 Keep the collection and rendering configuration free of admission policy.
- [x] 2.3 Update canonical specifications and contract tests.

## 3. Verification

- [x] 3.1 Prove the new contract through failing-then-passing focused tests.
- [x] 3.2 Pass complete Ruff, type, quality, behavior-matrix, and release sessions.
- [ ] 3.3 Produce exact-HEAD proof, archive, integrate, and retire obsolete lanes.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Coverage is strict and host-independent` | `2.1`, `2.2` | `focused-coverage-contracts-and-quality-session` |
| `quality-boundaries:One structural quality boundary` | `1.2`, `1.3` | `strict-openspec-and-policy-owner-tests` |
