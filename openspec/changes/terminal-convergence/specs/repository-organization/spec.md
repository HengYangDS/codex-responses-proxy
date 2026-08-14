## MODIFIED Requirements

### Requirement: Physical structure follows semantic ownership

Source, tests, tools, documentation, configuration, and release assets SHALL be
organized by one explicit semantic owner. Cross-package private imports,
forwarding facades, concatenated semantic package names, and root-level script
sprawl SHALL not create parallel authority.

#### Scenario: A contributor locates behavior

- **WHEN** a contributor follows a public command or runtime behavior
- **THEN** its implementation, tests, specification, and documentation point to one semantic owner
- **AND** no compatibility module or duplicated policy must be consulted.

### Requirement: User and developer interfaces remain distinct

Users SHALL operate the installed `codex-responses-proxy` command. Development
commands and module execution SHALL remain documented only as repository-local
DX surfaces.

#### Scenario: A user installs a signed release

- **WHEN** installation completes from a verified asset
- **THEN** status, lifecycle, and diagnostics are available through the product command
- **AND** no `python -m`, source checkout, uv, Nox, or ETHOS command is required at runtime.
