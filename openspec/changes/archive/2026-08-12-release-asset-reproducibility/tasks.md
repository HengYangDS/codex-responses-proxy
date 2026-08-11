## 1. Reproduce and Repair

- [x] 1.1 Add a red regression for distinct installer provenance producing
  different native freeze inputs.
- [x] 1.2 Normalize the installed product distribution before PyInstaller.
- [x] 1.3 Prove focused release tests and two-root deterministic build inputs.

## 2. Verify

- [x] 2.1 Run OpenSpec strict validation, quality, Python matrix, and release
  gates from the exact work-lane HEAD.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Native release payloads are reproducible` | `1.1` | `red-test-installer-provenance` |
| `ci-diagnostics:Native release payloads are reproducible` | `1.2` | `normalized-distribution-record` |
| `ci-diagnostics:Native release payloads are reproducible` | `1.3` | `two-run-native-asset-parity` |
| `ci-diagnostics:Native release payloads are reproducible` | `2.1` | `exact-head-proof` |
