## MODIFIED Requirements

### Requirement: Release signing preserves provider-owned key security

Release signing MUST use a complete caller-provided private-key file without
copying it, MUST normalize a missing terminal newline only on POSIX, and MUST
leave Windows ACL ownership to the secret provider.

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
