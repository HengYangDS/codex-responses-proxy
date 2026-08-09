# Tasks

- [x] 1.1 Confirm all accumulated product changes are archived and the lane is clean.
- [x] 1.2 Run the complete locked native verification graph.
- [x] 1.3 Execute exact-HEAD full proof.
- [x] 1.4 Archive the integration Change and land by exact candidate CAS.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Terminal candidate integration is exact and local` | `1.3` | `ethos prove --execute --full --expect-head <HEAD> --json` |
