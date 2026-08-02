## 1. Portable contract

- [x] 1.1 Add a synthetic successful `sysctl` argv-decoding contract that runs
  on every host while retaining the real Darwin-only subprocess integration.
- [x] 1.2 Advance `VERSION` and `CHANGELOG.md` to `2.0.7`, recording failed
  `v2.0.6` publication as immutable evidence.

## 2. Proof and release

- [x] 2.1 Validate OpenSpec, release metadata, focused process tests, full
  quality, and Python 3.12-3.14 behavior gates.
- [ ] 2.2 Commit with the governed GitLab identity, execute HEAD-bound ETHOS
  proof, land to `candidate/dev`, and close out to `dev`.
- [ ] 2.3 Publish signed provider-native `v2.0.7` tags and Releases on both
  Forges, require all hosted jobs to pass, and verify equal assets.
- [ ] 2.4 Install the admitted release transactionally, remove the temporary
  global-one containment only after runtime proof, and complete provider plus
  unchanged-task acceptance without editing Codex persistence.
