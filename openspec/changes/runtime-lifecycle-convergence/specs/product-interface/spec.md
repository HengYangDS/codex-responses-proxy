## MODIFIED Requirements

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Every public command
SHALL support both projections and SHALL preserve one semantic result and exit
status model across them. Human output SHALL use consistent sections,
display-width alignment, actionable failure guidance, and no serialized object
dump. Source modules, Python launch syntax, repository paths, and
release-operator commands SHALL remain outside the end-user journey. Status
SHALL report release identity from the verified installed-state record and
command discoverability without consulting repository files or a second state
authority. Runtime evidence SHALL be returned only when its PID is the sole
listener owned by the selected installation. An installed command path SHALL be
interpreted using the native absolute-path and link semantics of the host that
recorded it.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, command, service, and listener
  state in a scannable layout
- **AND** `status --json` exposes the same semantics
- **AND** Windows accepts its recorded native absolute command path without
  treating a foreign path syntax as valid
- **AND** `doctor` classifies a missing or foreign command projection as an
  actionable failure
- **AND** neither output exposes a Python module invocation or source-checkout
  requirement.

#### Scenario: Automation invokes any public command

- **WHEN** automation invokes `install`, `status`, `doctor`, `recover`, `reload`,
  `uninstall`, or `version` with `--json`
- **THEN** the command emits one stable JSON value and no human decoration
- **AND** expected failures remain nonzero without a traceback or warning.

#### Scenario: Another listener occupies the selected port

- **WHEN** loopback health responds but its PID is not the sole listener owned by
  the selected installation
- **THEN** status reports no runtime evidence for that installation
- **AND** it does not combine foreign health with local payload state.

### Requirement: Repository-owned verification separates wheel compatibility from native distribution

Python compatibility and quality sessions SHALL build and install the project
wheel, then exercise the complete behavior inventory through that installed
environment. They MUST NOT rebuild the native distribution. The release session
SHALL be the sole native bundle build owner and SHALL prove every public
command's help, valid and invalid inputs, human and JSON output, exit status,
real handoff behavior, no-Python execution, prewarmed startup, and release-asset
packaging. Release validation SHALL exercise the exact native executable that
installation will serve, using an isolated installation root, native service
identity, state root, HOME, and listener port. A temporary copy or the canonical
installed service SHALL NOT be treated as proof of the release candidate.

#### Scenario: Python and native gates prove distinct facts

- **WHEN** repository verification runs the supported Python matrix and release
  gate
- **THEN** each Python version proves the installed wheel and console executable
- **AND** exactly one release session builds and black-box tests the native
  bundle
- **AND** the release test prewarms and starts the exact installed executable
  within the configured installation deadline
- **AND** the complete public command matrix runs without consulting or mutating
  the canonical installation
- **AND** both surfaces retain their complete owned behavior tests.

#### Scenario: An operator upgrades a running installation

- **WHEN** a verified release is committed as the successor projection
- **THEN** the exact installed executable completes a bounded prewarm probe
- **AND** the handoff uses the operator's configured installation deadline.
