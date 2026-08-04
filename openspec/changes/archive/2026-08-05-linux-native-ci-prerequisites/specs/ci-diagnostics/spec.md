## MODIFIED Requirements

### Requirement: Native executable acceptance

Each supported operating-system release SHALL be built and smoke-tested on
that operating system. Cross-compilation or another platform's result MUST NOT
be treated as native runtime evidence. A hosted projection based on a minimal
operating-system image SHALL explicitly install the native inspection tools
required by the repository-owned executable build and MUST NOT rely on an
untracked runner image layer.

#### Scenario: A platform asset is published

- **WHEN** a release archive for a supported OS and architecture is admitted
- **THEN** its executable passed black-box help, version, status, manifest, and
  service-start checks in a pristine native environment
- **AND** Python was absent from the product execution path.

#### Scenario: Minimal Linux verifies the native executable

- **WHEN** a hosted Linux matrix or quality job starts from its declared
  minimal base image
- **THEN** the provider projection installs the operating-system tools required
  by the repository-owned native executable gate
- **AND** every supported Python line executes that gate without depending on
  private runner image state
- **AND** a contract test rejects omission of the declared prerequisite.
