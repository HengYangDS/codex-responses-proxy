## 1. Reproduce and repair

- [x] 1.1 Reproduce the private GitLab package asset as anonymous HTTP 401 while
  authenticated GitLab API access returns the published bytes.
- [x] 1.2 Add a failing adapter contract that requires the GitLab provider CLI
  to own Release asset downloads.
- [x] 1.3 Replace anonymous GitLab asset reads with the existing authenticated
  provider API transport and pass the focused regression.

## 2. Prove and publish

- [x] 2.1 Update release identity and user-facing notes for the forward-only
  patch release.
- [ ] 2.2 Pass strict OpenSpec, release, presentation, quality, and Python
  3.12-3.14 gates with pristine diagnostics.
- [ ] 2.3 Archive the completed change, land the signed GitLab commit, project
  GitHub identity, and complete both provider-native release pipelines.
- [ ] 2.4 Run the fixed verifier against the live dual-Forge release and retain
  secret-free asset-parity evidence before installation.
