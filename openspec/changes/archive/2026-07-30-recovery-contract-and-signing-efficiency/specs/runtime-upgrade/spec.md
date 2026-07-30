# Runtime Upgrade Delta

## MODIFIED Requirements

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
