## 1. Dependency boundary

- [x] 1.1 Reproduce the hosted failure and prove PyInstaller is release-only.
- [x] 1.2 Split locked quality and release dependency groups.
- [x] 1.3 Make Nox request release tools only for native release validation.

## 2. Platform truth

- [x] 2.1 Pin the GitLab default, floor, and native images to `linux/amd64`.
- [x] 2.2 Replace implementation-count assertions with semantic contracts.

## 3. Acceptance

- [x] 3.1 Pass focused repository and Forge contracts.
- [x] 3.2 Pass quick, quality, Python matrix, and native release gates.
- [ ] 3.3 Produce exact-HEAD ETHOS proof and land the atomic change.

Hosted GitLab and GitHub publication remain independent post-land transitions;
they do not turn external Forge state into OpenSpec completion.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Dependency-minimal verification` | `1.2` | `focused-contracts` |
| `ci-diagnostics:Platform-true GitLab evidence` | `2.1` | `focused-contracts` |
