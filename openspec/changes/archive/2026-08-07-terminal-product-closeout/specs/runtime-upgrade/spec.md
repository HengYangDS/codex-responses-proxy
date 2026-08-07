## MODIFIED Requirements

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one native executable, `providers.toml`,
their manifest, signed-release receipt, and finalized state. Installation SHALL
accept only an empty target or one verified current native listener.

#### Scenario: An incompatible installation is present

- **WHEN** its manifest or executable does not match the current payload shape
- **THEN** installation fails before mutation with one bounded removal action
- **AND** no inventory reader, interpreter entrypoint, or bypass switch admits it.

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL require one canonical journal, a fully verified current
candidate, a fully verified current rollback payload, and matching accepting
runtime identity.

#### Scenario: All identities agree

- **WHEN** release, serving digest, receipt, manifest digest, transaction, and
  runtime state match
- **THEN** recovery restores the exact prior payload and clears the hold.

#### Scenario: Any identity differs

- **WHEN** a required byte, digest, PID, state, or journal field differs
- **THEN** recovery fails closed without changing the payload or journal.
