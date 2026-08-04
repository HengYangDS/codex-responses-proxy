## ADDED Requirements

### Requirement: Executable-bound transactional lifecycle

Install, upgrade, reload, rollback, and uninstall SHALL bind identity to the
exact installed executable, provider manifest, release manifest, service, and
owned files. A Python interpreter path, package module, or source checkout MUST
NOT be part of the public or persistent service contract.

#### Scenario: A verified release replaces a running release

- **WHEN** the new executable and manifest pass admission
- **THEN** a non-accepting successor proves executable, release, manifest,
  listener, and health identity before commit
- **AND** failure restores the exact verified predecessor without two accepting
  listeners.

### Requirement: One direct predecessor migration

An upgrade SHALL recognize only the immediately preceding supported installed
schema and inventory. Release versions SHALL be data read from manifests, not
version-shaped program symbols or a general historical compatibility registry.

#### Scenario: An unsupported historical payload is present

- **WHEN** installation finds an owned payload other than the exact supported
  predecessor or current schema
- **THEN** mutation is refused with a bounded diagnostic
- **AND** no force option bypasses payload, process, or identity proof.

### Requirement: Runtime independence from development and governance systems

Installed operation MUST NOT call Git, a Forge, uv, Nox, ETHOS, Workstation
Control Plane, AIGW, or a source-checkout tool. It may use only installed owned
state, the provider manifest, request-supplied credentials, and platform-native
supervision.

#### Scenario: Development systems are absent

- **WHEN** the source repository and contributor environment are unavailable
- **THEN** service start, status, doctor, reload, and uninstall continue from
  installed product state
- **AND** no external product lifecycle or configuration implementation is
  imported or invoked.
