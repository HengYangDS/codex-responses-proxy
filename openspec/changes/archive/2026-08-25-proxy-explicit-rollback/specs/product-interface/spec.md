## MODIFIED Requirements

### Requirement: Small public lifecycle grammar

The installed executable SHALL expose only the end-user lifecycle commands
`install`, `status`, `doctor`, `reload`, `rollback`, `recover`, and `uninstall`.
`rollback` SHALL deliberately restore the one retained predecessor of the
current finalized installation. `recover` SHALL resolve only an interrupted or
indeterminate installation transaction. Source-side release admission and
publication SHALL remain outside the installed command grammar.

#### Scenario: Public help is rendered

- **WHEN** the operator runs `codex-responses-proxy --help`
- **THEN** exactly the supported lifecycle commands are presented
- **AND** rollback and recovery are separately discoverable
- **AND** their descriptions distinguish deliberate predecessor restoration
  from interrupted-transaction recovery
- **AND** Python module commands, internal service entrypoints, and aliases are
  absent.

#### Scenario: No predecessor is retained

- **WHEN** the operator runs `codex-responses-proxy rollback` after a fresh
  installation or before any successful upgrade
- **THEN** the command reports state `unavailable` without mutation
- **AND** Human and JSON output explain that no verified predecessor exists.

## ADDED Requirements

### Requirement: Explicit rollback has one public result model

The installed executable SHALL project one semantic rollback result to concise
human output by default and stable JSON when `--json` is requested. Rollback
unavailability, invalid evidence, indeterminate recovery-required state, and
completed rollback SHALL be distinct outcomes. Expected failures SHALL contain
one precise problem and one safe next command without a traceback or warning.

#### Scenario: Automation requests rollback

- **WHEN** automation invokes `rollback --json`
- **THEN** it receives exactly one JSON result with a stable `state`
  discriminator
- **AND** the Human projection renders the same predecessor, successor, and
  action semantics without exposing private carrier paths.

#### Scenario: Retained predecessor evidence is invalid

- **WHEN** rollback evidence is missing a required file, contains a symbolic
  link, has an unsupported schema, fails a digest, or does not bind the current
  installed successor
- **THEN** rollback fails closed with a stable error code and read-only next
  action
- **AND** it does not mutate the payload, command, service, listener, or
  retained bytes.
