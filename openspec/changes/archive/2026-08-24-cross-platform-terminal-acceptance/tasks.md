## 1. Governance and regression baseline

- [x] 1.1 Migrate the repository Commitment to the current strict schema and verify current ETHOS can parse it without a compatibility reader.
- [x] 1.2 Reproduce every current lifecycle, recovery, and native-service defect with the narrowest platform or CLI regression.
- [x] 1.3 Verify the current provider-portable request, `store=false`, provider-scoped 429 cooldown, and three-route invariants remain green.

## 2. Native lifecycle convergence

- [x] 2.1 Make lifecycle creation and teardown share one exact service target and verify success, assertion failure, exception, timeout, and interruption paths leave no net host residue.
- [x] 2.2 Make recovery diagnostics distinguish healthy absence, valid recovery, invalid retained evidence, and serving-runtime health through public CLI tests.
- [x] 2.3 Remove empty directory residue nested below retired predecessor-owned files without claiming or deleting unowned content.
- [x] 2.4 Exercise install, status, recover, and uninstall through native artifacts on macOS, Linux, and Windows and record platform-specific evidence.

## 3. Product and release acceptance

- [x] 3.1 Run strict format, lint, docstring, type, architecture, coverage, security, documentation, and link gates without suppressions or project-controlled warnings.
- [x] 3.2 Run Python 3.12, 3.13, and 3.14 behavior suites and the native release and predecessor-compatibility gates.
- [x] 3.3 Verify GitHub and GitLab project the same CI semantics and accept the same signed product SHA independently.
- [x] 3.4 Install the signed release artifact transactionally, verify runtime health plus provider switching and continuous conversation behavior, then prove exact cleanup of superseded state.

## Acceptance evidence

- GitHub run `32682786044` built the signed `v3.0.2` native assets from
  `6580fc50835956f4726eeca1a40163acd5bdd27c`: macOS and Windows each ran the
  public native lifecycle suite with 37 passing tests; Linux ran the same four
  native lifecycle cases against a real user systemd manager.
- GitLab pipelines `5610`, `5611`, `5612`, `5614`, and `5615` independently
  accepted the same source SHA. GitHub and GitLab published byte-identical
  eight-file `v3.0.2` release inventories and the same annotated tag object
  `40d8574bfbcda9a040339de3738389af2107fafb`.
- The signed macOS asset upgraded the canonical installation to `3.0.2` without
  rejected requests. `status`, `doctor`, and `recover` reported a healthy
  service on `127.0.0.1:8792`; DMXAPI, AIHubMix, and UCloud verification
  completed through their distinct Proxy routes.
- The formal payload verified all 85 manifest files. One empty predecessor
  metadata directory exposed an ownership-bounded cleanup gap; the `3.0.3`
  successor regression removes such empty descendants while preserving
  unowned files and links.
