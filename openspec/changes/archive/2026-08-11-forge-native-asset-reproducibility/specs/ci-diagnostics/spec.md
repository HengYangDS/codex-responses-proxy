## ADDED Requirements

### Requirement: Forge release projections use one exact common runtime

The repository SHALL define one immutable runtime identity for every native
asset built on more than one Forge, while each Forge remains an independent
builder and publisher.

#### Scenario: Independent Linux builders select the release runtime

- **WHEN** GitLab and GitHub build the Linux release asset
- **THEN** both use the repository-owned image digest and architecture
- **AND** both materialize the release commit at the same canonical build root
- **AND** neither builder consumes artifacts or state from the other Forge

### Requirement: Native release payloads are reproducible

Native release payloads SHALL contain only runtime-required bytes and portable
metadata.

#### Scenario: Equivalent source is built from distinct checkout roots

- **WHEN** the same release commit is built twice in the declared runtime
- **THEN** the resulting common-platform archives are byte-identical
- **AND** no checkout path, installer timestamp, or runner-private metadata is present

#### Scenario: A builder drifts from the declared runtime

- **WHEN** a build uses a different image, Python patch release, or toolchain
- **THEN** release verification fails before publication
