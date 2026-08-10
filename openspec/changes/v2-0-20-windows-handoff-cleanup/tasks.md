# Tasks

- [x] 1.1 Reproduce the v2.0.19 Windows teardown failure from hosted logs.
- [x] 1.2 Add a failing regression for one transient mapped-module lock.
- [x] 1.3 Retry only `PermissionError` within a bounded cleanup deadline.
- [x] 2.1 Pass focused, complete locked, and native release gates.
- [ ] 3.1 Execute exact-HEAD proof and prepare the repair for archive and land.
- [ ] 3.2 Prepare v2.0.20 from accepted truth in a separate release change.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Native handoff fixtures release temporary bundles` | `1.2` | `focused-transient-lock-regression` |
| `ci-diagnostics:Native handoff fixtures release temporary bundles` | `1.3` | `complete-native-release-gate` |

## Post-land acceptance

Independent Forge CI, release assets, trusted installation, and runtime
acceptance require fresh hosted and runtime evidence. OpenSpec archival does not
assert them.
