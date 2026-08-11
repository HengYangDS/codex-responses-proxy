# Tasks

## Process ownership

- [x] 1.1 Reproduce the Windows mapped-module failure from the v2.0.22 run.
- [x] 1.2 Add failing contracts for argv denial and PID reuse.
- [x] 1.3 Capture PID generation at health proof and use it for ordered teardown.
- [x] 1.4 Pass focused unit and native release tests on macOS.

## Verification and release

- [x] 2.1 Advance VERSION and Changelog to v2.0.23 without rewriting v2.0.22.
- [x] 2.2 Pass quick, quality, Python 3.12/3.13/3.14, and native release gates.

## Post-change lifecycle

Exact-HEAD proof, archival, landing, dual-Forge publication, formal installation,
and runtime acceptance are ordered transitions outside this source Change. Each
requires fresh evidence from its own plane; completing this checklist asserts
none of those external effects.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `1.2` | `captured-process-generation-contract` |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `1.3` | `ordered-native-payload-teardown` |
| `ci-diagnostics:Hosted fixtures own deterministic repository and process identities` | `2.2` | `cross-platform-native-release` |
