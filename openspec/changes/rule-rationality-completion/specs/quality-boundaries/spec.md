## MODIFIED Requirements

### Requirement: One structural quality boundary

Every enforced rule SHALL have one semantic owner and a proportionate evidence
model. A blocking rule SHALL state its risk model, exact measurement,
false-positive cost, remediation path, and review condition. Aggregate coverage
owns the quantitative product-risk boundary. Every semantic package SHALL have
current non-zero execution evidence and an exact diagnostic ratio; package- and
file-sized percentages SHALL NOT act as independent vetoes. The architecture gate owns the declared
product package, semantic package set, dependency direction, root-module
boundary, package declarations, and acyclic dependency graph. It SHALL NOT
encode authors, hosts, foreign product names, private-symbol syntax, aliases, or
historical implementation shapes as generic merge blacklists. Portability SHALL
be demonstrated by native execution, package isolation, explicit configuration
ownership, and platform-specific behavior tests rather than whole-text literal
scans. Tool-native
configuration SHALL NOT duplicate a canonical policy decision.
Release and documentation validation SHALL verify semantic identities, links,
and behavior rather than requiring an exact explanatory sentence.

#### Scenario: a small semantic package has a volatile ratio

- **WHEN** it has current execution evidence and the product aggregate satisfies the canonical coverage policy
- **THEN** its exact ratio remains diagnostic
- **AND** promotion is decided by aggregate product risk and package observation.

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

#### Scenario: documentation wording improves

- **WHEN** README prose changes without changing product identity, links, or release behavior
- **THEN** quality and release admission SHALL evaluate those semantic contracts
- **AND** no exact prose fragment SHALL act as a merge or publication veto.
