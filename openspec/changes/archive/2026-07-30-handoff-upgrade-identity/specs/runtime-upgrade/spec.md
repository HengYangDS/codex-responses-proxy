## ADDED Requirements

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
