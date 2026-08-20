## MODIFIED Requirements

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one prewarmed native bundle under `bin/`,
`providers.toml`, their complete manifest, signed-release receipt, and finalized
state. Installation SHALL accept an empty target, one verified current native
listener, or one current native payload whose sole listener and native
supervisor are strictly proved to use an install-owned alternate launcher. The
alternate launcher SHALL be reconciled to the canonical native executable
before candidate payload mutation and SHALL NOT remain as a compatibility
surface. After candidate projection, installation SHALL remove only regular
files declared by the verified predecessor manifest and absent from the
successor manifest. Unknown installation content SHALL remain untouched, and
rollback SHALL restore the complete predecessor projection.

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

#### Scenario: The successor omits a predecessor-owned file

- **WHEN** the verified predecessor manifest owns a regular file that the
  verified successor manifest does not declare
- **THEN** installation removes that file after writing the successor
  projection
- **AND** preserves every unowned file
- **AND** rollback restores the removed predecessor-owned file exactly.

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

#### Scenario: A verified alternate launcher is reconciled before upgrade

- **WHEN** the current native listener and install-owned alternate launcher
  satisfy the admitted identity contract on a POSIX host
- **THEN** the supervisor is rebound to the canonical executable before the
  candidate payload is committed
- **AND** the retained launcher is removed only after successor health is
  proved.

### Requirement: Upgrade converges the native supervisor generation

After candidate payload commitment and before listener handoff, installation
SHALL restart the platform-native supervisor from the canonical committed
executable. A watchdog that starts a listener SHALL retain and poll its process
handle so an exited child is reaped. If the subsequent handoff rolls back,
installation SHALL restart native supervision from the restored predecessor
payload before returning failure.

#### Scenario: A current native runtime is upgraded

- **WHEN** candidate bytes have committed and the current listener remains
  accepting
- **THEN** the native supervisor is restarted from the candidate executable
- **AND** listener handoff begins only after the supervisor declaration is
  rebound to that executable.

#### Scenario: A watchdog-owned listener exits

- **WHEN** a listener spawned by the resident watchdog reaches a terminal
  process state
- **THEN** the watchdog polls its retained process handle
- **AND** no zombie process remains owned by that watchdog.

#### Scenario: Handoff rolls back after supervisor replacement

- **WHEN** successor handoff fails with a proved rollback outcome
- **THEN** the predecessor payload is restored
- **AND** native supervision is restarted from that restored payload.

### Requirement: Handoff finalization observes the exact successor

After commit, the controller SHALL read bounded health snapshots through the
shared listener until the complete expected successor identity is served. A
snapshot from the retiring process SHALL be treated as transient observation,
not success or immediate failure. Timeout or another failure SHALL identify the
failed lifecycle phase without including exception messages, request content,
headers, credentials, or upstream payloads.

#### Scenario: The retiring listener answers during ownership transfer

- **WHEN** the first post-commit health snapshot still identifies the retiring
  process
- **THEN** the controller continues bounded observation
- **AND** finalizes only after the exact successor PID and payload identity are
  accepting and not draining.

#### Scenario: Successor observation does not converge

- **WHEN** the deadline expires or health observation fails
- **THEN** the transaction follows its rollback or recovery-required contract
- **AND** operational output records only the failed phase and exception class.

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
