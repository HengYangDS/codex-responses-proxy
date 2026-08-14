## MODIFIED Requirements

### Requirement: Verification has one repository-owned owner

Nox SHALL own the complete formatting, lint, typing, security, dependency,
documentation-link, architecture, test, release, and platform verification
graph. The committed uv lock SHALL own Python tool resolution, and project
metadata SHALL declare the exact current stable uv bootstrap used by local and
hosted verification. A GitLab job that synchronizes against an explicit Python
identity SHALL use that same identity for every no-sync execution. Warnings,
tracebacks, skipped required platforms, and missing runners SHALL NOT be
represented as success.

#### Scenario: A clean checkout is verified

- **WHEN** a contributor or Forge installs the declared uv bootstrap and runs the repository command
- **THEN** the lock supplies every runtime and quality dependency
- **AND** synchronized and executed Python identities are equal
- **AND** no ambient user site, another repository environment, or unpinned package resolution contributes to success

## MODIFIED Requirements

### Requirement: GitLab verification bootstrap is bounded and cached

GitLab verification SHALL start from an immutable image containing the
repository-selected UV and Python runtime. It SHALL reuse one target-platform
cache for package data and UV-managed Python runtimes, and SHALL NOT download a
different Python after a locked environment has been synchronized.

#### Scenario: A fresh GitLab job starts verification

- **WHEN** an admitted GitLab runner starts with an empty reusable cache
- **THEN** the job installs repository dependencies from `uv.lock`
- **AND** any managed compatibility interpreters are stored in the declared cache
- **AND** subsequent no-sync commands cannot select or download another interpreter
