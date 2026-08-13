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

The repository SHALL advance local release `main` from accepted `dev` only
through the adopted package-only ETHOS closeout command. Proxy source SHALL NOT
define a second release-root mutation command. The transition SHALL be local,
exact-head guarded, and independent of both Forge publication planes.

#### Scenario: Candidate is proved

- **WHEN** `candidate/dev` and accepted `dev` identify the same clean, proved
  commit and local `main` is its ancestor
- **THEN** ETHOS closeout MAY fast-forward `main` by exact compare-and-swap
- **AND** no remote ref, tag, Release, asset, client, or Codex session state is
  changed.

#### Scenario: Local transition facts drift

- **WHEN** the observed head, proof, branch role, candidate, accepted root, or
  worktree cleanliness changes before apply
- **THEN** closeout SHALL fail before `main` moves.

#### Scenario: Direct main update is attempted

- **WHEN** direct Git mutation bypasses ETHOS
- **THEN** admission SHALL fail closed and the protected ref SHALL remain
  unchanged.

#### Scenario: A second product-owned transition is proposed

- **WHEN** Proxy code attempts to implement the same local `dev` to `main`
  mutation
- **THEN** repository review SHALL reject it as a duplicate lifecycle owner.

### Requirement: Portable product and repository UX

The installed executable SHALL not require Python, a source checkout, or repository-specific shell variables, while repository verification SHALL expose one documented locked command graph.

#### Scenario: Operator installs a release

- **WHEN** an operator invokes the documented product installation command
- **THEN** the command accepts explicit release metadata or a resolved manifest without personal paths, identities, or Forge coupling

#### Scenario: Contributor verifies a checkout

- **WHEN** a contributor runs the documented local gate
- **THEN** the same `uv`/`nox` graph is used by CI and ETHOS proof without a second test runner or compatibility wrapper
