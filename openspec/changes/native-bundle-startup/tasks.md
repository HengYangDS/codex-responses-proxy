# Tasks

- [x] 1.1 Pin recursive native-bundle inventory and archive behavior with failing release tests.
- [x] 1.2 Pin candidate validation, prewarm ordering, rollback, and purge with failing lifecycle tests.
- [x] 2.1 Replace the one-file freezer path with the sole directory-bundle build.
- [x] 2.2 Bind archive, artifact admission, manifest, installation, handoff, and recovery to the complete bundle inventory.
- [x] 2.3 Delete fixed two-file assumptions and all obsolete one-file semantics.
- [x] 2.4 Align product, installation, and release documentation with the actual bundle UX.
- [x] 3.1 Run focused release and lifecycle tests.
- [x] 3.2 Run locked quick, quality, Python 3.12/3.13/3.14, and release sessions.
- [x] 3.3 Execute exact-HEAD full proof, archive the Change, and land it to the candidate train.

## Requirement To Task To Proof

| Requirement | Tasks | Proof |
| --- | --- | --- |
| `product-interface:One self-contained product executable` | `1.1` | `tests/release/test_assets.py::ReleaseAssetContracts::test_asset_command_packages_only_native_runtime_inputs` |
| `product-interface:Repository-owned verification separates wheel compatibility from native distribution` | `3.2` | `nox -s tests-3.12 tests-3.13 tests-3.14 release` |
| `runtime-upgrade:The installed payload has one current shape` | `1.2` | `tests/lifecycle/test_artifact.py; tests/lifecycle/test_integrity.py` |
| `runtime-upgrade:Upgrade uses the current native handoff protocol` | `2.2` | `nox -s release` |
| `runtime-upgrade:Recovery binds candidate, rollback, and live runtime` | `2.2` | `tests/lifecycle/test_transaction.py` |
| `runtime-upgrade:Rollback owns only current product files` | `2.2` | `tests/lifecycle/test_projection.py; tests/lifecycle/test_transaction.py` |
