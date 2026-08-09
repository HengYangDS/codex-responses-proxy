# Tasks

- [x] 1.1 Resolve the current stable dependency graph in an isolated clone.
- [x] 1.2 Apply only the stable resolver delta to `uv.lock`.
- [x] 1.3 Run the complete locked native verification graph.
- [x] 1.4 Execute exact-HEAD proof.
- [x] 1.5 Archive the Change.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `1.2` | `uv lock --check; nox -s quick quality tests-3.12 tests-3.13 tests-3.14 release` |
