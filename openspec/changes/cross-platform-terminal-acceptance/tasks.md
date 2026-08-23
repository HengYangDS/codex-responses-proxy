## 1. Governance and regression baseline

- [x] 1.1 Migrate the repository Commitment to the current strict schema and verify current ETHOS can parse it without a compatibility reader.
- [x] 1.2 Reproduce every current lifecycle, recovery, and native-service defect with the narrowest platform or CLI regression.
- [x] 1.3 Verify the current provider-portable request, `store=false`, provider-scoped 429 cooldown, and three-route invariants remain green.

## 2. Native lifecycle convergence

- [x] 2.1 Make lifecycle creation and teardown share one exact service target and verify success, assertion failure, exception, timeout, and interruption paths leave no net host residue.
- [x] 2.2 Make recovery diagnostics distinguish healthy absence, valid recovery, invalid retained evidence, and serving-runtime health through public CLI tests.
- [ ] 2.3 Exercise install, status, recover, and uninstall through native artifacts on macOS, Linux, and Windows and record platform-specific evidence.

## 3. Product and release acceptance

- [x] 3.1 Run strict format, lint, docstring, type, architecture, coverage, security, documentation, and link gates without suppressions or project-controlled warnings.
- [x] 3.2 Run Python 3.12, 3.13, and 3.14 behavior suites and the native release and predecessor-compatibility gates.
- [ ] 3.3 Verify GitHub and GitLab project the same CI semantics and accept the same signed product SHA independently.
- [ ] 3.4 Install the signed release artifact transactionally, verify runtime health plus provider switching and continuous conversation behavior, then prove exact cleanup of superseded state.
