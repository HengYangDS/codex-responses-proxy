## MODIFIED Requirements

### Requirement: Rollback converges on an explicit verified release

The rollback command SHALL require one syntactically valid target release. If
the installed active release already equals that target, rollback SHALL succeed
as an idempotent no-op without draining, starting a transaction, changing the
generation selection, or rewriting the command. If the target equals the sole
verified retained predecessor, rollback SHALL use the existing transactional
native lifecycle to select it. Every other target SHALL be rejected before any
lifecycle mutation.

#### Scenario: Requested release is already active

- **WHEN** rollback names the exact installed active release
- **THEN** it reports an unchanged terminal state
- **AND** performs no drain, handoff, transaction, selection, command, service,
  listener, or payload mutation.

#### Scenario: Requested release is the verified predecessor

- **WHEN** rollback names the sole retained predecessor release
- **THEN** it restores that release through the verified transactional lifecycle
- **AND** reports the actual source and target releases.

#### Scenario: Requested release is not admissible

- **WHEN** rollback names neither the installed active release nor the verified
  retained predecessor
- **THEN** it fails before drain or mutation
- **AND** preserves the selected payload, command, listener, service, retained
  predecessor, and transaction state.

#### Scenario: Required target is omitted or malformed

- **WHEN** the caller omits `--to-release` or supplies an invalid release value
- **THEN** command parsing or the existing strict version authority rejects the
  request before lifecycle mutation.

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL distinguish no transaction, an unmutated `prepared`
transaction, a `recovery_required` payload transition, and an invalid retained
transaction. No transaction SHALL be an idempotent successful no-op. A prepared
transaction SHALL be closed only when its canonical journal is the sole
transaction-root entry. Recovery of a selected mutated projection SHALL require
one canonical journal, a fully verified current candidate bundle, the exact
rollback command snapshot, and matching accepting runtime identity.

When a materialized reverse candidate was never selected, recovery SHALL prove
that the current generation selection is exactly the pre-transaction selection,
the installed state is bound to that active generation and release, the command
is owned by that generation's executable, the immutable payload identity is
valid, and the accepting non-draining runtime matches that payload. Only then
may it close the transaction without reading an unused rollback snapshot. It
SHALL preserve the selected payload, command, listener, and service. Any missing
proof or any other selection SHALL fail closed without mutation. Journal-only
closure SHALL remove only a transaction root whose canonical journal is its sole
entry. Lifecycle writers are serialized before transaction inspection or
mutation; processes that bypass the product-owned lifecycle boundary are outside
the supported concurrency contract.

Any existing but unverifiable transaction carrier SHALL fail closed without
mutation and identify whether the transaction root or journal is missing, a
symbolic link, the wrong filesystem type, malformed JSON, non-canonical JSON,
an unsupported schema, or invalid under the current schema.

The public recovery result SHALL be exactly one of `not_required`, `closed`,
`finalized`, or `rolled_back`. `finalized` requires the accepting runtime to
match the committed candidate's release, serving payload, release receipt, and
manifest identities. `rolled_back` requires either the retained rollback
identity or exact proof that the prior selected generation remained terminal;
neither outcome may be inferred from process presence alone.

#### Scenario: No transaction exists

- **WHEN** the exact transaction root is absent
- **THEN** recovery succeeds with state `not_required`
- **AND** changes no payload, command, listener, service, or filesystem entry.

#### Scenario: A prepared transaction contains only its canonical journal

- **WHEN** admission completed but payload mutation never began
- **THEN** recovery removes the transaction root without changing payload,
  command, listener, or supervision
- **AND** reports the transaction as closed.

#### Scenario: A prepared transaction contains additional content

- **WHEN** any file, directory, link, or ambiguous journal field exists beyond
  the canonical prepared journal
- **THEN** recovery fails closed and preserves the complete transaction root.

#### Scenario: An unselected reverse candidate has no rollback snapshot

- **WHEN** a materialized reverse candidate was never selected
- **AND** selection, installed state, command ownership, immutable payload, and
  accepting runtime all prove the prior terminal generation
- **THEN** recovery closes the orphaned transaction without reading a rollback
  command snapshot
- **AND** preserves the selected payload, command, listener, and service.

#### Scenario: The unselected reverse candidate cannot prove terminal state

- **WHEN** selection, installed state, command ownership, immutable payload, or
  accepting runtime differs from the prior terminal generation
- **THEN** recovery fails closed without removing the candidate or transaction
- **AND** does not read absence of a snapshot as permission to invent state.

#### Scenario: Another lifecycle writer is active

- **WHEN** install, recover, reload, rollback, or uninstall already owns the
  product lifecycle mutation boundary
- **THEN** another lifecycle mutation is rejected before reading or changing
  transaction state
- **AND** status and doctor remain available as read-only observations.

#### Scenario: All identities agree

- **WHEN** release, complete file inventory, serving digest, receipt, manifest
  digest, transaction, and runtime state match the selected candidate
- **THEN** recovery finalizes or restores the exact prior payload as required
- **AND** clears the hold only after terminal binding succeeds.

#### Scenario: Any identity differs

- **WHEN** a required byte, path, mode, digest, PID, state, or journal field
  differs
- **THEN** recovery fails closed without changing the payload or journal.

#### Scenario: The transaction carrier is invalid

- **WHEN** recovery observes a symbolic-link or non-directory transaction root,
  a missing or symbolic-link journal, malformed or non-canonical JSON, an
  unsupported schema, or invalid current-schema fields
- **THEN** recovery fails before any lifecycle mutation
- **AND** identifies the exact failed invariant
- **AND** leaves all retained files and the independently serving runtime
  unchanged.
