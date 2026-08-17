## ADDED Requirements

### Requirement: Semantic documentation architecture

Proxy documentation SHALL use one global entry point and SHALL organize its
small documentation kernel by semantic domain. Content document filenames
SHALL state their subjects. Repository checks and release metadata SHALL
consume those semantic paths directly.

#### Scenario: Reader enters the documentation

- **WHEN** a reader starts at `docs/README.md`
- **THEN** every canonical document SHALL be reachable through the domain map
- **AND** no redirect-only local index SHALL be required.

#### Scenario: A content-bearing register or policy is stored

- **WHEN** a document owns Decision Record registration or evidence policy
- **THEN** its filename SHALL identify that subject
- **AND** no container-named compatibility copy SHALL remain.

#### Scenario: Repository tooling consumes documentation paths

- **WHEN** quality or release validation reads a canonical document
- **THEN** it SHALL use the same semantic path exposed to readers
- **AND** the documentation tree and executable contract SHALL not diverge.
