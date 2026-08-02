## MODIFIED Requirements

### Requirement: Native supervision starts and remains observable

The released macOS service SHALL start the watchdog by its exact installed
entrypoint without relying on ambient `PYTHONPATH`, SHALL preserve the listener
argv needed for ownership checks, and SHALL persist stdout and stderr below a
pre-created application log directory. Process discovery on non-Darwin hosts
SHALL consume one batch command inventory per discovery call rather than
launching a second host query for every PID, while every signal path SHALL
revalidate the exact live PID identity immediately before mutation.

#### Scenario: Direct watchdog execution from an unrelated directory

- **WHEN** the installed watchdog file is loaded in an isolated Python process
- **THEN** the package root is established before imports can resolve sibling
  modules
- **AND** no supervision filename shadows a Python standard-library module.

#### Scenario: First native-service installation

- **WHEN** launchd is loaded before any application log exists
- **THEN** the installer creates the configured log directory
- **AND** the plist routes stdout and stderr to persistent files there.

#### Scenario: Non-Darwin process discovery

- **WHEN** the runtime discovers PIDs naming one exact installed entrypoint on
  Windows or Linux
- **THEN** it obtains one batch process inventory and validates each captured
  command without issuing a per-PID host query
- **AND** a later signal operation independently revalidates the selected live
  PID before mutation.
