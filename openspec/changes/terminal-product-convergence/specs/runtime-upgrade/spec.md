## ADDED Requirements

### Requirement: Supported native lifecycles are behaviorally symmetric

macOS, Linux, and Windows SHALL expose the same public install, status, doctor,
reload, rollback, recover, upgrade, and uninstall semantics while native adapters
own only their operating-system service operations. Each platform SHALL prove
the complete lifecycle using its own released artifact; a container, mock,
source execution, cross-compilation, or another operating system SHALL NOT
substitute for native product evidence.

#### Scenario: A supported platform accepts a release

- **WHEN** its signed native artifact is installed into an isolated user context
- **THEN** install, health, active-target no-op, upgrade, rollback, recovery,
  re-upgrade, uninstall, and reinstall reach their declared terminal states
- **AND** teardown leaves no owned service, process, transaction, payload,
  command, temporary carrier, or host-configuration residue.

### Requirement: Legacy lifecycle state has no implicit compatibility authority

An installed payload, journal, launcher, supervisor, manifest, command, or
schema shape that cannot satisfy the current exact ownership and transition
contract SHALL be rejected before mutation. After the terminal lifecycle has
no consumer for an earlier shape, its reader, writer, fallback, migration
bypass, and tests SHALL be deleted.

#### Scenario: A legacy carrier is encountered

- **WHEN** current code cannot prove its exact ownership and safe transition
- **THEN** the public command reports the bounded removal or reinstall action
- **AND** no compatibility inference or permissive fallback mutates it.
