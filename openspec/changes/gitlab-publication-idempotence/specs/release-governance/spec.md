## ADDED Requirements

### Requirement: Forge publication is restartable without duplicate remote state

Each Forge publication adapter SHALL treat an existing immutable Release and
its exact asset bytes as reusable state. A retry SHALL upload only missing
assets, SHALL reject differing existing bytes or Release identity, and SHALL
preserve bounded provider diagnostics when transport or API validation fails.

#### Scenario: Retry after complete GitLab publication

- **WHEN** the exact tag, Release identity, and complete signed asset bundle
  already exist on GitLab
- **THEN** publication SHALL verify the existing records without uploading a
  second package-file record
- **AND** it SHALL report the publication as matched.

#### Scenario: Retry after partial GitLab asset upload

- **WHEN** some exact assets exist but no Release record has been created
- **THEN** publication SHALL reuse byte-identical assets
- **AND** it SHALL upload only missing assets before creating the Release.

#### Scenario: Existing remote state differs

- **WHEN** an existing asset byte sequence or Release identity differs from the
  requested immutable publication
- **THEN** publication SHALL fail closed without replacing that state.

#### Scenario: GitLab rejects a request

- **WHEN** GitLab returns an unsuccessful HTTP response
- **THEN** the failure SHALL identify the HTTP status and bounded provider
  response detail without exposing credentials.
