# Tasks

- [x] 1.1 Add focused failing tests for zombie liveness and bounded termination.
- [x] 1.2 Classify exact-generation zombies as exited in the process-ownership primitive.
- [x] 2.1 Run focused supervision and native handoff tests on macOS and Linux.
- [ ] 3.1 Run quick, quality, Python matrix, native release, and exact-HEAD ETHOS proof.
- [ ] 4.1 Publish a new SemVer patch through independent GitLab and GitHub planes.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `process-ownership:Exited process tombstones are terminal` | `1.1` | `tests/lifecycle/supervision/test_process.py` |
| `process-ownership:Exited process tombstones are terminal` | `1.2` | `src/codex_responses_proxy/lifecycle/supervision/process.py` |
| `process-ownership:Exited process tombstones are terminal` | `2.1` | `focused-macos-and-linux-process-lifecycle-proof` |
| `process-ownership:Exited process tombstones are terminal` | `3.1` | `exact-head-local-proof` |
