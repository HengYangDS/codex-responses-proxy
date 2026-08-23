# Product Interface

## Purpose

Define one self-contained executable UX, repository-owned DX, native distribution contract, and terminal repository-family state.

## Requirements

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

- **WHEN** the user runs help, `--version`, or `status` from a pristine directory
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

### Requirement: Small public lifecycle grammar

The public command grammar SHALL contain only `install`, `status`, `doctor`,
`reload`, `recover`, and `uninstall`. The executable SHALL expose release
identity through the conventional top-level `--version` option. Private service
execution MUST NOT appear as public commands or aliases.

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

#### Scenario: Compatibility evidence uses a published predecessor

- **WHEN** release compatibility verification is explicitly supplied one
  published signed predecessor asset and its external trust anchor
- **THEN** it installs and verifies that exact predecessor before deriving an
  isolated route-controlled fixture from the admitted executable bytes
- **AND** proves ordinary and streaming requests survive the forward upgrade
- **AND** never fabricates a predecessor by changing current release metadata.

#### Scenario: An operator upgrades a running installation

- **WHEN** a verified release is committed as the successor projection
- **THEN** the exact installed executable completes a bounded prewarm probe
- **AND** the handoff uses the operator's configured installation deadline.

### Requirement: Local product closure is Forge-free

The repository SHALL keep local Git as the sole product source and SHALL make
GitLab and GitHub optional, independent publication peers. A selected Forge
SHALL receive the exact signed local commit object without changing author,
committer, parents, tree, message, or signature. `main` publication SHALL
atomically advance remote `main` and `dev`; `proposal/*` SHALL publish only the
selected proposal. `candidate/dev` and `work/*` SHALL remain local-only.

#### Scenario: Both Forges are unavailable

- **WHEN** a clean accepted checkout has no reachable remote
- **THEN** local verification, packaging, installation, runtime acceptance,
  update, rollback, and uninstall remain executable
- **AND** no hosted publication fact is claimed.

#### Scenario: Either Forge is independently available

- **WHEN** GitLab or GitHub alone is selected for publication
- **THEN** it receives the exact local signed commit OID and tree
- **AND** the unavailable peer is neither read nor required.

#### Scenario: Both Forges are independently available

- **WHEN** each peer is selected in a separate publication operation
- **THEN** local, GitLab, and GitHub branch tips are the same commit OID
- **AND** each Forge retains independent authentication, CI, Release, and asset state.

#### Scenario: Source proof is complete

- **WHEN** exact-HEAD repository proof passes and the Change is archived
- **THEN** the governed landing command can atomically advance `candidate/dev`
- **AND** the permission does not authorize direct publication or runtime mutation
- **AND** no alternate integration path is introduced.

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Every public command
SHALL support both projections and SHALL preserve one semantic result and exit
status model across them. Healthy absence, pending recovery, invalid evidence,
degraded installation, and completed mutation SHALL be distinct outcomes.
Human output SHALL use consistent sections, display-width alignment,
actionable state-specific guidance, and no serialized object dump. Source
modules, Python launch syntax, repository paths, and release-operator commands
SHALL remain outside the end-user journey. Status SHALL report release identity
from the verified installed-state record and command discoverability without
consulting repository files or a second state authority. Runtime evidence SHALL
be returned only when its PID is the sole listener owned by the selected
installation. An installed command path SHALL be interpreted using the native
absolute-path and link semantics of the host that recorded it.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, command, service, listener,
  and transaction state in a scannable layout
- **AND** `status --json` exposes the same semantics
- **AND** Windows accepts its recorded native absolute command path without
  treating a foreign path syntax as valid
- **AND** `doctor` classifies a missing or foreign command projection as an
  actionable failure
- **AND** a listener is healthy only when its runtime payload identity matches
  the currently committed installed candidate
- **AND** neither output exposes a Python module invocation or source-checkout
  requirement.

#### Scenario: The product is not installed

- **WHEN** `status`, `doctor`, `recover`, or `uninstall` observes no owned
  installation or transaction
- **THEN** each command identifies the absent state without calling it corrupt,
  unknown, recovered, or removed
- **AND** `doctor` recommends installation rather than reload
- **AND** `recover` and `uninstall` return successful explicit no-op results.

#### Scenario: Automation invokes any public command

- **WHEN** automation invokes `install`, `status`, `doctor`, `recover`, `reload`,
  `uninstall`, or `version` with `--json`
- **THEN** the command emits one stable JSON value and no human decoration
- **AND** successful lifecycle results use one `state` discriminator rather
  than parallel boolean or mode fields
- **AND** expected failures expose one stable error `code`, one concise
  `message`, and one directly executable `next` command
- **AND** expected failures remain nonzero without a traceback or warning.

#### Scenario: Another listener occupies the selected port

- **WHEN** loopback health responds but its PID is not the sole listener owned by
  the selected installation
- **THEN** status omits untrusted runtime evidence
- **AND** doctor reports an identity mismatch without treating that listener as
  this product.

### Requirement: Native lifecycle inspection is self-contained

The released executable SHALL discover listener and process identity on each
supported operating system without requiring an optional host utility outside
the product dependency graph.

#### Scenario: Linux has no lsof executable

- **WHEN** the native Linux lifecycle verifies the listener bound to its port
- **THEN** it SHALL still discover the exact listener PID
- **AND** it SHALL preserve the existing executable-and-private-role identity proof.

### Requirement: Repository automation has one portable semantic owner

Forge, release, quality, and contract behavior SHALL be implemented in the
repository's Python command and pytest surfaces. CI MAY select a platform or
supply credentials but SHALL NOT reimplement repository policy. Shell adapters
MAY exist only when required by the target operating system and SHALL contain no
product or repository policy.

#### Scenario: A developer verifies the repository on a supported platform

- **WHEN** the developer runs the documented repository verification command
- **THEN** the same Python and pytest owners execute on Windows, macOS, and Linux
- **AND** no POSIX shell installation is required on native Windows

#### Scenario: A Shell owner is migrated

- **WHEN** its Python replacement and callers are complete
- **THEN** the Shell file is deleted in the same change
- **AND** no forwarding wrapper or parallel PowerShell implementation remains
