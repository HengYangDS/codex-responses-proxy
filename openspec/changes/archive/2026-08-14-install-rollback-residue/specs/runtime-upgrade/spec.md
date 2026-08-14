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

- **WHEN** an upgrade projects a candidate-only file below `bin/`
- **AND** the handoff fails and rollback runs
- **THEN** the candidate-only file is absent
- **AND** the previous manifest, receipt, installed state, executable, and provider manifest are restored exactly
- **AND** content outside the prior-owned and candidate inventories remains unchanged

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `runtime-upgrade:Rollback owns only current product files` | `1.2` | `tests/lifecycle/test_transaction.py::test_upgrade_rollback_removes_candidate_only_runtime_members` |
