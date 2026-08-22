## MODIFIED Requirements

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL distinguish no transaction, an unmutated `prepared`
transaction, a `recovery_required` payload transition, and an invalid retained
transaction. No transaction SHALL be an idempotent successful no-op. A prepared
transaction SHALL be closed only when its canonical journal is the sole
transaction-root entry. Recovery of a mutated projection SHALL require one
canonical journal, a fully verified current candidate bundle, a fully verified
current rollback bundle, and matching accepting runtime identity. Any existing
but unverifiable transaction carrier SHALL fail closed without mutation.

The public recovery result SHALL be exactly one of `not_required`, `closed`,
`finalized`, or `rolled_back`. `finalized` requires the accepting runtime to
match the committed candidate's release, serving payload, release receipt, and
manifest identities. `rolled_back` requires the retained rollback identity;
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

#### Scenario: All identities agree

- **WHEN** release, complete file inventory, serving digest, receipt, manifest
  digest, transaction, and runtime state match
- **THEN** recovery restores the exact prior payload and clears the hold.

#### Scenario: Any identity differs

- **WHEN** a required byte, path, mode, digest, PID, state, or journal field
  differs
- **THEN** recovery fails closed without changing the payload or journal.

### Requirement: Uninstall removes only proved product ownership

Uninstall SHALL remove only the exact service, processes, command projection,
and manifest-owned payload associated with the selected installation. An
absent installation SHALL be an idempotent successful no-op. An existing
payload root without valid ownership evidence SHALL be preserved and purge
SHALL fail closed.

#### Scenario: No installation exists

- **WHEN** no owned service, listener, command projection, payload root, or
  installed-state record exists
- **THEN** uninstall succeeds with state `not_installed`
- **AND** `--purge` has the same result without creating or deleting content.

#### Scenario: Unverified content occupies the payload root

- **WHEN** purge observes an existing payload root without a valid ownership
  manifest
- **THEN** it exits nonzero with a precise ownership diagnostic
- **AND** preserves every byte.

#### Scenario: Unknown content shares the install directory

- **WHEN** purge removes every manifest-owned file
- **THEN** unknown content remains untouched
- **AND** the command reports that the directory is not fully purged.

#### Scenario: The installed command link remains product-owned

- **WHEN** uninstall has proved service and process absence
- **AND** the command link still targets the exact installed executable
- **THEN** the command link is removed
- **AND** the payload is preserved unless `--purge` is requested.

#### Scenario: The command path changed ownership

- **WHEN** uninstall observes a foreign file, directory, or link at the command
  path
- **THEN** the path is preserved
- **AND** uninstall reports the ownership conflict without claiming complete
  removal.
