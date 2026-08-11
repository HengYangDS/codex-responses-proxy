# Tasks

## Process ownership

- [x] 1.1 Reproduce the Windows mapped-module failure from the v2.0.22 run.
- [x] 1.2 Add failing contracts for argv denial and PID reuse.
- [x] 1.3 Capture PID generation at health proof and use it for ordered teardown.
- [x] 1.4 Pass focused unit and native release tests on macOS.

## Verification and release

- [x] 2.1 Advance VERSION and Changelog to v2.0.23 without rewriting v2.0.22.
- [ ] 2.2 Pass quick, quality, Python 3.12/3.13/3.14, and native release gates.
- [ ] 2.3 Complete exact-HEAD proof, archival, candidate landing, and accepted closeout.
- [ ] 2.4 Publish independent signed GitLab and GitHub v2.0.23 releases and prove asset parity.
- [ ] 2.5 Install a trusted formal asset and complete provider and client runtime acceptance.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `1.2` | `captured-process-generation-contract` |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `1.3` | `ordered-native-payload-teardown` |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `2.2` | `cross-platform-native-release` |
