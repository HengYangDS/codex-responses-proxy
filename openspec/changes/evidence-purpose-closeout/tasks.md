## 1. Close the placeholder

- [x] 1.1 Replace the generated canonical purpose with current product semantics.
- [x] 1.2 Preserve claims, chronicles, and Forge-audit ownership unchanged.

## 2. Verify

- [ ] 2.1 Run focused repository and documentation gates.
- [ ] 2.2 Execute exact-HEAD proof, archive, and post-archive proof.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `evidence-layout:Durable evidence roots have one project meaning` | `1.1` | `tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_uses_only_project_owned_semantic_roots` |
| `evidence-layout:Forge parity retains its existing semantic owner` | `1.2` | `tools/forge/audit.py; tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_uses_only_project_owned_semantic_roots` |
