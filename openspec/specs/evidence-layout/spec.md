# Evidence layout Specification

## Purpose

Define the positive durable evidence taxonomy and preserve one semantic owner
for independent Forge comparison.
## Requirements
### Requirement: Durable evidence families have one positive taxonomy

The evidence policy SHALL declare every durable evidence family and its precise
meaning in one machine-readable collection. The evidence-layout specification
SHALL explain that contract without becoming a second executable configuration
format. Repository quality SHALL report any physical top-level evidence
directory that has no declared family.

#### Scenario: Declared families are present

- **WHEN** repository quality inspects `evidence/`
- **THEN** it classifies each directory using the evidence policy
- **AND** no Markdown-fence parser or second implementation allowlist is used.

#### Scenario: An unknown family is present

- **WHEN** a physical top-level evidence directory has no policy entry
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
