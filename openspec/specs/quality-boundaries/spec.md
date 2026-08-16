# quality-boundaries Specification

## Purpose

Define the repository's positive semantic ownership, dependency direction, and
portable verification boundary without turning descriptive source metrics into
arbitrary merge vetoes.
## Requirements
### Requirement: One structural quality boundary

Source, tests, tools, documentation, configuration, and release assets SHALL
follow one explicit semantic owner and dependency direction. The repository
quality command SHALL report source size and nesting as descriptive review
evidence. Those observations SHALL NOT become merge vetoes without an
independently justified risk model, exact measurement semantics,
false-positive cost, remediation path, and review trigger. The positive package
topology SHALL be the only package-admission authority.

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
