# Design

This is a release-tooling forward fix. `CHANGELOG.md` remains the release
chronology owner; `[tool.uv].required-version` remains the bootstrap owner; the
committed lock remains the dependency owner. GitLab and GitHub each validate
their own native tags. Tag creation time is not release chronology authority.
No product runtime or provider protocol behavior changes.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Verification has one repository-owned owner` | `1.5` | `full-local-proof` |
