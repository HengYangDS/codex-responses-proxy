## MODIFIED Requirements

### Requirement: Durable evidence roots have one project meaning

The evidence-layout specification SHALL state its current project-owned purpose
directly and SHALL NOT retain generated placeholder text. Claims and chronicles
SHALL remain the only durable evidence roots until another family is deliberately
specified and gated.

#### Scenario: An unowned evidence root is introduced

- **WHEN** a tracked or physical top-level directory appears below `evidence/`
  without an admitted project meaning
- **THEN** the repository quality command reports that directory
- **AND** the change cannot pass quality proof.

#### Scenario: Canonical evidence documentation is verified

- **WHEN** repository quality reads the canonical evidence-layout specification
- **THEN** its purpose SHALL describe durable evidence ownership directly
- **AND** no generated placeholder SHALL remain.
