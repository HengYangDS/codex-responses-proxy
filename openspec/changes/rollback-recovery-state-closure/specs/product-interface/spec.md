## MODIFIED Requirements

### Requirement: Small public lifecycle grammar

The installed executable SHALL expose only the end-user lifecycle commands
`install`, `status`, `doctor`, `reload`, `rollback`, `recover`, and `uninstall`.
`rollback` SHALL require one exact release and converge on it only when it is
already active or is the sole verified retained predecessor. `recover` SHALL
resolve only an interrupted or indeterminate installation transaction.
Source-side release admission and publication SHALL remain outside the
installed command grammar.

#### Scenario: Public help is rendered

- **WHEN** the operator runs `codex-responses-proxy --help`
- **THEN** exactly the supported lifecycle commands are presented
- **AND** rollback and recovery are separately discoverable
- **AND** their descriptions distinguish explicit release selection from
  interrupted-transaction recovery
- **AND** Python module commands, internal service entrypoints, and aliases are
  absent.

#### Scenario: No predecessor is retained

- **WHEN** the operator requests an exact release that is not active after a
  fresh installation or before any successful upgrade
- **THEN** the command reports state `unavailable` without mutation
- **AND** Human and JSON output explain that no verified predecessor exists.

### Requirement: Explicit rollback has one public result model

The installed executable SHALL project one semantic rollback result to concise
human output by default and stable JSON when `--json` is requested. An
already-active requested release, rollback unavailability, invalid evidence,
indeterminate recovery-required state, and completed rollback SHALL be distinct
outcomes. Expected failures SHALL contain one precise problem and one safe next
command without a traceback or warning.

#### Scenario: Automation requests rollback

- **WHEN** automation invokes `rollback --to-release <exact-version> --json`
- **THEN** it receives exactly one JSON result with a stable `state`
  discriminator
- **AND** the Human projection renders the same requested release and action
  semantics without exposing private carrier paths.

#### Scenario: The requested release is already active

- **WHEN** rollback proves that the requested release is the active installed,
  selected, projected, and accepting runtime
- **THEN** it reports state `unchanged`
- **AND** performs no drain, handoff, transaction, selection, command, service,
  listener, or payload mutation.

#### Scenario: Retained predecessor evidence is invalid

- **WHEN** rollback evidence is missing a required file, contains a symbolic
  link, has an unsupported schema, fails a digest, or does not bind the current
  installed successor
- **THEN** rollback fails closed with a stable error code and read-only next
  action
- **AND** it does not mutate the payload, command, service, listener, or
  retained bytes.
