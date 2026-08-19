## MODIFIED Requirements

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one prewarmed native bundle under `bin/`,
`providers.toml`, their complete manifest, signed-release receipt, and finalized
state. Installation SHALL accept an empty target, one verified current native
listener, or one current native payload whose sole listener and native
supervisor are strictly proved to use an install-owned alternate launcher. The
alternate launcher SHALL be reconciled to the canonical native executable
before candidate payload mutation and SHALL NOT remain as a compatibility
surface.

#### Scenario: An incompatible installation is present

- **WHEN** its manifest, bundle inventory, executable, listener identity,
  supervisor declaration, or alternate launcher ownership does not match an
  admitted shape
- **THEN** installation fails before mutation with one bounded removal action
- **AND** no legacy inventory reader, one-file entrypoint, interpreter
  entrypoint, external launcher, or bypass switch admits it.

#### Scenario: A candidate bundle is admitted

- **WHEN** signed release verification has produced the complete candidate
  inventory
- **THEN** every regular file and mode is verified in staging
- **AND** the staged executable completes a bounded prewarm probe
- **AND** any admitted alternate launcher has already converged onto native
  supervision
- **AND** only then may the payload transaction replace installed bytes.

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL distinguish an unmutated `prepared` transaction from a
`recovery_required` payload transition. A prepared transaction SHALL be closed
only when its canonical journal is the sole transaction-root entry. Recovery of
a mutated projection SHALL require one canonical journal, a fully verified
current candidate bundle, a fully verified current rollback bundle, and matching
accepting runtime identity.

#### Scenario: A prepared transaction contains only its canonical journal

- **WHEN** admission completed but payload mutation never began
- **THEN** recovery removes the transaction root without changing payload,
  command, listener, or supervision
- **AND** reports the transaction as closed.

#### Scenario: A prepared transaction contains additional content

- **WHEN** any file, directory, link, or ambiguous journal field exists beyond
  the canonical prepared journal
- **THEN** recovery fails closed and preserves the complete transaction root.

#### Scenario: All identities agree

- **WHEN** release, complete file inventory, serving digest, receipt, manifest
  digest, transaction, and runtime state match
- **THEN** recovery restores the exact prior payload and clears the hold.

#### Scenario: Any identity differs

- **WHEN** a required byte, path, mode, digest, PID, state, or journal field
  differs
- **THEN** recovery fails closed without changing the payload or journal.

## ADDED Requirements

### Requirement: Supervisor reconciliation precedes payload mutation

Installation SHALL converge a verified native listener and its native
supervisor onto the canonical installed executable before committing candidate
payload bytes. On POSIX hosts, reconciliation MAY admit the known
install-owned alternate launcher and SHALL use the existing transactional
handoff protocol, retain the exact alternate launcher until native supervision
is proved, and remain retryable after controller interruption. Windows SHALL
retain its canonical native lifecycle and reject the POSIX-only alternate
launcher shape before mutation.

#### Scenario: An install-owned alternate launcher is active on a POSIX host

- **WHEN** the current payload identity, sole listener PID, process generation,
  supervisor declaration, and alternate launcher path all agree
- **THEN** installation atomically bridges that launcher to the canonical native
  executable
- **AND** protocol-v2 handoff starts and proves the canonical native listener
- **AND** the supervisor is rebound before the bridge and retained original are
  removed.

#### Scenario: An alternate launcher is presented on Windows

- **WHEN** installation observes a noncanonical launcher on Windows
- **THEN** it rejects that launcher before service or payload mutation
- **AND** the canonical Windows native install, reload, status, doctor, and
  uninstall lifecycle remains unchanged.

#### Scenario: Reconciliation fails before native handoff

- **WHEN** handoff cannot prove the canonical native successor
- **THEN** the exact alternate launcher is restored
- **AND** no candidate payload mutation begins.

#### Scenario: The native listener committed before controller interruption

- **WHEN** a retry observes the canonical native listener and the supervisor
  still declares the exact retained bridge
- **THEN** installation proves the same listener identity, rebinds the
  supervisor, and removes the bridge residue
- **AND** candidate payload mutation begins only after that convergence.
