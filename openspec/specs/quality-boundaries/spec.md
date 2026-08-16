# quality-boundaries Specification

## Purpose

Define the repository's positive semantic ownership, dependency direction, and
portable verification boundary without turning descriptive source metrics into
arbitrary merge vetoes.
## Requirements
### Requirement: One structural quality boundary

Every enforced rule SHALL have one semantic owner and a proportionate evidence
model. A quantitative merge veto SHALL state its risk model, exact measurement,
false-positive cost, remediation path, and review condition. Aggregate and
semantic-package coverage own the current product-risk boundary; file-sized
coverage remains diagnostic evidence. A tool-native collection configuration
SHALL NOT duplicate the canonical policy floor.

#### Scenario: a small module has a volatile ratio

- **WHEN** its semantic package and the product aggregate satisfy the canonical coverage policy
- **THEN** the file ratio remains diagnostic
- **AND** promotion is decided by the declared product-risk scopes.

#### Scenario: A contributor reviews a large owner

- **WHEN** a production, test, or tool owner has high source-size or nesting observations
- **THEN** the repository quality command reports the measurements with the exact path
- **AND** semantic ownership, behavior, dependency direction, and review evidence determine whether refactoring is required.

#### Scenario: An undeclared package appears

- **WHEN** a package is added outside the positive package topology
- **THEN** the quality command rejects it as an undeclared semantic owner
- **AND** no parallel forbidden-name list is consulted.

#### Scenario: A contributor locates behavior

- **WHEN** a contributor follows a public command or runtime behavior
- **THEN** its implementation, tests, specification, and documentation point to one semantic owner
- **AND** no compatibility module or duplicated policy must be consulted.

#### Scenario: Coverage evidence is evaluated

- **WHEN** one small module has a volatile ratio but its semantic package and the product aggregate satisfy the canonical coverage policy
- **THEN** the file ratio remains diagnostic evidence
- **AND** no duplicate threshold in a tool-native formatting file can change the verdict.

#### Scenario: a policy changes

- **WHEN** maintainers revise a quantitative boundary
- **THEN** they update its single machine owner and recorded rationale
- **AND** repository tests reject any competing threshold source.
