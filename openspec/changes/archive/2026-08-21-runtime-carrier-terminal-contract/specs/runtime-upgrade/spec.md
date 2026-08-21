## ADDED Requirements

### Requirement: Carrier-bound native handoff is the only upgrade protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and bind
native supervision to that committed executable before requesting transactional
handoff. A successor SHALL prove its PID, executable, release, manifest,
serving aggregate, receipt, accepting state, and non-draining state. The
handoff child SHALL own only listener transfer and runtime identity; it SHALL
NOT mutate the platform-native supervisor. Every private service role SHALL
activate one existing, validated `runtime-config.json` located in the installed
executable's payload root before importing or starting product runtime behavior.
Environment variables are a projection of that carrier, not an alternate source
and not an input from which a missing carrier may be created.

#### Scenario: Every private role activates the same carrier

- **WHEN** the listener, handoff child, or watchdog starts from an admitted
  installed executable
- **THEN** it resolves the carrier from that executable
- **AND** validates the carrier before product startup
- **AND** replaces inherited product settings with the carrier projection.

#### Scenario: A private role lacks a valid carrier

- **WHEN** any private role cannot read one valid executable-owned carrier
- **THEN** startup fails closed before listener, handoff, or watchdog behavior
  begins
- **AND** no private role creates a carrier from inherited environment variables
  or platform defaults.

#### Scenario: A current release upgrades successfully

- **WHEN** the sole verified listener supports handoff and the successor proves
  the admitted identity
- **THEN** installation writes the successor carrier and binds native
  supervision to the committed successor before requesting listener handoff
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

## REMOVED Requirements

### Requirement: Upgrade uses the current native handoff protocol

**Reason**: The requirement mixed the terminal handoff contract with three
release-scoped scenarios for a predecessor that lacked `runtime-config.json`.
The formal `2.0.52 → 2.0.55` migration has completed, so those scenarios have no
remaining product consumer and would preserve obsolete compatibility semantics.

**Migration**: Use `2.0.55` as the explicit bridge for any installation older
than the carrier contract. Current and future releases use the carrier-bound
native handoff requirement above; direct upgrade from a pre-carrier release is
not a supported terminal path.
