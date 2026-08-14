# quality-boundaries Specification

## Purpose
TBD - created by archiving change quality-boundary-tightening. Update Purpose after archive.
## Requirements
### Requirement: One structural quality boundary

Source, tests, tools, documentation, configuration, and release assets SHALL
follow one explicit semantic owner and dependency direction. Every tracked Python
module and function in the configured source, tool, and test roots MUST use the
same effective-line, function-size, and control-nesting limits declared in the
architecture policy. Cross-package private imports, forwarding facades,
concatenated semantic package names, compatibility modules, duplicated policy,
and root-level script sprawl SHALL NOT create parallel authority.

#### Scenario: A large test module is rejected

- **WHEN** a test module exceeds the declared effective-line or statement limit
- **THEN** the repository quality command reports a deterministic gap
- **AND** no test-only exception or ratchet is accepted.

#### Scenario: A test owner exceeds function or nesting limits

- **WHEN** a test function exceeds the declared function limit or nesting depth
- **THEN** the quality command rejects the repository
- **AND** pytest remains the only behavior test runner.

#### Scenario: A contributor locates behavior

- **WHEN** a contributor follows a public command or runtime behavior
- **THEN** its implementation, tests, specification, and documentation point to one semantic owner
- **AND** no compatibility module or duplicated policy must be consulted.
