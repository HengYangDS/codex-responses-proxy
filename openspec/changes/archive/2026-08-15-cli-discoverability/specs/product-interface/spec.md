## MODIFIED Requirements

### Requirement: One self-contained product executable

Codex Responses Proxy SHALL expose one `codex-responses-proxy` executable in a
manifest-bound native bundle that contains the selected native supervision
adapter and runs without an installed Python interpreter, package environment,
source checkout, or repository script. Installation SHALL project that
executable into the current user's platform command directory as a native link,
not a wrapper, alias, shell-profile edit, or second copy.

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

#### Scenario: A verified release is installed

- **WHEN** installation finalizes a verified native payload
- **THEN** `codex-responses-proxy` is discoverable through the user's platform
  command directory
- **AND** it resolves to the exact installed executable
- **AND** no Python interpreter, source checkout, wrapper, or shell-profile
  mutation is required.

#### Scenario: A foreign command occupies the target

- **WHEN** the derived command path is not absent and is not an exact link to
  this product's installed executable
- **THEN** installation fails before payload mutation
- **AND** the foreign path remains unchanged.

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Human output SHALL use
consistent sections, display-width alignment, actionable failure guidance, and
no serialized object dump. Source modules, Python launch syntax, repository
paths, and release-operator commands SHALL remain outside the end-user journey.
Status SHALL report release identity from the verified installed-state record
and command discoverability without consulting repository files or a second
state authority.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, command, service, and listener
  state in a scannable layout
- **AND** `status --json` exposes the same semantics
- **AND** `doctor` classifies a missing or foreign command projection as an
  actionable failure
- **AND** neither output exposes a Python module invocation or source-checkout
  requirement.

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `product-interface:One self-contained product executable` | `2.1` | `tests/lifecycle/test_command.py; tests/lifecycle/test_transaction.py` |
| `product-interface:Human and machine interfaces share one result model` | `1.3` | `tests/lifecycle/test_control.py; tests/cli/test_lifecycle.py` |
