# release-governance Specification

## Purpose
Define the provider-neutral validation, product identity, release construction,
and independent publication contract from reviewed source through installation
authority.

## Requirements

### Requirement: Validation follows the release state

The repository SHALL expose distinct, non-overlapping validation modes for
reviewed source changes, accepted branch projections, pre-tag preparation, and
exact tagged-release verification. Every Forge SHALL project the same
provider-neutral contracts without repeating a complete proof for the same
commit and proof context.

#### Scenario: Ordinary test in an untagged checkout

- **WHEN** the product test suite validates repository metadata outside a
  review or tag pipeline
- **THEN** it SHALL use ordinary provider-neutral validation
- **AND** it SHALL NOT assume that the current release tag is absent

#### Scenario: Reviewed source change

- **WHEN** an MR or PR evaluates a proposed product commit
- **THEN** the complete source, quality, supported-Python, and platform-test
  proof SHALL run once for that review context
- **AND** a proposal branch push SHALL NOT run a duplicate complete proof

#### Scenario: Accepted branch projection

- **WHEN** the reviewed commit is absorbed into `dev` or promoted to `main`
- **THEN** the branch pipeline SHALL confirm repository and release metadata
- **AND** it SHALL NOT repeat the complete review test matrix

#### Scenario: Pre-tag preparation

- **WHEN** the release owner prepares a new immutable tag
- **THEN** `--prepare-release` SHALL require the current version tag to be absent

#### Scenario: Tagged release checkout

- **WHEN** CI evaluates an existing release tag
- **THEN** exact release validation SHALL use `--tag v<VERSION>`
- **AND** release jobs SHALL build or consume every supported native platform
  asset without repeating the complete review test matrix

#### Scenario: Forge verifies the product tag

- **WHEN** a Forge tag pipeline verifies the published product object
- **THEN** it SHALL supply only the repository, exact tag, and external trust
  anchor
- **AND** it SHALL NOT add a Forge identity to the verifier grammar

### Requirement: Dual-Forge releases project one complete signed bundle

The admitted native builder for each supported platform SHALL produce that
platform's asset pair. The release owner SHALL admit those assets into exactly
one complete release bundle and sign it once. Each selected Forge SHALL publish
and re-download the exact same files, and dual-Forge parity SHALL require equal
complete inventories and digests.

#### Scenario: Physical build execution

- **WHEN** native assets are built on different platform executors or one
  executor is hosted by a selected Forge
- **THEN** runner placement SHALL NOT make that Forge a product authority
- **AND** no Forge publication adapter SHALL build, repackage, or sign assets

#### Scenario: Complete parity

- **WHEN** GitLab and GitHub both publish a release tag
- **THEN** each release SHALL contain every archive and manifest named by the
  supported platform SSOT plus `SHA256SUMS` and `SHA256SUMS.sig`
- **AND** every corresponding digest SHALL be identical
- **AND** both releases SHALL report the same product trust-anchor digest

#### Scenario: Incomplete or independently signed projection

- **WHEN** either Forge omits a platform, changes any file, regenerates the
  checksum inventory, re-signs the bundle, or reports a different trust anchor
- **THEN** publication parity SHALL fail closed
- **AND** the incomplete release SHALL NOT be installation authority

#### Scenario: Optional peer unavailable

- **WHEN** one Forge is unavailable
- **THEN** the other Forge MAY publish the unchanged complete bundle
- **AND** the result SHALL be reported as one-sided publication rather than
  dual-Forge parity
