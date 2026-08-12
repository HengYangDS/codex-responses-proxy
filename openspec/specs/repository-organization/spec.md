# repository-organization Specification

## Purpose
TBD - created by archiving change proxy-repository-organization-convergence. Update Purpose after archive.
## Requirements
### Requirement: One release identity

Proxy SHALL use tracked `VERSION` as the sole product release identity for package metadata, artifact names, changelog headings, tags, and installation records.

#### Scenario: Release metadata is consistent

- **WHEN** local or hosted release verification runs
- **THEN** every release surface resolves the same SemVer value from `VERSION`

#### Scenario: A competing version is introduced

- **WHEN** a tool or workflow supplies a conflicting inferred version
- **THEN** verification fails before asset creation or publication

### Requirement: Governed release-branch convergence

The repository SHALL advance release `main` from accepted `dev` only through ETHOS closeout; `candidate/dev` and `work/*` remain local-only.

#### Scenario: Candidate is proved

- **WHEN** candidate head is clean, proved, and accepted
- **THEN** closeout may fast-forward `main` with exact-head and receipt checks

#### Scenario: Direct main update is attempted

- **WHEN** direct Git mutation bypasses ETHOS
- **THEN** admission fails closed and the protected ref remains unchanged

### Requirement: Portable product and repository UX

The installed executable SHALL not require Python, a source checkout, or repository-specific shell variables, while repository verification SHALL expose one documented locked command graph.

#### Scenario: Operator installs a release

- **WHEN** an operator invokes the documented product installation command
- **THEN** the command accepts explicit release metadata or a resolved manifest without personal paths, identities, or Forge coupling

#### Scenario: Contributor verifies a checkout

- **WHEN** a contributor runs the documented local gate
- **THEN** the same `uv`/`nox` graph is used by CI and ETHOS proof without a second test runner or compatibility wrapper
