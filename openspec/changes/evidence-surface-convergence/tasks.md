## 1. Establish the contract

- [x] 1.1 Verify that generic adopter parity is not configured or consumed.
- [x] 1.2 Verify that dual-Forge parity has one owner in `tools/forge/audit.py`.
- [x] 1.3 Add and observe the focused failing evidence-layout regression.

## 2. Converge the surface

- [x] 2.1 Remove the empty `evidence/parity/` placeholder.
- [x] 2.2 Admit only `evidence/claims` and `evidence/chronicle` as project-owned roots.
- [x] 2.3 Make the existing repository quality command enforce the contract.

## 3. Verify and close

- [x] 3.1 Run the focused contract suite and repository quality command.
- [ ] 3.2 Complete strict OpenSpec validation and exact-HEAD ETHOS proof.
- [ ] 3.3 Archive and land through public lifecycle commands when ETHOS admits the required Git ref effect.

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `evidence-layout:Durable evidence roots have one project meaning` | `2.2` | `tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_layout_gate_rejects_unowned_top_level_surfaces` |
| `evidence-layout:Forge parity retains its existing semantic owner` | `1.2` | `tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_uses_only_project_owned_semantic_roots` |
