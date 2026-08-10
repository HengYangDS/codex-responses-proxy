# Tasks

- [x] 1.1 Reproduce the Windows case-variant false escape.
- [x] 1.2 Implement host-canonical containment and keep escape rejection.
- [x] 2.1 Align README, VERSION, and Changelog at 2.0.18.
- [x] 2.2 Pass focused release contracts and the full locked local graph.
- [x] 3.1 Complete exact-HEAD local proof and make the Change ready to archive and land.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Native bundle containment uses filesystem identity` | `1.1` | `tests/release/test_assets.py::ReleaseAssetContracts::test_bundle_files_uses_platform_canonical_path_identity` |
