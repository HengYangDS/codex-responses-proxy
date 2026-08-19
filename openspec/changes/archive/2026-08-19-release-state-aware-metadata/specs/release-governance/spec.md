# Release Governance Delta

## ADDED Requirements

### Requirement: Validation follows the release state

The repository SHALL expose distinct validation modes for ordinary source
checks, pre-tag preparation, and exact tagged-release verification.

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
