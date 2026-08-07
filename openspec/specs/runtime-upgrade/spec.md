# Runtime Upgrade

## Purpose

Define the current native payload, transactional handoff, rollback, recovery,
and supervision invariants.
## Requirements
### Requirement: Source-side upgrade authority

Only the signed-asset installer SHALL admit a different release. Installed
control SHALL observe, reload, recover, or remove the current product but SHALL
NOT accept arbitrary release bytes. Forge availability SHALL NOT be an
installation input.

#### Scenario: An operator installs a release

- **WHEN** one signed native archive and its external trust anchor are supplied
- **THEN** the installer verifies and applies the release locally
- **AND** a Forge, Git, Python, uv, Nox, ETHOS, a client control plane, and a source checkout
  are not runtime dependencies.

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one native executable, `providers.toml`,
their manifest, signed-release receipt, and finalized state. Installation SHALL
accept only an empty target or one verified current native listener.

#### Scenario: An incompatible installation is present

- **WHEN** its manifest or executable does not match the current payload shape
- **THEN** installation fails before mutation with one bounded removal action
- **AND** no inventory reader, interpreter entrypoint, or bypass switch admits it.

### Requirement: Upgrade uses the current native handoff protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted candidate, and request
transactional handoff. A successor SHALL prove its PID, executable, release,
manifest, serving aggregate, receipt, accepting state, and non-draining state.

#### Scenario: A current release upgrades successfully

- **WHEN** the sole verified listener supports handoff and the successor proves
  the admitted identity
- **THEN** the transaction finalizes without replacing native supervision
- **AND** at most one listener accepts requests at each barrier.

#### Scenario: Handoff rolls back

- **WHEN** failure resolution proves the original runtime resumed
- **THEN** the exact rollback snapshot is restored and the operation fails.

#### Scenario: Handoff outcome is unknown

- **WHEN** neither finalization nor rollback can be proved
- **THEN** candidate and rollback bytes remain transaction-bound for recovery
- **AND** no success or rollback claim is emitted.

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

### Requirement: Rollback owns only current product files

Rollback SHALL snapshot the current owned inventory or its complete absence.
Unknown install content SHALL be preserved and SHALL never become implicitly
owned. Candidate paths that collide with unknown content SHALL block mutation.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned byte and mode is restored
- **AND** unknown content remains unchanged.

### Requirement: Payload primitives have one semantic owner

Canonical paths and safe file I/O SHALL belong to `owned_files`; candidate
materialization to `candidate`; installed integrity and purge to `projection`;
rollback to `rollback`; journals to `state`; and orchestration to `transaction`.
No forwarding facade or private-name import SHALL create a second authority.
The four transaction roles SHALL remain separate concrete modules rather than
being folded into the orchestrator or projected through a compatibility facade.

#### Scenario: A transaction mutates the payload

- **WHEN** it validates, snapshots, writes, verifies, restores, or finalizes
- **THEN** it calls the defining semantic owner directly.

### Requirement: Listener configuration has one source

The runtime configuration owner SHALL define the default listener port and all
validated overrides. Installer, control, service, and uninstall code SHALL not
copy port, host, log, or concurrency policy.

#### Scenario: A port override is supplied

- **WHEN** an operator selects a valid port through the public CLI
- **THEN** installation, supervision, health, reload, and uninstall use that
  exact value consistently.

### Requirement: Native supervision is self-contained and portable

The released executable SHALL install and inspect its user service through the
native macOS, Linux, or Windows adapter without an ambient Python interpreter,
optional process utility, source path, user identity, or workstation-specific
coordinate. Signal paths SHALL revalidate exact process identity immediately
before mutation.

#### Scenario: A supported host lacks development tools

- **WHEN** the product is installed on a clean supported host
- **THEN** service installation, listener discovery, handoff, status, and
  uninstall remain available from the released executable alone.

### Requirement: Uninstall removes only proved product ownership

Uninstall SHALL remove native supervision and exact owned listener processes.
`--purge` SHALL additionally require a valid current manifest, remove only its
owned files, preserve unknown content, and fail nonzero if residue remains.

#### Scenario: Unknown content shares the install directory

- **WHEN** purge removes every manifest-owned file
- **THEN** unknown content remains untouched
- **AND** the command reports that the directory is not fully purged.

