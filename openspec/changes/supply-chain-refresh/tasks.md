# Tasks

- [x] 1.1 Audit direct, transitive, and hosted Action versions against their
  authoritative release sources.
- [x] 1.2 Add a failing workflow contract for the new immutable Action revisions.
- [x] 1.3 Refresh direct pins and regenerate the complete uv lock.
- [x] 1.4 Advance artifact Actions without mutable references or compatibility
  shims.
- [x] 1.5 Run focused lock and workflow contracts.
- [x] 1.6 Run full repository proof and archive the Change.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `1.2` | `tests/forge/contracts/test-github-actions.sh` |
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `1.3` | `uv lock --check; nox quality` |
