## MODIFIED Requirements

### Requirement: One self-contained product executable

Codex Responses Proxy SHALL expose one `codex-responses-proxy` executable that
contains the selected native supervision adapter and runs without an installed
Python interpreter, package environment, source checkout, or repository script.

#### Scenario: A released product selects its native service adapter

- **WHEN** the built executable runs `status` or begins installation on macOS,
  Linux, or Windows
- **THEN** its platform adapter is available from the bundled artifact
- **AND** missing internal modules cannot be hidden as an unknown service state
- **AND** no traceback, warning, Python module name, or private path is emitted.

#### Scenario: A release artifact is incomplete

- **WHEN** native platform assembly cannot be completed
- **THEN** the operation exits nonzero before lifecycle mutation
- **AND** the user receives one concise reinstall action
- **AND** the release gate rejects the artifact.

#### Scenario: A user invokes a released product

- **WHEN** the user runs help, `version`, or `status` from a pristine directory
  with Python absent from `PATH`
- **THEN** the executable completes its documented behavior
- **AND** no module path, virtual environment, source file, or missing-Python
  diagnostic appears.
