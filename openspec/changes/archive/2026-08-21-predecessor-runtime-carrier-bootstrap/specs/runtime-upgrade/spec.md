## MODIFIED Requirements

### Requirement: Upgrade uses the current native handoff protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and bind
native supervision to that committed executable before requesting transactional
handoff. A successor SHALL prove its PID, executable, release, manifest,
serving aggregate, receipt, accepting state, and non-draining state. The
handoff child SHALL own only listener transfer and runtime identity; it SHALL
NOT mutate the platform-native supervisor. When an admitted published
predecessor predates the sole runtime carrier, only the successor handoff child
MAY atomically materialize that missing carrier before activation. It SHALL use
either one complete predecessor runtime environment or platform defaults and
SHALL reject partial predecessor settings. Listener and watchdog startup SHALL
NOT materialize a missing carrier.

#### Scenario: A published predecessor drives the upgrade

- **WHEN** the admitted predecessor projects a successor payload without the
  successor runtime carrier
- **THEN** the successor handoff child atomically creates the carrier from the
  complete inherited contract or platform defaults
- **AND** activates that carrier before protocol startup
- **AND** the upgrade continues through exact successor identity proof.

#### Scenario: Predecessor runtime settings are partial

- **WHEN** some but not all product runtime settings are inherited and the
  carrier is absent
- **THEN** handoff-child startup fails before listener transfer
- **AND** no mixed predecessor/default contract is persisted.

#### Scenario: Another private role lacks the carrier

- **WHEN** listener or watchdog startup cannot read the sole runtime carrier
- **THEN** it fails closed
- **AND** does not synthesize a parallel runtime authority.

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
