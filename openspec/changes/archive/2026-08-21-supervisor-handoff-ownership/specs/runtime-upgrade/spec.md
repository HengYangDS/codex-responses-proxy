## MODIFIED Requirements

### Requirement: Upgrade uses the current native handoff protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and bind
native supervision to that committed executable before requesting transactional
handoff. A successor SHALL prove its PID, executable, release, manifest, serving
aggregate, receipt, accepting state, and non-draining state. The handoff child
SHALL own only listener transfer and runtime identity; it SHALL NOT mutate the
platform-native supervisor.

#### Scenario: A current release upgrades successfully

- **WHEN** the sole verified listener supports handoff and the successor proves
  the admitted identity
- **THEN** installation binds native supervision to the committed successor
  before requesting listener handoff
- **AND** the handoff child does not restart or replace its own supervisor
- **AND** startup performs no first-run bundle extraction
- **AND** at most one listener accepts requests at each barrier.

#### Scenario: Supervisor rebinding fails before handoff

- **WHEN** the platform-native supervisor cannot be proved to declare the
  committed successor
- **THEN** handoff is not requested
- **AND** the prior payload and native supervision are restored
- **AND** the operation fails.

#### Scenario: Handoff rolls back

- **WHEN** failure resolution proves the original runtime resumed
- **THEN** the exact complete rollback inventory is restored
- **AND** native supervision is rebound to the restored predecessor
- **AND** the operation fails.

#### Scenario: Handoff outcome is unknown

- **WHEN** neither finalization nor rollback can be proved
- **THEN** candidate and rollback bundle bytes remain transaction-bound for
  recovery
- **AND** native supervision remains bound to the committed candidate
- **AND** no success or rollback claim is emitted.
