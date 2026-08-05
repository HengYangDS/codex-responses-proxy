## ADDED Requirements

### Requirement: Host-independent semantic-package coverage

Every hosted quality target MUST prove every semantic package has statement and
branch coverage strictly greater than 95 percent without relying on the runner
host to select a required platform branch.

#### Scenario: Linux proves the Darwin state-root branch

- **WHEN** the quality inventory runs on Linux
- **THEN** a portable test explicitly selects the Darwin state-root semantics
- **AND** the `relay` package branch ratio remains strictly greater than 95
  percent
- **AND** no production conditional, exclusion, or CI-only bypass is added.
