## MODIFIED Requirements

### Requirement: Dual-Forge releases project one complete signed bundle

The admitted native builder for each supported platform SHALL produce that
platform's asset pair. The release owner SHALL admit those assets into exactly
one complete release-bundle identity and sign it once. Each selected Forge
SHALL publish and re-download the exact same files, and dual-Forge parity SHALL
require equal complete inventories, bytes, checksum manifest, signature, and
trust-anchor digest. Provider adapters SHALL only transport and verify the
bundle. Release-source verification SHALL inspect the annotated tag and its
target without changing the caller's symbolic ref, `HEAD`, index, or worktree.

#### Scenario: Physical build execution

- **WHEN** native assets are built on different platform executors or one
  executor is hosted by a selected Forge
- **THEN** runner placement SHALL NOT make that Forge a product authority
- **AND** no Forge publication adapter SHALL build, repackage, or sign assets.

#### Scenario: Complete parity

- **WHEN** GitLab and GitHub both publish a release tag
- **THEN** each release SHALL contain every archive and manifest named by the
  supported platform SSOT plus `SHA256SUMS` and `SHA256SUMS.sig`
- **AND** every corresponding byte digest SHALL be identical
- **AND** both releases SHALL report the same product trust-anchor digest.

#### Scenario: Provider publishes the canonical bundle

- **WHEN** a provider adapter publishes a release
- **THEN** it SHALL consume the canonical pre-signed bundle without rebuilding
  or re-signing any file
- **AND** the re-downloaded result SHALL match that bundle byte for byte.

#### Scenario: Release source is verified

- **WHEN** publication verifies an annotated release tag against an expected
  commit in an attached branch checkout
- **THEN** the tag object and dereferenced commit SHALL be validated exactly
- **AND** the symbolic ref, `HEAD`, index, and worktree SHALL remain unchanged.

#### Scenario: Release source identity differs

- **WHEN** the tag is absent, is not annotated, or resolves to a commit other
  than the expected commit
- **THEN** publication SHALL fail closed before provider I/O
- **AND** the caller checkout SHALL remain unchanged.

#### Scenario: Incomplete or independently signed projection

- **WHEN** either Forge omits a platform, changes any file, regenerates a
  different checksum inventory, re-signs with a different identity, or reports
  a different trust anchor
- **THEN** publication parity SHALL fail closed
- **AND** the incomplete release SHALL NOT be installation authority.

#### Scenario: Optional peer unavailable

- **WHEN** one Forge is unavailable
- **THEN** the other Forge MAY publish the unchanged complete bundle
- **AND** the result SHALL be reported as one-sided publication rather than
  dual-Forge parity.
