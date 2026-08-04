# Product Interface

## Purpose

Define one self-contained executable UX, repository-owned DX, native distribution contract, and terminal repository-family state.

## Requirements

### Requirement: One self-contained product executable

Codex Responses Proxy SHALL expose one `codex-responses-proxy` executable that
runs without an installed Python interpreter, Python package environment,
source checkout, or repository script.

#### Scenario: A user invokes a released product

- **WHEN** the user runs help, `version`, or `status` from a pristine directory
  with Python absent from `PATH`
- **THEN** the executable completes its documented behavior
- **AND** no module path, virtual environment, source file, or missing-Python
  diagnostic appears.

### Requirement: Small public lifecycle grammar

The public command grammar SHALL contain only `install`, `status`, `doctor`,
`reload`, `uninstall`, and `version`. Private service execution and migration
mechanics MUST NOT appear as public commands or compatibility aliases.

#### Scenario: Public help is rendered

- **WHEN** a user requests top-level help
- **THEN** exactly the supported lifecycle commands are presented
- **AND** Python module commands, internal service entrypoints, and retired
  aliases are absent.

### Requirement: Quiet actionable diagnostics

Expected command failures SHALL return a concise human diagnostic or a stable
JSON error object with a nonzero exit status. They MUST NOT emit a traceback,
warning, usage dump unrelated to the error, success residue, credential,
request payload, or local private path.

#### Scenario: Doctor finds an unavailable listener

- **WHEN** `doctor --json` evaluates an installed service whose listener is not
  accepting
- **THEN** it returns the classified failed check and an actionable next step
- **AND** output contains no traceback, warning, secret, or false success.

### Requirement: Repository-owned development environment

The repository SHALL own its supported Python versions, direct and transitive
development dependencies, isolated environments, and verification session
graph. Verification MUST NOT be satisfied by another repository environment,
ambient user-site packages, PATH-selected quality tools, or mutable unpinned
dependency resolution.

#### Scenario: A contributor verifies a fresh clone

- **WHEN** a contributor with Git and uv runs the documented locked command
- **THEN** repository-local environments execute the declared Python 3.12,
  3.13, and 3.14 matrix
- **AND** local and hosted verification use the same session owners.

### Requirement: Terminal lane state

After release and runtime acceptance, the repository family SHALL contain no
delivery worktree, work branch, lease, detached temporary checkout, obsolete
service, retired product directory, or generated closeout residue.

#### Scenario: Closeout audit completes

- **WHEN** final Git, repository-family, process, service, and filesystem audits
  run
- **THEN** only the clean canonical repository and immutable publication or
  closeout records remain
- **AND** every removed lane is bound to its exact final head and delta digest.
