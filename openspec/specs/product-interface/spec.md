# Product Interface

## Purpose

Define one self-contained executable UX, repository-owned DX, native distribution contract, and terminal repository-family state.
## Requirements
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

### Requirement: Small public lifecycle grammar

The public command grammar SHALL contain only `install`, `status`, `doctor`,
`reload`, `recover`, `uninstall`, and `version`. Private service execution MUST
NOT appear as public commands or aliases.

#### Scenario: Public help is rendered

- **WHEN** a user requests top-level help
- **THEN** exactly the supported lifecycle commands are presented
- **AND** Python module commands, internal service entrypoints, and aliases are
  absent.

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
service, temporary product directory, or generated closeout residue.

#### Scenario: Closeout audit completes

- **WHEN** final Git, repository-family, process, service, and filesystem audits
  run
- **THEN** only the clean canonical repository and immutable publication or
  closeout records remain
- **AND** every removed lane is bound to its exact final head and delta digest.

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native executable build owner and SHALL prove CLI behavior,
real handoff behavior, no-Python execution, and release-asset packaging.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native executable
- **AND** both surfaces retain their complete owned behavior tests.

### Requirement: Local product closure is Forge-free

The repository SHALL declare one local verification command and one local
installation command that operate from its isolated locked environment. It SHALL
also declare distinct GitLab and GitHub remote aliases and tracked CI surfaces.
GitLab and GitHub SHALL remain independent publication peers: neither Forge may
consume the other Forge's CI status or release assets as publication authority.
Only `main`, `dev`, and `proposal/*` are remote-eligible; `candidate/dev` and
`work/*` remain local-only. Forge publication SHALL be an optional distribution
projection, not a prerequisite for local product closure.

#### Scenario: Both Forges are unavailable

- **WHEN** a clean accepted checkout has no reachable remote
- **THEN** the declared repository-owned command can verify the current source
- **AND** an operator can install a verified current-platform artifact through
  the declared isolated product executable
- **AND** no hosted publication fact is falsely claimed.

#### Scenario: Either Forge is independently available

- **WHEN** GitLab or GitHub alone can receive an admitted remote-eligible branch
- **THEN** that Forge can run its own tracked CI and publish its own release
- **AND** the unavailable peer creates no dependency or substitute authority
- **AND** no `candidate/dev` or `work/*` ref is published.

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Human output SHALL use
consistent sections, display-width alignment, actionable failure guidance, and
no serialized object dump. Source modules, Python launch syntax, repository
paths, and release-operator commands SHALL remain outside the end-user journey.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, service, and listener state in a scannable layout
- **AND** the same observation remains available without semantic drift through `status --json`
- **AND** neither output exposes a Python module invocation or source-checkout requirement.

### Requirement: Native lifecycle inspection is self-contained
The released executable SHALL discover listener and process identity on each
supported operating system without requiring an optional host utility outside
the product dependency graph.

#### Scenario: Linux has no lsof executable
- **WHEN** the native Linux lifecycle verifies the listener bound to its port
- **THEN** it SHALL still discover the exact listener PID
- **AND** it SHALL preserve the existing executable-and-private-role identity proof.

