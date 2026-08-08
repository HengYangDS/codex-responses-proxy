## ADDED Requirements

### Requirement: Repository automation has one portable semantic owner

Forge, release, quality, and contract behavior SHALL be implemented in the
repository's Python command and pytest surfaces. CI MAY select a platform or
supply credentials but SHALL NOT reimplement repository policy. Shell adapters
MAY exist only when required by the target operating system and SHALL contain no
product or repository policy.

#### Scenario: A developer verifies the repository on a supported platform

- **WHEN** the developer runs the documented repository verification command
- **THEN** the same Python and pytest owners execute on Windows, macOS, and Linux
- **AND** no POSIX shell installation is required on native Windows

#### Scenario: A Shell owner is migrated

- **WHEN** its Python replacement and callers are complete
- **THEN** the Shell file is deleted in the same change
- **AND** no forwarding wrapper or parallel PowerShell implementation remains
