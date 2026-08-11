## ADDED Requirements

### Requirement: Publication topology has one declared peer collection

The repository SHALL declare local verification and installation once and
represent every remote publication plane as one peer in the same collection.
Forge-specific scalar aliases SHALL NOT be accepted as parallel configuration
owners.

#### Scenario: GitLab and GitHub are both available

- **WHEN** publication readiness compiles the repository release declaration
- **THEN** GitLab and GitHub appear as independent peers with their own Git remote and CI surface
- **AND** neither peer supplies credentials, jobs, tags, Releases, or assets for the other.

#### Scenario: A retired scalar field returns

- **WHEN** the publication table contains a Forge-specific remote or CI scalar
- **THEN** repository quality rejects the declaration
- **AND** no compatibility reader or inferred default peer is used.
