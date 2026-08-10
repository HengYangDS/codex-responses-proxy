## MODIFIED Requirements

### Requirement: One self-contained product executable

Codex Responses Proxy SHALL expose one `codex-responses-proxy` executable in a
manifest-bound native bundle that contains the selected native supervision
adapter and runs without an installed Python interpreter, package environment,
source checkout, or repository script.

#### Scenario: A released product selects its native service adapter

- **WHEN** the bundled executable runs `status` or begins installation on macOS,
  Linux, or Windows
- **THEN** its adjacent frozen dependencies and platform adapter are available
  from the same verified bundle
- **AND** missing internal modules cannot be hidden as an unknown service state
- **AND** no traceback, warning, Python module name, or private path is emitted.

#### Scenario: A release artifact is incomplete

- **WHEN** native platform assembly cannot enumerate every required bundle file
- **THEN** the operation exits nonzero before lifecycle mutation
- **AND** the user receives one concise reinstall action
- **AND** the release gate rejects the artifact.

#### Scenario: A user invokes a released product

- **WHEN** the user runs help, `version`, or `status` from a pristine directory
  with Python absent from `PATH`
- **THEN** the executable completes its documented behavior from the verified
  bundle
- **AND** no module path, virtual environment, source file, or missing-Python
  diagnostic appears.

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native bundle build owner and SHALL prove CLI behavior, real
handoff behavior, no-Python execution, prewarmed startup, and release-asset
packaging.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release
  gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native
  bundle
- **AND** the release test starts the prewarmed executable within its bounded
  handoff window
- **AND** both surfaces retain their complete owned behavior tests.
