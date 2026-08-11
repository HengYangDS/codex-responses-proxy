# Tasks

- [x] 1.1 Reproduce publication readiness rejecting the retired scalar fields.
- [x] 1.2 Replace them with the canonical independent peer collection.
- [x] 1.3 Add a repository contract that admits only local commands and peers.
- [x] 2.1 Pass focused quality and ETHOS publication-readiness checks.
- [x] 2.2 Transfer exact-HEAD proof, archival, and relanding to the governed post-change lifecycle.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Publication topology has one declared peer collection` | `1.2` | `.ethos/release.toml` |
| `ci-diagnostics:Publication topology has one declared peer collection` | `1.3` | `tests/quality/test_contract.py::TestQualityPolicyContracts::test_publication_topology_has_only_declared_independent_peers` |
| `ci-diagnostics:Publication topology has one declared peer collection` | `2.1` | `ethos publish --json` reports `remote_topology.state=ready` |

Forge publication, asset parity, formal installation, and runtime acceptance
remain ordered external transitions after this source Change closes.
