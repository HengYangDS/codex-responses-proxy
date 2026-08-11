# Tasks

## Contract

- [x] 1.1 Add failing tests for exact Linux runtime parity across Forge files.
- [x] 1.2 Add failing tests for checkout-path and installer-cache exclusion.
- [x] 1.3 Add a two-root reproducibility test for the release bundle.

## Implementation

- [x] 2.1 Define and project the immutable Linux release runtime from one SSOT.
- [x] 2.2 Remove non-runtime installer provenance before native bundling.
- [x] 2.3 Set deterministic build inputs without adding a second build owner.

## Verification and delivery

- [x] 3.1 Pass focused tests, quick, quality, all Python matrices, and release.
- [ ] 3.2 Produce exact-HEAD proof, archive the Change, and close accepted source.
- [ ] 3.3 Publish v2.0.26 independently on both Forges and prove Linux byte parity.
- [ ] 3.4 Install one trusted macOS asset and complete runtime acceptance.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Forge release projections use one exact common runtime` | `1.1` | `tests/release/test_metadata.py; tests/forge/test_workflow_contracts.py` |
| `ci-diagnostics:Forge release projections use one exact common runtime` | `2.1` | `pyproject.toml; .github/workflows/verify.yml; .gitlab-ci.yml` |
| `ci-diagnostics:Native release payloads are reproducible` | `1.2` | `tests/release/test_assets.py` |
| `ci-diagnostics:Native release payloads are reproducible` | `1.3` | `two-root-native-release-parity` |
| `ci-diagnostics:Native release payloads are reproducible` | `2.2` | `noxfile.py; tools/release/assets.py` |
| `ci-diagnostics:Native release payloads are reproducible` | `3.3` | `independent-forge-v2.0.26-asset-parity` |
