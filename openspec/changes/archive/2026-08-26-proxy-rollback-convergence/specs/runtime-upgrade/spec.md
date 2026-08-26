## MODIFIED Requirements

### Requirement: Explicit rollback is one reverse lifecycle transaction

Explicit rollback SHALL restore only the retained predecessor bound to the
current finalized successor. It SHALL verify current payload and installed
state, retained payload and command snapshots, and their generation binding
before mutation. It SHALL rebind the native service and complete a bounded
listener handoff to the predecessor identity before reporting success. The
returned predecessor PID SHALL be the only verified product listener when
success is reported; finalized health alone SHALL NOT establish completion.

#### Scenario: Exact predecessor rollback succeeds

- **WHEN** the current successor and retained predecessor both verify and the
  predecessor proves accepting, finalized runtime identity
- **THEN** rollback reports state `rolled_back` only after the predecessor PID
  is the sole verified product listener
- **AND** payload, installed state, command projection, service definition, and
  listener all identify the predecessor
- **AND** the displaced successor becomes the one retained predecessor for a
  possible forward reversal.

#### Scenario: Retained evidence is absent

- **WHEN** no retained predecessor exists
- **THEN** rollback reports state `unavailable`
- **AND** changes no filesystem, process, service, command, or listener state.

#### Scenario: Retained evidence is unverifiable

- **WHEN** any carrier shape, byte, mode, digest, generation binding, current
  installed identity, service identity, or listener identity cannot be proved
- **THEN** rollback fails closed before mutation
- **AND** preserves current and retained generations for inspection.

#### Scenario: Finalized health precedes listener convergence

- **WHEN** the predecessor reports finalized health while the displaced
  successor remains a verified listener
- **THEN** rollback continues bounded convergence and does not report success
- **AND** reports an indeterminate outcome if one sole predecessor listener
  cannot be proved within the bound.

#### Scenario: Reverse handoff has a proved failure

- **WHEN** rollback has projected the predecessor but successor retirement or
  predecessor readiness fails with a proved outcome
- **THEN** the transaction restores the displaced successor and its command and
  service projection
- **AND** does not report rollback success.

#### Scenario: Reverse handoff outcome is unknown

- **WHEN** neither predecessor finalization nor successor restoration can be
  proved
- **THEN** the active transaction is retained for `recover`
- **AND** no successful rollback or restoration claim is emitted.
