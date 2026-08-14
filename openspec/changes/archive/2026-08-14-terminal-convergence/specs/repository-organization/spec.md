## MODIFIED Requirements

### Requirement: Portable product and repository UX

Users SHALL operate the installed `codex-responses-proxy` command for status,
lifecycle, and diagnostics. It SHALL not require Python, module execution, a
source checkout, uv, Nox, ETHOS, repository-specific shell variables, personal
paths, identities, or Forge coupling. Repository verification SHALL expose one
documented locked command graph as a distinct developer surface.

#### Scenario: Operator installs a release

- **WHEN** an operator invokes the documented product installation command
- **THEN** the command accepts explicit release metadata or a resolved manifest without personal paths, identities, or Forge coupling

#### Scenario: Contributor verifies a checkout

- **WHEN** a contributor runs the documented local gate
- **THEN** the same `uv`/`nox` graph is used by CI and ETHOS proof without a second test runner or compatibility wrapper

#### Scenario: A user installs a signed release

- **WHEN** installation completes from a verified asset
- **THEN** status, lifecycle, and diagnostics are available through the product command
- **AND** no `python -m`, source checkout, uv, Nox, or ETHOS command is required at runtime.
