## ADDED Requirements

### Requirement: Successful upgrade retains one exact predecessor

A successful upgrade SHALL retain exactly one verified predecessor generation
after the successor has proved accepting runtime identity. The retained
generation SHALL contain the complete predecessor payload, installed state,
command projection, and the exact successor identity for which that
predecessor is valid. A subsequent successful upgrade SHALL atomically replace
the older retained predecessor. Fresh installation SHALL retain none.

#### Scenario: Upgrade finalizes successfully

- **WHEN** the successor payload, command, native supervisor, and listener have
  proved the committed successor identity
- **THEN** finalization promotes the transaction's verified predecessor into
  the sole retained rollback generation
- **AND** removes the active transaction without copying live successor bytes
  into that generation.

#### Scenario: Finalization is interrupted between promotion phases

- **WHEN** finalization stops after the predecessor generation is materialized
  or after its selector is committed
- **THEN** the active transaction remains the sole recovery authority
- **AND** retry advances the same generation to the terminal selected state
- **AND** the previously selected generation is not removed before the new
  selector is durable.

#### Scenario: A second upgrade succeeds

- **WHEN** an installation with a retained predecessor upgrades again
- **THEN** the newly displaced release becomes the sole retained predecessor
- **AND** no older rollback history remains.

#### Scenario: The retained-generation transition is introduced

- **WHEN** the published predecessor predates retained-generation finalization
- **THEN** the verified successor executable drives that one upgrade
- **AND** establishes the current carrier without synthesizing historical state
- **AND** later adjacent upgrades return to installed-release ownership.

### Requirement: Explicit rollback is one reverse lifecycle transaction

Explicit rollback SHALL restore only the retained predecessor bound to the
current finalized successor. It SHALL verify current payload and installed
state, retained payload and command snapshots, and their generation binding
before mutation. It SHALL rebind the native service and complete a bounded
listener handoff to the predecessor identity before reporting success.

#### Scenario: Exact predecessor rollback succeeds

- **WHEN** the current successor and retained predecessor both verify and the
  predecessor proves accepting listener identity
- **THEN** rollback reports state `rolled_back`
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

### Requirement: Repeated lifecycle transitions use declared runtime capability

The deployment controller SHALL select one strategy from verified runtime
identity and explicit handoff capability. An idle runtime or a finalized
runtime declaring `repeatable` MAY use shared-listener handoff. A complete,
verified finalized runtime without that capability SHALL use a bounded native
process-generation replacement. An incomplete or inconsistent runtime SHALL be
unsupported and SHALL NOT be mutated.

#### Scenario: Runtime declares repeatable handoff

- **WHEN** a finalized runtime projects the `repeatable` handoff capability
- **THEN** the next upgrade or rollback may use the shared-listener handoff
- **AND** successor acceptance still requires the exact payload and process
  identity.

#### Scenario: Verified predecessor lacks repeatable handoff

- **WHEN** a finalized published predecessor has complete identity but does not
  declare the `repeatable` capability
- **THEN** deployment captures its exact listener process generation before
  writing candidate state
- **AND** rebinds native supervision, retires only that generation, and proves
  one successor listener within the configured bound
- **AND** preserves the transaction for recovery if predecessor exit is not
  proved.

#### Scenario: Native-generation successor does not become ready

- **WHEN** the bounded replacement cannot prove the successor listener
- **THEN** deployment restores the predecessor payload and service projection
- **AND** reports no successful upgrade or rollback.

#### Scenario: Runtime identity is incomplete

- **WHEN** listener, payload, protocol, transaction, or process identity is
  absent or inconsistent
- **THEN** no handoff or native-generation replacement is attempted
- **AND** the operator receives one precise incompatibility result.
