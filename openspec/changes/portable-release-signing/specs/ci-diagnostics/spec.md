## ADDED Requirements

### Requirement: Release signing uses one provider-owned key path

Release assembly SHALL accept one existing private-key file path supplied by
the publishing Forge and SHALL NOT accept or materialize private-key text.

#### Scenario: A Forge signs release assets

- **WHEN** GitHub or GitLab assembles one release asset set
- **THEN** the protected environment supplies an existing private-key path
- **AND** repository code does not copy the key or recreate its permissions
- **AND** OpenSSH signs and independently verifies the checksum inventory.

#### Scenario: The signing input is unsafe

- **WHEN** the path is absent, a symbolic link, or the trust input is empty
- **THEN** release assembly fails closed before publication.
