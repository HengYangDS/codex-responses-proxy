## MODIFIED Requirements

### Requirement: Durable evidence families have one positive taxonomy

The evidence-layout specification SHALL declare every durable evidence family,
its project meaning, and its physical root in one machine-readable taxonomy.
The repository quality gate SHALL consume that taxonomy and SHALL report any
physical top-level evidence directory that has no declared family.

#### Scenario: Declared families are present

- **WHEN** repository quality inspects `evidence/`
- **THEN** `claims` is classified as bounded machine-verifiable assertions
- **AND** `chronicle` is classified as human-readable historical execution context
- **AND** no second implementation allowlist is consulted.

#### Scenario: An unknown family is present

- **WHEN** a physical top-level evidence directory has no taxonomy entry
- **THEN** repository quality reports the unknown directory
- **AND** quality proof cannot pass.

### Requirement: Forge comparison has one semantic owner

Cross-Forge source and release comparison SHALL remain a transient publication
audit owned by the Forge audit command. It SHALL become durable evidence only
through an explicitly admitted evidence family.

#### Scenario: Forge state is compared

- **WHEN** GitLab and GitHub publication state is audited
- **THEN** the Forge audit command produces the comparison result
- **AND** the durable evidence taxonomy remains unchanged.
