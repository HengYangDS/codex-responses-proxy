## MODIFIED Requirements

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
