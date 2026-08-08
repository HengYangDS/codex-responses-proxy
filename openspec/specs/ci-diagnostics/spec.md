# Verification Diagnostics

## Purpose

Define one repository-owned verification graph whose successful output is
quiet, reproducible, cross-platform, and sufficient to reject incomplete
product or release candidates.
## Requirements
### Requirement: Verification has one repository-owned owner

Nox SHALL own the verification graph, the committed uv lock SHALL own Python
tool resolution, and project metadata SHALL declare the exact current stable uv
bootstrap used by local and hosted verification. A pending release heading SHALL
match `VERSION` and the current UTC date before either Forge prepares a release.

#### Scenario: A clean checkout is verified

- **WHEN** a contributor or Forge installs the declared uv bootstrap and runs
  the repository command
- **THEN** the lock supplies every runtime and quality dependency
- **AND** Nox resolves the Python matrix from `.python-versions`
- **AND** no ambient user site, another repository environment, or unpinned
  package resolution contributes to success.

#### Scenario: Release preparation crosses a UTC date boundary

- **WHEN** a pending version has not been tagged and its Changelog date is no longer the current UTC date
- **THEN** release preparation fails closed
- **AND** the heading is advanced before proof, tagging, or publication.

#### Scenario: Provider-native tags are checked

- **WHEN** GitLab or GitHub validates release history
- **THEN** the provider checks its own reachable SemVer tags and corresponding
  Changelog headings
- **AND** tag creation time is not required to equal the Changelog date
- **AND** the two publication planes remain independently verifiable.

#### Scenario: GitLab runs a repository Python tool

- **WHEN** a GitLab job invokes release or quality Python code
- **THEN** it runs through `uv run --locked --no-sync`
- **AND** no ambient interpreter or uninstalled runtime dependency contributes
  to the result.

#### Scenario: GitLab project coordinates contain namespaces

- **WHEN** runner admission queries a project whose coordinate contains `/`
- **THEN** the coordinate is encoded as one GitLab project identifier
- **AND** the runner API request resolves the intended project rather than a
  truncated path.

#### Scenario: The uv bootstrap advances

- **WHEN** the current stable uv patch is available
- **THEN** project metadata and its executable contract name that same exact version
- **AND** the dependency lock and product runtime semantics remain unchanged.

### Requirement: Successful verification output is pristine

Passing tests, quality checks, builds, and expected operational-failure probes
SHALL emit no unhandled traceback, warning, `socketserver` exception banner,
package-install warning, false success, or private path. Expected peer
disconnects MAY be suppressed only by the fixture that creates them.

#### Scenario: A test leaks a warning or server exception

- **WHEN** the underlying process exits zero but emits an unhandled warning or
  exception banner
- **THEN** the repository-owned gate fails
- **AND** a Forge cannot report that revision as verified.

#### Scenario: A clean gate succeeds

- **WHEN** quick, quality, matrix, or release verification completes
- **THEN** its log ends with one concise receipt
- **AND** the checkout contains no bytecode, coverage, Ruff, or build cache
  created by that gate.

### Requirement: Python compatibility and native release prove distinct facts

Each supported Python minor line SHALL build and install the wheel, then run
the complete non-native behavior inventory. The release session SHALL be the
only native executable build owner and SHALL black-box test the target-platform
executable with Python absent from the product `PATH`.

#### Scenario: The supported matrix runs

- **WHEN** Python 3.12, 3.13, and 3.14 sessions execute
- **THEN** each tests the installed wheel rather than source-import fallback
- **AND** hosted jobs select minor release lines rather than one host-specific
  patch build
- **AND** platform-specific integration runs only on the platform that owns the
  real system call while synthetic wire fixtures remain portable.

#### Scenario: A native asset is accepted

- **WHEN** the release session packages a supported platform archive
- **THEN** help, version, status, handoff, manifest, and service behavior have
  passed through the built executable
- **AND** the archive is bound to the release-owned manifest.

### Requirement: Coverage is strict and host-independent

The complete behavior suite SHALL keep aggregate, statement, branch, and every
semantic package coverage strictly greater than 95 percent. Required platform
branches SHALL be exercised through explicit semantic inputs rather than host
spoofing, exclusions, or CI-only production conditionals.

#### Scenario: A quality gate succeeds

- **WHEN** coverage is reported for the exact candidate tree
- **THEN** every required ratio is greater than 95 percent
- **AND** no required test is skipped merely because the quality host differs
  from the modeled platform.

### Requirement: Python structure limits are repository-owned

The repository quality owner SHALL measure production logical statements,
module effective lines, maximum function lines, and control-flow nesting. The
declared ceilings SHALL be positive, explicit, and exercised by contract tests;
normal source files SHALL receive no path-specific allowance above them.

#### Scenario: Structural policy drifts

- **WHEN** a ceiling is missing, non-positive, raised above the ratified bound,
  or bypassed for one production path
- **THEN** repository quality fails before the candidate is accepted.

#### Scenario: Production structure exceeds a ceiling

- **WHEN** a production module exceeds any declared structural dimension
- **THEN** the gate reports the exact path, measured value, and ceiling
- **AND** the implementation is simplified rather than compensated by another
  allowance.

### Requirement: Forge jobs are portable projections

Hosted jobs SHALL use supported native shells and filesystem semantics, install
their explicit operating-system prerequisites, and reach a terminal result on
an admitted project runner. A reused self-hosted checkout SHALL preserve Git
diagnostic integrity without changing runner-global configuration.

#### Scenario: Windows verifies the product

- **WHEN** the Windows matrix executes
- **THEN** it uses native PowerShell and Git index metadata for executable intent
- **AND** POSIX-only shell fixtures are excluded without disabling Windows
  product behavior.

#### Scenario: Linux builds an x86_64 asset on an ARM host

- **WHEN** the Docker executor runs on ARM
- **THEN** the release job explicitly selects an amd64 container
- **AND** packaging fails unless the container reports an x86_64-compatible
  machine.

#### Scenario: A required runner is unavailable

- **WHEN** Forge admission cannot match every job to an allowed runner
- **THEN** publication is blocked before a pipeline is treated as accepted
- **AND** a pending job is not reported as verification success.

### Requirement: Hosted product-tool execution uses the locked product environment

Hosted jobs SHALL install the product runtime whenever they execute repository
product tools, and SHALL run package-aware tools through import-safe module
entrypoints.

#### Scenario: Release metadata executes in GitLab

- **WHEN** the GitLab metadata job validates a branch or tag
- **THEN** it installs the complete environment from `uv.lock`
- **AND** the product CLI dependencies are importable

#### Scenario: Repository quality executes in either Forge

- **WHEN** a hosted job invokes repository quality checks
- **THEN** it uses the package-aware module entrypoint
- **AND** release chronology tests receive complete tag history

