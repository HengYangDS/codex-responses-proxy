# Tasks

- [x] 1.1 Identify the split quality owners and the ETHOS gate boundary.
- [x] 1.2 Add failing contracts for explicit owner paths and metadata-only `pyproject.toml`.
- [x] 2.1 Move tool policy into the declared owners without weakening gates.
- [x] 2.2 Make repository structure and commit semantics consume tracked policy.
- [x] 3.1 Pass focused, quick, quality, and Python-matrix verification.
- [ ] 3.2 Execute exact-HEAD proof, archive, land, and retire the lane.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Quality policy has explicit owners` | `1.2` | `quality-owner-contract-red-green` |
| `ci-diagnostics:Quality policy has explicit owners` | `2.1` | `complete-quality-gate` |
| `ci-diagnostics:Commit semantics are machine checked` | `2.2` | `commit-policy-contract` |
