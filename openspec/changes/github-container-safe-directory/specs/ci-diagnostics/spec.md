## MODIFIED Requirements

### Requirement: Forge jobs are portable projections

Hosted jobs SHALL use supported native shells and filesystem semantics, install
their explicit operating-system prerequisites, and reach a terminal result on
an admitted project runner. A reused self-hosted checkout SHALL preserve Git
diagnostic integrity without changing runner-global configuration. A container
whose user does not own the GitHub checkout SHALL grant Git trust only to the
exact workflow workspace for the one archive command.

#### Scenario: Windows verifies the product

- **WHEN** the Windows matrix executes
- **THEN** it uses native PowerShell and Git index metadata for executable intent
- **AND** POSIX-only shell fixtures are excluded without disabling Windows
  product behavior.

#### Scenario: Linux builds an x86_64 asset on an ARM host

- **WHEN** the Docker executor runs on ARM
- **THEN** the release job explicitly selects an amd64 container
- **AND** packaging fails unless the container reports an x86_64-compatible
  machine.

#### Scenario: A required runner is unavailable

- **WHEN** Forge admission cannot match every job to an allowed runner
- **THEN** publication is blocked before a pipeline is treated as accepted
- **AND** a pending job is not reported as verification success.

#### Scenario: A GitHub release container reads the checked-out tag

- **WHEN** the Linux container user does not own `GITHUB_WORKSPACE`
- **THEN** the archive command trusts that exact workspace for that invocation
- **AND** no global, repository-local, system, or wildcard safe-directory rule
  is created
- **AND** the canonical `/workspace` source materialization continues.
