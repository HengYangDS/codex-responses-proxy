# Runtime Upgrade

## Purpose

Define the released-payload identity and recovery invariants for source-side
protocol-v2 upgrades.
## Requirements
### Requirement: Source-side upgrade authority

Released-payload mutation SHALL remain owned by the source-side installer after
signed-source admission; installed control must not accept an arbitrary upgrade
payload. Forge publication evidence SHALL NOT be an installation input.

#### Scenario: Different release requested

- **WHEN** an operator needs to install payload bytes from a different release
- **THEN** the operation runs through the source-side installer and its release
  transaction rather than installed control

#### Scenario: One signed release source selected

- **WHEN** an operator installs an exact signed release checkout under an
  external trust anchor
- **THEN** installation requires no GitLab, GitHub, hosted-CI, or release-record
  credential or coordinate

### Requirement: Recovery binds the live prior runtime

The installer SHALL restore a retained rollback snapshot only while the live
accepting listener's frozen release, serving digest, and receipt match that
snapshot; its reported manifest digest matches the fully verified candidate
projection committed on disk; and it is the sole idle PID bound to the installed
entrypoint.

#### Scenario: Runtime, rollback, and candidate agree

- **WHEN** the rollback bytes match the listener's frozen serving identity and
  the installed manifest matches the listener's reported manifest digest
- **THEN** the prior projection is restored and the retained transaction is
  removed before a new release transaction begins

#### Scenario: Either projection disagrees

- **WHEN** any bound runtime identity, candidate manifest identity, or unique
  process proof differs or cannot be read
- **THEN** recovery fails closed and retains the transaction

### Requirement: Cross-version successor identity
The listener SHALL validate a handoff request against the complete committed
successor payload on disk, independently of the old process's frozen runtime
identity.

#### Scenario: Valid cross-version upgrade
- **WHEN** a signed released payload with a new version is committed and its
  manifest, serving files, receipt, and requested identity agree
- **THEN** the old protocol-v2 listener prepares a child from that successor
  payload and permits the bounded handoff to continue

#### Scenario: Successor payload mismatch
- **WHEN** any requested successor field, manifest-owned file, or aggregate
  digest differs from the committed payload
- **THEN** preparation fails before the accept barrier and the old listener
  remains serving

### Requirement: Recovery rollback before a new installation

Source-side recovery SHALL validate the old listener's frozen serving identity
against the rollback snapshot and its reported manifest digest against the
fully verified candidate projection currently committed on disk. It SHALL then
restore the exact rollback snapshot only while that listener is the sole
accepting, idle process bound to the installed entrypoint.

#### Scenario: Old listener serves after candidate commit

- **WHEN** the listener reports the rollback release, serving digest, and
  receipt, while its manifest digest identifies the committed candidate
- **THEN** recovery accepts the two-projection identity and restores the exact
  rollback snapshot

#### Scenario: Either projection differs

- **WHEN** a runtime field differs from the rollback projection or the reported
  manifest differs from the committed candidate
- **THEN** recovery refuses without changing the transaction or installed files

#### Scenario: Recoverable committed transaction

- **WHEN** one canonical recovery journal, intact rollback snapshot, fully
  verified committed candidate, and matching accepting prior listener are present
- **THEN** recovery restores the prior owned projection, removes transaction
  residue, and leaves successor installation to a new admitted transaction

#### Scenario: Ambiguous recovery state

- **WHEN** either projection, rollback proof, or listener identity is missing or
  mismatched
- **THEN** recovery fails closed without removing the journal or claiming either
  rollback or installation success

### Requirement: Explicit protocol-v2 bootstrap
Source-side installation MAY interrupt an old protocol-v2 listener only under
explicit authorization after binding one idle accepting PID to the exact
installed entrypoint. Failure SHALL restore the prior payload and prove the
prior accepting runtime.

#### Scenario: Authorized replacement
- **WHEN** the old listener is exactly bound and the admitted successor becomes
  the sole accepting runtime
- **THEN** the new release transaction finalizes with successor identity proof

#### Scenario: Replacement fails
- **WHEN** termination, supervision replacement, or successor proof fails
- **THEN** the installer restores the prior projection and reports failure unless
  the prior accepting runtime is also proved

### Requirement: Installed payload operations have concrete module owners

Each installed-payload filesystem primitive SHALL have one public module owner.
Peer modules SHALL import that owner directly and SHALL NOT recover shared
behavior through another module's private names or forwarding aliases.

#### Scenario: A payload transaction reads or writes an owned file

- **WHEN** candidate construction, migration, rollback, state, or transaction code needs a canonical payload path, safe regular-file read, digest, or atomic write
- **THEN** it calls the public owned-file module directly
- **AND** projection remains responsible only for installed projection semantics
- **AND** transaction does not re-export peer behavior as a second authority.

### Requirement: Process-local behavior has concrete semantic owners

Admission and drain, telemetry, safe logging, and provider-neutral cooldown
SHALL be owned by separate concrete modules. Production callers SHALL import
the defining owner directly, and the retired mixed runtime state module SHALL
NOT remain as an implementation or compatibility facade.

#### Scenario: The listener handles a Responses request

- **WHEN** the listener admits, logs, records, or cooldown-checks the request
- **THEN** each operation is delegated to its concrete semantic owner
- **AND** no caller imports a mixed runtime state namespace.

### Requirement: Replay metrics are structured data

Replay normalization SHALL return immutable structured metrics with the
projected bytes and bounded rejection state. Telemetry SHALL consume numeric
fields directly and SHALL NOT parse diagnostic strings.

#### Scenario: Provider-bound replay data is removed

- **WHEN** replay removes response ids, reasoning items, encrypted blocks, or
  unreplayable local images
- **THEN** the result reports each aggregate as a typed field
- **AND** operational diagnostics are derived from that result without
  retaining removed content.

### Requirement: Dual-Forge history parity is identity-aware

Provider-native histories SHALL use the configured Forge author email and
trusted signature. Verification SHALL prove source-to-projection tree, message,
date, and parent-topology correspondence without claiming identical commit
object ids across different identities.

#### Scenario: GitHub publishes a GitLab-accepted source commit

- **WHEN** the required GitHub actor differs from the GitLab actor
- **THEN** publication creates or reuses the verified identity projection
- **AND** rejects destructive updates, ambiguous mappings, or tree/topology drift.

### Requirement: Loopback listener admission is DNS-independent

Fresh and handoff-adopted loopback listeners SHALL become serviceable without
forward, reverse, or FQDN resolution. Each listener SHALL derive its presented
host and port from the address bound by the kernel rather than from DNS.

#### Scenario: A fresh listener starts while DNS is unavailable

- **WHEN** the proxy constructs a fresh loopback listener and hostname resolution is unavailable or blocked
- **THEN** listener construction completes without consulting DNS
- **AND** the listener reports the actual bound loopback host and port
- **AND** it can proceed immediately to serve requests.

#### Scenario: A handed-off listener is adopted while DNS is unavailable

- **WHEN** an authorized runtime handoff supplies an already bound loopback socket and hostname resolution is unavailable or blocked
- **THEN** the successor adopts the socket without consulting DNS
- **AND** its reported host and port match the adopted socket's bound address.
