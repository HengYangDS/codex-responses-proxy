## 1. Contract

- [x] 1.1 Define native command ownership for Windows and POSIX.
- [x] 1.2 Preserve strict foreign-path and rollback behavior.

## 2. TDD

- [x] 2.1 Reproduce the Windows matrix failures with host-native expectations.
- [x] 2.2 Make failure injection select the native projection primitive.
- [x] 2.3 Make CLI installed-state fixtures host-native.

## 3. Verification and Release

- [x] 3.1 Pass focused lifecycle and CLI tests.
- [x] 3.2 Pass quick, quality, Python 3.12-3.14, and release sessions.
- [ ] 3.3 Complete exact proof, archive, land, accepted closeout, and release 2.0.38.
- [ ] 3.4 Verify both independent Forge publications and the installed runtime.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `runtime-upgrade:Source-side upgrade authority` | `1.1` | `native-link-kind-and-samefile-contracts` |
| `runtime-upgrade:Source-side upgrade authority` | `1.2` | `foreign-path-and-rollback-tests` |
| `runtime-upgrade:Source-side upgrade authority` | `2.1` | `windows-matrix-failure-reproduction` |
| `runtime-upgrade:Source-side upgrade authority` | `2.2` | `platform-selected-failure-injection` |
| `product-interface:Human and machine interfaces share one result model` | `2.3` | `host-native-installed-state-fixture` |
| `product-interface:Human and machine interfaces share one result model` | `3.1` | `focused-lifecycle-and-cli-tests` |
| `product-interface:Human and machine interfaces share one result model` | `3.2` | `supported-python-and-quality-proof` |
| `runtime-upgrade:Source-side upgrade authority` | `3.2` | `supported-python-and-native-release-proof` |
