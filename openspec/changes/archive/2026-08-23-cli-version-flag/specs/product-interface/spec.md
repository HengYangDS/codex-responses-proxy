## MODIFIED Requirements

### Requirement: Small public lifecycle grammar

The public command grammar SHALL contain only `install`, `status`, `doctor`,
`reload`, `recover`, and `uninstall`. The executable SHALL expose release
identity through the conventional top-level `--version` option. Private service
execution MUST NOT appear as public commands or aliases.

#### Scenario: Public help is rendered

- **WHEN** a user requests top-level help
- **THEN** exactly the supported lifecycle commands are presented
- **AND** Python module commands, internal service entrypoints, and aliases are absent.

#### Scenario: Release identity is requested

- **WHEN** a user or packaging tool invokes `codex-responses-proxy --version`
- **THEN** the executable prints the current release identity and exits successfully
- **AND** no redundant `version` subcommand is exposed.
