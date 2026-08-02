## ADDED Requirements

### Requirement: Native supervision starts and remains observable

The released macOS service SHALL start the watchdog by its exact installed
entrypoint without relying on ambient `PYTHONPATH`, SHALL preserve the listener
argv needed for ownership checks, and SHALL persist stdout and stderr below a
pre-created application log directory.

#### Scenario: Direct watchdog execution from an unrelated directory

- **WHEN** the installed watchdog file is loaded in an isolated Python process
- **THEN** the package root is established before imports can resolve sibling
  modules
- **AND** no supervision filename shadows a Python standard-library module.

#### Scenario: First native-service installation

- **WHEN** launchd is loaded before any application log exists
- **THEN** the installer creates the configured log directory
- **AND** the plist routes stdout and stderr to persistent files there.

### Requirement: Listener port remains configurable

The runtime SHALL own one named default of 8792 and SHALL accept explicit CLI
and `CODEX_RESPONSES_PROXY_PROXY_PORT` overrides without any hard-coded dual
listener design.

#### Scenario: Explicit non-default port

- **WHEN** an operator supplies a supported port through CLI or environment
- **THEN** install, control, and uninstall use that port consistently
- **AND** supervision does not copy 8791 or 8792 literals.
