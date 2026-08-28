## ADDED Requirements

### Requirement: Native supervision projects the terminal generation

After listener handoff proves the terminal admission owner, installation SHALL
replace the platform-native supervisor with one running watchdog generation
executing that exact payload. Product runtime identity SHALL be reconstructed
from the committed, secret-free `runtime-config.json`; operating-system service
definitions SHALL remain derived projections and SHALL NOT duplicate product
configuration. A watchdog that starts a listener SHALL retain and poll its
process handle so an exited child is reaped. The transaction SHALL remain the
recovery authority until the configured and running supervisor identity is
proved. If handoff rolls back, installation SHALL restore the predecessor
payload and prove native supervision from that payload before closing the
transaction.

On macOS, installation SHALL bind the exact GUI-domain service, prove any
predecessor watchdog PID has exited, bootstrap the current plist, and re-read
the exact successor PID. Plist registration, executable-path equality, or a
successful platform command alone SHALL NOT establish convergence.

#### Scenario: One runtime carrier projects to native service managers

- **WHEN** a committed payload is installed on macOS, Linux, or Windows
- **THEN** the watchdog and native-service adapter reconstruct the same exact
  executable, installation root, log root, and service identity from
  `runtime-config.json`
- **AND** launchd, systemd user services, or Task Scheduler contain only the
  native invocation and service-manager metadata
- **AND** no platform definition becomes a second product configuration source.

#### Scenario: An installed macOS watchdog is replaced during upgrade

- **WHEN** candidate payload bytes have committed while an earlier watchdog
  generation is registered
- **THEN** after listener handoff proves the terminal admission owner, the
  installer boots out the exact prior launchd service
- **AND** proves the predecessor PID is absent within a bounded deadline
- **AND** bootstraps the current plist into the exact GUI domain
- **AND** accepts only a distinct running PID returned and re-observed for the
  exact service label
- **AND** leaves the independent terminal listener serving throughout
  replacement.

#### Scenario: A current native runtime is upgraded

- **WHEN** the candidate listener has proved accepting terminal ownership
- **THEN** the native supervisor is replaced by a generation executing the
  candidate payload
- **AND** the transaction closes only after the exact service registration,
  executable, and running generation are proved.

#### Scenario: A watchdog-owned listener exits

- **WHEN** a listener spawned by the resident watchdog reaches a terminal
  process state
- **THEN** the watchdog polls its retained process handle
- **AND** no zombie process remains owned by that watchdog.

#### Scenario: Handoff rolls back before supervisor replacement

- **WHEN** successor handoff fails with a proved rollback outcome
- **THEN** the predecessor payload is restored
- **AND** native supervision is proved to execute that restored payload before
  the transaction closes.

#### Scenario: Launchd cannot prove generation replacement

- **WHEN** bootout, predecessor exit, bootstrap, kickstart, or successor PID
  observation fails or is ambiguous
- **THEN** installation fails with an actionable lifecycle error
- **AND** does not report native supervision as converged.

#### Scenario: An isolated native lifecycle ends

- **WHEN** a noncanonical installation succeeds, fails, times out, or raises
- **THEN** teardown removes the exact service registration and projection path
  used at creation
- **AND** proves every process owned by that exact service has exited
- **AND** leaves the canonical service and listener unchanged
- **AND** the set of noncanonical host service projections has no net growth.

### Requirement: Transactional handoff is the sole generation transition

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and request
transactional handoff before changing native supervision. A successor SHALL
prove its PID, executable, release, manifest,
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
- **THEN** installation writes the successor carrier and requests listener
  handoff without replacing the predecessor supervisor
- **AND** after the successor owns admission, native supervision is rebound to
  that exact successor and its configured and running executable identity is
  proved
- **AND** the handoff child does not restart or replace its own supervisor
- **AND** startup performs no first-run bundle extraction
- **AND** at most one listener accepts requests at each barrier.

#### Scenario: Supervisor rebinding fails after successful handoff

- **WHEN** the platform-native supervisor cannot be proved to declare the
  committed successor
- **THEN** the successor remains the sole serving generation
- **AND** the payload transaction remains recoverable
- **AND** no finalized claim is emitted.

