# Spec Delta

## MODIFIED Requirements

### Requirement: Python compatibility and native release prove distinct facts

Each supported Python minor line SHALL build and install the wheel, then run the
complete non-native behavior inventory. The release session SHALL be the only
native executable build owner and SHALL black-box test the target-platform
executable through one portable process-environment contract. That contract
SHALL preserve the native host execution substrate, redirect Proxy-owned user,
payload, state, and command roots to test-owned locations, and make Python
undiscoverable through the product `PATH`.

#### Scenario: The supported matrix runs

- **WHEN** Python 3.12, 3.13, and 3.14 sessions execute
- **THEN** each tests the installed wheel rather than source-import fallback
- **AND** hosted jobs select minor release lines rather than one host-specific
  patch build
- **AND** platform-specific integration runs only on the platform that owns the
  real system call while synthetic wire fixtures remain portable.

#### Scenario: A native process environment is isolated

- **WHEN** black-box acceptance starts a packaged executable
- **THEN** the child environment derives the execution substrate from the
  current supported native host
- **AND** Proxy-owned user, payload, state, and command roots resolve only
  inside the test-owned workspace
- **AND** the product `PATH` contains no Python executable
- **AND** one platform-neutral contract supplies the environment on macOS,
  Linux, and Windows.

#### Scenario: A native asset is accepted

- **WHEN** the release session packages a supported platform archive
- **THEN** help, version, status, handoff, manifest, and service behavior have
  passed through the built executable under the isolated native environment
- **AND** the archive is bound to the release-owned manifest.

## ADDED Requirements

### Requirement: Online link checks respect the selected publication plane

Local verification SHALL check repository links without requiring either Forge.
Online verification on a selected Forge SHALL check that peer and public
references without requiring network access to another declared publication
repository. The existing native checker SHALL derive only exact unselected
repository exclusions from the authoritative publication table; it SHALL NOT
exclude an entire host, private address range, source file, wrong repository, or
unknown peer. Excluded links remain network-unqualified in that execution.
Repository identity and reference admission SHALL remain mandatory and distinct
from HTTP availability; the shared ETHOS contract owns that admission.

Declaration roots SHALL be normalized by the locked native WHATWG URL parser
before constructing exclusions. Duplicate or nested repository roots,
credentials, queries, fragments, invalid roots, and failed native observations
SHALL refuse peer-scoped verification without exposing supplied credentials.
Parser-dependent tests SHALL run in repository governance, not add a Node
prerequisite to the Python-only compatibility matrix.

#### Scenario: Public CI cannot reach the organization's private Forge

- **WHEN** GitHub runs online link verification with GitHub explicitly selected
- **THEN** it checks local links, the declared GitHub repository, and public
  references without contacting the exact declared GitLab repository
- **AND** it does not report that unselected GitLab repository as available or
  borrow its result for GitLab qualification.

#### Scenario: A selected or unrelated link is broken

- **WHEN** the selected peer, an undeclared repository on the other peer's host,
  or an external reference returns an error
- **THEN** native link verification fails
- **AND** unknown peers or malformed declarations fail before any exclusion is
  created; neither timeouts nor failure status codes are accepted.

### Requirement: Clean-room verification follows the locked repository environment

The repository SHALL expose one cross-platform developer entrypoint that selects
locked tools, reconstructs Work-Lane-local mutable environments, and runs the
same semantic verification graph consumed by both Forges. Ambient interpreters,
user-site packages, global tool configuration, another checkout's environment,
and mutable unpinned resolution SHALL NOT contribute to success.

#### Scenario: A fresh checkout is bootstrapped

- **WHEN** the repository has no local virtual environment, Nox environment,
  Node modules, build output, coverage data, or test temporary state
- **THEN** the documented locked bootstrap reconstructs all required state
- **AND** subsequent verification uses only that checkout's mutable environments
  and shared content-addressed caches.

### Requirement: Native process acceptance preserves the host substrate

Black-box native acceptance SHALL derive the child environment from the current
supported host, remove inherited Proxy and Python injection state, redirect all
product-owned roots, and make Python undiscoverable through the product `PATH`.
One semantic owner SHALL supply that environment to fixtures, packaged CLI
contracts, and release verification on macOS, Linux, and Windows.

#### Scenario: A packaged executable runs without Python discovery

- **WHEN** help, version, status, prewarm, or another self-contained public
  command runs under native acceptance
- **THEN** the executable cannot resolve Python through `PATH`
- **AND** the operating-system execution substrate remains available
- **AND** no platform allow-list or Windows-only environment exception is used.

#### Scenario: Native tests run from a deep checkout

- **WHEN** the native release session executes from a long Runner checkout path
- **THEN** pytest SHALL use a uniquely owned temporary root outside that
  checkout
- **AND** teardown SHALL remove that root after native process cleanup,
  including failed test control flow
- **AND** the session SHALL NOT infer payload compatibility from physical CPU
  naming when a different executable ABI runs under emulation.

#### Scenario: Native CI selects the locked interpreter

- **WHEN** native macOS or Windows CI reconstructs its local environment
- **THEN** the existing Mise tool-aware environment directive binds the exact
  locked executable returned by its native resolver, not an install directory
- **AND** native locked synchronization restores a missing or stale generated
  environment before execution
- **AND** an out-of-date dependency lock fails without rewriting source
- **AND** the local tasks, direct proof commands, and native CI consume the same
  binding
- **AND** each native platform executes the environment conformance before
  constructing its candidate
- **AND** neither an executable-name ambiguity, no-sync execution, nor warning
  suppression establishes acceptance.

#### Scenario: Sequential consumers preserve a ready environment

- **GIVEN** the current locked interpreter and dependencies have synchronized
  this Work Lane's project environment
- **WHEN** consecutive verification commands execute with unchanged inputs
- **THEN** they reuse that environment without deleting or recreating it
- **AND** its configuration and existing owned content remain unchanged
- **AND** changed interpreter or lock inputs still trigger normal admission and
  synchronization.

#### Scenario: A native job selects only acquisition tools

- **WHEN** a job enables a declared tool subset without Python
- **THEN** native environment resolution does not require an unselected Python
  installation or reference an unavailable tool field
- **AND** that subset does not replace the job's separately owned interpreter
- **AND** selecting the Python tool plane still binds the locked interpreter.
