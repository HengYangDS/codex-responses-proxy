## 1. Align ownership

- [x] 1.1 Replace the universal `.config/checks/` ownership statement with the native-discovery rule and verify the quality contract rejects the old wording.
- [x] 1.2 Add `.pytest_cache/` to the local-state boundary and verify the quality contract requires it.

## 2. Prove and close

- [x] 2.1 Run focused quality contract tests and `nox -s quick`; verify both pass without warnings.
- [x] 2.2 Run strict OpenSpec validation, archive the completed tooling-only Change, and verify no active Change remains.
