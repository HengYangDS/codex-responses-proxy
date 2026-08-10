# Tasks

- [x] 1.1 Define the canonical positive evidence taxonomy in the active specification.
- [x] 1.2 Make repository quality consume the canonical taxonomy without a duplicate allowlist.
- [x] 1.3 Align the human evidence policy and active tests with the positive taxonomy.
- [x] 2.1 Run focused repository-quality and OpenSpec validation tests.
- [ ] 2.2 Run exact-HEAD proof, archive the Change, and run post-archive proof.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `evidence-layout:Durable evidence families have one positive taxonomy` | `1.1` | `tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_uses_only_project_owned_semantic_roots` |
| `evidence-layout:Forge comparison has one semantic owner` | `1.3` | `tools/forge/audit.py; tests/quality/test_contract.py::TestQualityPolicyContracts::test_evidence_uses_only_project_owned_semantic_roots` |
