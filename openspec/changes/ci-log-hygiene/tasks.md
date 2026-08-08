# Tasks

- [x] 1.1 Add rejecting workflow-contract regressions.
- [x] 1.2 Declare process-scoped Git default-branch configuration.
- [x] 1.3 Isolate concurrent matrix caches by Python version.
- [x] 1.4 Run focused verification and release contracts.
- [x] 1.5 Run the full local proof; verify both hosted projections after landing.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted setup is deterministic and contention-free` | `1.1` | `tests/forge/contracts/test-github-actions.sh; tests/forge/contracts/test-github-release.sh` |
