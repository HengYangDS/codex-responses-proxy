## MODIFIED Requirements

### Requirement: Native release payloads are reproducible

Native release payloads SHALL contain only runtime-required bytes and portable
metadata. The release build SHALL remove installer-local metadata and repair
its inventory before native executable freezing. Every platform built by both
Forge planes from the same accepted source and locked toolchain SHALL publish
byte-identical archives, manifests, and checksum entries.

#### Scenario: Equivalent source is built from distinct checkout roots

- **WHEN** the same release commit is installed and built twice in the declared
  runtime with different checkout paths or installer timestamps
- **THEN** the frozen executable inputs and resulting common-platform archives
  are byte-identical
- **AND** no checkout path, installer timestamp, installer cache record, or
  runner-private metadata is present.

#### Scenario: Independently published common assets are compared

- **WHEN** GitLab and GitHub finish publishing the same release version
- **THEN** a read-only audit downloads each common-platform asset and its
  manifest from both independent Forge planes
- **AND** their SHA-256 digests are equal before installation is accepted.

#### Scenario: A builder drifts from the declared runtime

- **WHEN** a build uses a different image, Python patch release, toolchain, or
  non-normalized installed distribution
- **THEN** release verification fails before publication.
