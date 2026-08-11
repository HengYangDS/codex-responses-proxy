## 1. Path Identity

- [x] 1.1 Reproduce the container/host path mismatch with the focused workflow contract test.
- [x] 1.2 Write and upload the Linux asset through one shared workspace path.
- [x] 1.3 Advance `VERSION` and Changelog to the v2.0.29 forward fix.

## 2. Verification

- [x] 2.1 Pass the Forge and release contract tests.
- [x] 2.2 Build and black-box accept the local native release asset.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted native asset jobs preserve path identity` | `1.2` | `tests/forge/test_workflow_contracts.py::test_linux_native_workflows_use_the_same_container_runtime` |
