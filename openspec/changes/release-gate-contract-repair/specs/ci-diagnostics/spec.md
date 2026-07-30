## MODIFIED Requirements

### Requirement: Capability boundary

The CI diagnostics capability SHALL own diagnostic cleanliness across the
repository test runner, quality gate, dependency bootstrap, and provider
projections without owning application logs or provider infrastructure.
Release-contract tests SHALL verify repository-owner behavior and stable policy
values without depending on private shell syntax.

#### Scenario: A diagnostic contract changes

- **WHEN** a change alters warning, traceback, compile, cache, dependency
  bootstrap, or versioned-tool selection handling
- **THEN** the repository-owned command remains the semantic owner
- **AND** GitLab and GitHub remain thin projections over that command
- **AND** contract tests prove behavior rather than obsolete implementation text.

### Requirement: Quality tooling leaves no checkout cache

Compilation SHALL write bytecode below an isolated temporary prefix, and Ruff
SHALL run without a persistent checkout cache. Containerized dependency
installation SHALL explicitly select its noninteractive policy, suppress
routine package-manager chatter, and emit neither root-user nor frontend
fallback warnings.

#### Scenario: A clean quality gate completes

- **WHEN** the repository-owned quality command succeeds in hosted CI
- **THEN** no bytecode, coverage file, or Ruff cache remains in the checkout
- **AND** the job log contains no pip root-user or Debian frontend warning.
