# Runtime Upgrade

## Purpose

Define the released-payload identity and recovery invariants for source-side
protocol-v2 upgrades.
## Requirements
### Requirement: Source-side upgrade authority

Released-payload mutation SHALL remain owned by the source-side installer after
publication and signed-source admission; installed control must not accept an
arbitrary upgrade payload.

#### Scenario: Different release requested

- **WHEN** an operator needs to install payload bytes from a different release
- **THEN** the operation runs through the source-side installer and its release
  transaction rather than installed control

### Requirement: Recovery binds the live prior runtime

The installer SHALL restore a retained rollback snapshot only while the live
accepting listener matches that snapshot's release, serving digest, receipt
digest, manifest digest, and idle handoff state, and is the sole PID bound to
the installed entrypoint.

#### Scenario: Runtime and rollback agree

- **WHEN** the canonical recovery journal, rollback bytes, and live prior
  listener identities agree
- **THEN** the prior projection is restored and the retained transaction is
  removed before a new release transaction begins

#### Scenario: Runtime and rollback disagree

- **WHEN** any bound runtime identity differs or cannot be read
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
Source-side recovery SHALL restore only the exact rollback snapshot retained by
a canonical `recovery_required` transaction while the accepting listener still
matches that prior projection's release, serving digest, receipt digest,
manifest digest, and idle handoff state, and is the sole PID bound to the
installed entrypoint. It SHALL remove that transaction only
after restoration succeeds; the newer release then starts a fresh,
publication-gated transaction.

#### Scenario: Recoverable committed transaction
- **WHEN** one canonical recovery journal, intact rollback snapshot, and matching
  accepting prior listener are present
- **THEN** recovery restores the prior owned projection, removes transaction
  residue, and leaves successor installation to a new admitted transaction

#### Scenario: Ambiguous recovery state
- **WHEN** any recovery identity, rollback proof, or listener identity is missing
  or mismatched
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
