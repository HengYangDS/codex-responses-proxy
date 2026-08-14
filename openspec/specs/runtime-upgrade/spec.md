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
mutation. When an upgrade fails after projecting candidate bytes, rollback
SHALL restore every retained prior byte and remove every verified candidate
file that was absent from the prior snapshot.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned bundle byte and mode is restored
- **AND** unknown content remains unchanged.

#### Scenario: Candidate adds a new frozen-runtime member

- **WHEN** an upgrade projects a verified candidate-only file below `bin/`
- **AND** handoff fails and rollback runs
- **THEN** the candidate-only file is removed
- **AND** every prior owned byte and mode is restored exactly
- **AND** content outside prior-owned and candidate inventories is unchanged.

#### Scenario: Candidate collides with unknown content

- **WHEN** a candidate path already contains content outside the current owned inventory
- **THEN** the upgrade blocks before payload mutation
- **AND** rollback never claims ownership of that content.

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
