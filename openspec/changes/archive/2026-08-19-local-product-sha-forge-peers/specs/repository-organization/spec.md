## MODIFIED Requirements

### Requirement: Portable repository quality surface

Repository tooling SHALL represent Forge publication as exact projection of
existing local Git objects. Provider-specific history reconstruction, identity
rewriting, continuity maps, and replay receipts SHALL NOT remain as parallel
publication authorities.

#### Scenario: A maintainer traces branch publication

- **WHEN** the selected Forge branch is advanced
- **THEN** one projector verifies the local object and exact remote CAS coordinate
- **AND** pushes that object without creating another commit
- **AND** no history-mapping module or compatibility flag is consulted.
