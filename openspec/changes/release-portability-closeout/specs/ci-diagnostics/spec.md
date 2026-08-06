## ADDED Requirements

### Requirement: Hosted verification uses portable product semantics
Hosted verification SHALL test repository and runtime semantics without relying
on host-specific filesystem permission projection, optional process utilities,
or controller connection lifetime. Successful jobs MUST be free of expected
package-install warnings.

#### Scenario: Windows verifies an executable Git hook
- **WHEN** a hosted Windows checkout verifies the tracked pre-commit hook
- **THEN** it SHALL inspect the Git index mode as `100755`
- **AND** it SHALL NOT infer executable intent from the Windows filesystem mode.

#### Scenario: A prepared controller disconnects
- **WHEN** the listener has validated a successor and reached READY
- **AND** the requesting controller disconnects while the acknowledgement is written
- **THEN** the listener-owned commit transaction SHALL still start exactly once
- **AND** the successor SHALL either finalize or expose a bounded rollback.

#### Scenario: Locked dependencies cross Windows filesystems
- **WHEN** CI installs locked dependencies on a host whose cache and environment
  are on different filesystems
- **THEN** installation SHALL use explicit copy mode
- **AND** successful output SHALL contain no hardlink fallback warning.
