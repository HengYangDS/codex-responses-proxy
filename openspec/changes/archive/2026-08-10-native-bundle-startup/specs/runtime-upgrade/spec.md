## MODIFIED Requirements

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one prewarmed native bundle under `bin/`,
`providers.toml`, their complete manifest, signed-release receipt, and finalized
state. Installation SHALL accept only an empty target or one verified current
native listener.

#### Scenario: An incompatible installation is present

- **WHEN** its manifest, bundle inventory, or executable does not match the
  current payload shape
- **THEN** installation fails before mutation with one bounded removal action
- **AND** no legacy inventory reader, one-file entrypoint, interpreter entrypoint,
  or bypass switch admits it.

#### Scenario: A candidate bundle is admitted

- **WHEN** signed release verification has produced the complete candidate
  inventory
- **THEN** every regular file and mode is verified in staging
- **AND** the staged executable completes a bounded prewarm probe
- **AND** only then may the payload transaction replace installed bytes.

### Requirement: Upgrade uses the current native handoff protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and request
transactional handoff. A successor SHALL prove its PID, executable, release,
manifest, serving aggregate, receipt, accepting state, and non-draining state.

#### Scenario: A current release upgrades successfully

- **WHEN** the sole verified listener supports handoff and the successor proves
  the admitted identity
- **THEN** the transaction finalizes without replacing native supervision
- **AND** startup performs no first-run bundle extraction
- **AND** at most one listener accepts requests at each barrier.

#### Scenario: Handoff rolls back

- **WHEN** failure resolution proves the original runtime resumed
- **THEN** the exact complete rollback inventory is restored
- **AND** the operation fails.

#### Scenario: Handoff outcome is unknown

- **WHEN** neither finalization nor rollback can be proved
- **THEN** candidate and rollback bundle bytes remain transaction-bound for
  recovery
- **AND** no success or rollback claim is emitted.

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL require one canonical journal, a fully verified current
candidate bundle, a fully verified current rollback bundle, and matching
accepting runtime identity.

#### Scenario: All identities agree

- **WHEN** release, complete file inventory, serving digest, receipt, manifest
  digest, transaction, and runtime state match
- **THEN** recovery restores the exact prior payload and clears the hold.

#### Scenario: Any identity differs

- **WHEN** a required byte, path, mode, digest, PID, state, or journal field
  differs
- **THEN** recovery fails closed without changing the payload or journal.

### Requirement: Rollback owns only current product files

Rollback SHALL snapshot the complete current owned inventory or its complete
absence. Unknown install content SHALL be preserved and SHALL never become
implicitly owned. Candidate paths that collide with unknown content SHALL block
mutation.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned bundle byte and mode is restored
- **AND** unknown content remains unchanged.
