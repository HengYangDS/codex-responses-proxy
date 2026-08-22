## ADDED Requirements

### Requirement: Runtime carrier remains install-generation stable

The supported predecessor installer and successor payload SHALL implement one
stable, secret-free `runtime-config.json` contract. Operating-system service
definitions SHALL remain derived projections and SHALL NOT expand that product
carrier with host-only ownership coordinates.

#### Scenario: A predecessor writes the successor carrier

- **WHEN** a supported published predecessor installs a newer signed payload
- **THEN** the predecessor writes the same current runtime-carrier schema that
  the successor consumes
- **AND** the successor activates without a compatibility parser or migration
  branch.

#### Scenario: macOS service ownership is projected

- **WHEN** installation creates or removes one launchd service
- **THEN** its exact plist path and `HOME` projection come from the live runtime
  context used by that operation
- **AND** the persisted product carrier remains platform-neutral.
