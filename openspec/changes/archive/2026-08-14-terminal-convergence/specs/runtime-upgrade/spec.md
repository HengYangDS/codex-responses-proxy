## MODIFIED Requirements

### Requirement: Rollback owns only current product files

Rollback SHALL snapshot the complete current owned inventory or its complete
absence. Unknown install content SHALL be preserved and SHALL never become
implicitly owned. Candidate paths that collide with unknown content SHALL block
mutation. When an upgrade fails after projecting candidate bytes, rollback
SHALL restore every retained prior byte and remove every verified candidate
file that was absent from the prior snapshot.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned bundle byte and mode is restored
- **AND** unknown content remains unchanged.

#### Scenario: Candidate adds a new frozen-runtime member

- **WHEN** an upgrade projects a verified candidate-only file below `bin/`
- **AND** handoff fails and rollback runs
- **THEN** the candidate-only file is removed
- **AND** every prior owned byte and mode is restored exactly
- **AND** content outside prior-owned and candidate inventories is unchanged.

#### Scenario: Candidate collides with unknown content

- **WHEN** a candidate path already contains content outside the current owned inventory
- **THEN** the upgrade blocks before payload mutation
- **AND** rollback never claims ownership of that content.
