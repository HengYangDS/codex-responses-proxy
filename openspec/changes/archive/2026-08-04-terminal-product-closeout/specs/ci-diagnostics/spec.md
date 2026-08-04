## ADDED Requirements

### Requirement: One locked verification projection

Local verification, GitLab CI, and GitHub Actions SHALL invoke the same small
session graph backed by the committed dependency lock. Provider files MUST NOT
duplicate tool versions, interpreter loops, coverage policy, or quality command
sequences.

#### Scenario: Verification metadata drifts

- **WHEN** project metadata, the dependency lock, session graph, or a Forge
  projection disagree
- **THEN** a fast contract gate fails before behavior, coverage, packaging, or
  publication work begins.

### Requirement: Strict coverage and pristine success output

The complete supported behavior suite SHALL maintain statement coverage and
branch coverage each strictly greater than 95 percent. Passing tests, quality
gates, builds, and expected operational-failure checks MUST emit no unexpected
warning, traceback, error banner, skipped required test, or false completion
message.

#### Scenario: A green job is reported

- **WHEN** a local or hosted full gate exits successfully
- **THEN** both coverage measures exceed 95 percent and every required check ran
- **AND** the success log contains one concise receipt rather than traceback,
  warning, or a full coverage table.

### Requirement: Native executable acceptance

Each supported operating-system release SHALL be built and smoke-tested on
that operating system. Cross-compilation or another platform's result MUST NOT
be treated as native runtime evidence.

#### Scenario: A platform asset is published

- **WHEN** a release archive for a supported OS and architecture is admitted
- **THEN** its executable passed black-box help, version, status, manifest, and
  service-start checks in a pristine native environment
- **AND** Python was absent from the product execution path.
