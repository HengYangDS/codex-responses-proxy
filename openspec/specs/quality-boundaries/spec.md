# quality-boundaries Specification

## Purpose
TBD - created by archiving change quality-boundary-tightening. Update Purpose after archive.
## Requirements
### Requirement: One structural quality boundary

Every tracked Python module and function in the repository's configured source,
tool, and test roots MUST use the same effective-line, function-size, and
control-nesting limits declared in the architecture policy. The active hard floors are 600 effective lines or statements per module, 110 effective lines per function, and eight control-nesting levels.

#### Scenario: A large test module is rejected

- **WHEN** a test module exceeds the declared effective-line or statement limit
- **THEN** the repository quality command reports a deterministic gap
- **AND** no test-only exception or ratchet is accepted.

#### Scenario: A test owner exceeds function or nesting limits

- **WHEN** a test function exceeds the declared function limit or nesting depth
- **THEN** the quality command rejects the repository
- **AND** pytest remains the only behavior test runner.