#### Scenario: Handoff rolls back

- **WHEN** failure resolution proves the original runtime resumed
- **THEN** the exact complete rollback inventory is restored
- **AND** native supervision is rebound to the restored predecessor
- **AND** the transaction closes only after that supervisor identity is proved
- **AND** the operation fails.

#### Scenario: Handoff outcome is unknown

- **WHEN** neither finalization nor rollback can be proved
- **THEN** candidate and rollback bundle bytes remain transaction-bound for
  recovery
- **AND** native supervision is not treated as lifecycle authority
- **AND** no success or rollback claim is emitted.

## REMOVED Requirements

### Requirement: Upgrade converges the native supervisor generation

After candidate payload commitment and before listener handoff, installation
SHALL replace the platform-native supervisor with one running watchdog
generation executing the canonical committed payload. Product runtime identity
SHALL be reconstructed from the committed, secret-free `runtime-config.json`;
operating-system service definitions SHALL remain derived projections and SHALL
NOT duplicate product configuration. A watchdog that starts a listener SHALL
retain and poll its process handle so an exited child is reaped. If subsequent
handoff rolls back, installation SHALL restore the predecessor payload and
replace native supervision from that payload before returning failure.

On macOS, installation SHALL bind the exact GUI-domain service, prove any
predecessor watchdog PID has exited, bootstrap the current plist, and re-read
the exact successor PID. Plist registration, executable-path equality, or a
successful platform command alone SHALL NOT establish convergence.

#### Scenario: One runtime carrier projects to native service managers

- **WHEN** a committed payload is installed on macOS, Linux, or Windows
- **THEN** the watchdog and native-service adapter reconstruct the same exact
  executable, installation root, log root, and service identity from
  `runtime-config.json`
- **AND** launchd, systemd user services, or Task Scheduler contain only the
  native invocation and service-manager metadata
- **AND** no platform definition becomes a second product configuration source.

#### Scenario: An installed macOS watchdog is replaced during upgrade

- **WHEN** candidate payload bytes have committed while an earlier watchdog
  generation is registered
- **THEN** the installer boots out the exact prior launchd service
- **AND** proves the predecessor PID is absent within a bounded deadline
- **AND** bootstraps the current plist into the exact GUI domain
- **AND** accepts only a distinct running PID returned and re-observed for the
  exact service label
- **AND** leaves the independent listener serving throughout replacement.

#### Scenario: A current native runtime is upgraded

- **WHEN** candidate bytes have committed and the current listener remains
  accepting
- **THEN** the native supervisor is replaced by a generation executing the
  candidate payload
- **AND** listener handoff begins only after the exact service registration,
  executable, and running generation are proved.

#### Scenario: A watchdog-owned listener exits

- **WHEN** a listener spawned by the resident watchdog reaches a terminal
  process state
- **THEN** the watchdog polls its retained process handle
- **AND** no zombie process remains owned by that watchdog.

#### Scenario: Handoff rolls back after supervisor replacement

- **WHEN** successor handoff fails with a proved rollback outcome
- **THEN** the predecessor payload is restored
- **AND** native supervision is replaced by a generation executing that restored
  payload.

#### Scenario: Launchd cannot prove generation replacement

- **WHEN** bootout, predecessor exit, bootstrap, kickstart, or successor PID
  observation fails or is ambiguous
- **THEN** installation fails with an actionable lifecycle error
- **AND** does not report native supervision as converged.

#### Scenario: An isolated native lifecycle ends

- **WHEN** a noncanonical installation succeeds, fails, times out, or raises
- **THEN** teardown removes the exact service registration and projection path
  used at creation
- **AND** proves every process owned by that exact service has exited
- **AND** leaves the canonical service and listener unchanged
- **AND** the set of noncanonical host service projections has no net growth.

**Reason**: The requirement encoded supervisor replacement before terminal listener ownership, creating a competing lifecycle authority.

**Migration**: Use the replacement requirements in this change; no compatibility path is retained.

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

**Reason**: The requirement encoded supervisor replacement before terminal listener ownership, creating a competing lifecycle authority.

**Migration**: Use the replacement requirements in this change; no compatibility path is retained.
