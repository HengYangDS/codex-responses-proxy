## MODIFIED Requirements

### Requirement: Validation follows the release state

The repository SHALL expose distinct validation modes for ordinary source
checks, pre-tag preparation, and exact tagged-release verification. Every Forge
SHALL invoke the same provider-neutral product-tag verifier contract.

#### Scenario: Ordinary test in an untagged checkout

- **WHEN** the product test suite validates repository metadata
- **THEN** it SHALL use ordinary provider-neutral validation
- **AND** it SHALL NOT assume that the current release tag is absent

#### Scenario: Pre-tag preparation

- **WHEN** the release owner prepares a new immutable tag
- **THEN** `--prepare-release` SHALL require the current version tag to be absent

#### Scenario: Tagged release checkout

- **WHEN** CI evaluates an existing release tag
- **THEN** ordinary tests SHALL remain valid
- **AND** exact release validation SHALL use `--tag v<VERSION>`

#### Scenario: Forge verifies the product tag

- **WHEN** a Forge tag pipeline verifies the published product object
- **THEN** it SHALL supply only the repository, exact tag, and external trust anchor
- **AND** it SHALL NOT add a Forge identity to the verifier grammar
