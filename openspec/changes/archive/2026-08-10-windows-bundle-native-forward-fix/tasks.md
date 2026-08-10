# Tasks

- [x] 1.1 Reproduce the native Windows failures from v2.0.18.
- [x] 1.2 Normalize the `commonpath` result and preserve rejection invariants.
- [x] 1.3 Scope the POSIX symlink fixture to compatible hosts.
- [x] 2.1 Advance VERSION, README, and Changelog to v2.0.19.
- [x] 2.2 Pass focused and full locked local gates.
- [x] 3.1 Execute exact-HEAD proof and prepare the archive and land transition.

## Requirement To Task To Proof

| Requirement | Tasks | Proof |
| --- | --- | --- |
| `ci-diagnostics:Native bundle containment uses filesystem identity` | `1.2` | `tests/release/test_assets.py::ReleaseAssetContracts::test_bundle_files_uses_platform_canonical_path_identity` |

## Post-land acceptance

Independent Forge CI, release assets, trusted installation, and runtime
acceptance are external transitions. Their completion requires fresh hosted and
runtime evidence; OpenSpec archival does not assert them.
