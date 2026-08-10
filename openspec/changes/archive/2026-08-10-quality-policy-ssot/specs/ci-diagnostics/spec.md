# CI Diagnostics Delta

## ADDED Requirements

### Requirement: Quality policy has explicit owners

The repository SHALL keep tool-native and repository-level quality policy in
one explicit owner per concern, while ETHOS registers executable gates.

#### Scenario: A quality gate is planned

- **WHEN** ETHOS plans or executes the Proxy quality proof
- **THEN** its Nox command consumes the tracked policy owners
- **AND** `pyproject.toml` does not duplicate lint, test, type, coverage, or
  repository-structure policy.

### Requirement: Commit semantics are machine checked

The repository SHALL admit human commit subjects only through one scoped
Conventional Commit grammar and SHALL classify generated lifecycle commits
through explicit semantic patterns.

#### Scenario: A human commit omits its semantic scope

- **WHEN** repository quality validates its subject
- **THEN** the commit is rejected before publication.
