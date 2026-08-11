## MODIFIED Requirements

### Requirement: Release signing uses one provider-owned key path

Release signing MUST use a complete caller-provided private-key file without
copying it. It MAY create one process-scoped private copy only to restore a
missing terminal newline on POSIX, and MUST leave Windows ACL ownership to the
secret provider.

#### Scenario: A Forge signs release assets

- **WHEN** GitHub or GitLab assembles one release asset set
- **THEN** the protected environment supplies an existing private-key path
- **AND** repository code preserves a complete key's path and security metadata
- **AND** OpenSSH signs and independently verifies the checksum inventory.

#### Scenario: The signing input is unsafe

- **WHEN** the path is absent, a symbolic link, or the trust input is empty
- **THEN** release assembly fails closed before publication.

#### Scenario: The provider supplies a complete key

- **WHEN** the private-key file ends with a terminal newline
- **THEN** OpenSSH receives that exact file path
- **AND** no temporary private-key copy is created.

#### Scenario: A POSIX file variable omits its terminal newline

- **WHEN** a valid POSIX private-key file lacks its terminal newline
- **THEN** signing uses one process-scoped `0600` normalized copy
- **AND** removes the copy after signing.

#### Scenario: Windows input is incomplete

- **WHEN** a Windows private-key file lacks its terminal newline
- **THEN** the signer does not copy or rewrite the file
- **AND** OpenSSH rejects invalid input through the concise signing diagnostic.
