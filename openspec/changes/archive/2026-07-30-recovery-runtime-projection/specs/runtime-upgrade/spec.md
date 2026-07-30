# Runtime Upgrade Delta

## MODIFIED Requirements

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
