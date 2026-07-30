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
