## 1. Contract and TDD

- [x] 1.1 Isolate the first differing Linux archive member and prove semantic equality.
- [x] 1.2 Add a failing contract for the supported PyInstaller `ctypes` hook.
- [x] 1.3 Add failing lifecycle tests for exact-installed-inode prewarm and the configured `READY` deadline.

## 2. Implementation

- [x] 2.1 Collect `ctypes` as source through the official PyInstaller hook interface.
- [x] 2.2 Prewarm the verified committed executable inside the rollback domain.
- [x] 2.3 Remove the independent ten-second handoff cap and retain a bounded transport margin.

## 3. Verification and Release

- [x] 3.1 Pass focused lifecycle, verification, and rollback tests.
- [x] 3.2 Prove two locked Linux builds have identical executable and archive hashes.
- [x] 3.3 Pass quick, quality, Python 3.12-3.14, and native release sessions.
- [ ] 3.4 Complete exact-HEAD proof and release 2.0.39 independently on both Forges.
- [ ] 3.5 Verify Forge tree and asset parity, then hot-install the verified macOS asset.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `runtime-upgrade:Native release artifacts are reproducible` | `2.1` | `locked-linux-double-build-hashes` |
| `runtime-upgrade:Source-side upgrade authority` | `2.3` | `exact-executable-prewarm-and-ready-deadline-tests` |
| `product-interface:Native release validation exercises the installed product` | `3.3` | `supported-python-and-native-release-proof` |
