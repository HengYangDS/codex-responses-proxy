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
