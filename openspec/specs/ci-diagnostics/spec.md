# CI diagnostics

## Purpose

Codex Responses Proxy SHALL require successful CI jobs to be free of unhandled Python
tracebacks and warnings.
## Requirements
### Requirement: Capability boundary

The CI diagnostics capability SHALL own diagnostic cleanliness across the
repository test runner, quality gate, dependency bootstrap, release metadata
validation, and provider projections without owning application logs or
provider infrastructure. Release-contract tests SHALL verify repository-owner
behavior and stable policy values without depending on private syntax. Every
metadata invocation SHALL select the current provider chronology in all release
states, while canonical GitLab validation remains strict.

#### Scenario: A diagnostic contract changes

- **WHEN** a change alters warning, traceback, compile, cache, dependency
  bootstrap, versioned-tool selection, or release-metadata handling
- **THEN** the repository-owned command remains the semantic owner
- **AND** GitLab and GitHub remain thin projections over that command
- **AND** contract tests prove behavior rather than obsolete implementation text.

#### Scenario: A provider-native release tag is verified

- **WHEN** a Forge checks an already-tagged release from its native history
- **THEN** every direct and regression-driven metadata invocation uses that
  Forge's chronology
- **AND** a policy rejection is concise and contains no implementation traceback
- **AND** missing provider-external history is not mistaken for missing native
  history.

#### Scenario: Canonical chronology is verified

- **WHEN** GitLab checks canonical release history
- **THEN** every canonical heading still requires its exact reachable tag and
  UTC tag date
- **AND** no GitHub-specific subset rule weakens that check.

### Requirement: Passing test jobs have clean diagnostic output

The canonical Python test runner SHALL fail when a test returns nonzero or
emits an unhandled traceback, a `socketserver` exception banner, or a Python
warning. It SHALL use the same compile-and-test entrypoint across supported
interpreters and Forge operating systems. Hosted CI SHALL select each supported
minor release line rather than one platform-specific patch build.

#### Scenario: A passing test leaks a warning

- **WHEN** a test process exits successfully but emits a Python warning
- **THEN** the canonical runner rejects the test job
- **AND** the hosted provider cannot report that revision as verified.

#### Scenario: A supported Python patch is absent from one hosted platform

- **WHEN** an official Forge runner does not publish the same patch build as
  another supported operating system
- **THEN** the job resolves a stable patch from the declared supported minor line
- **AND** verification starts without narrowing the 3.12, 3.13, and 3.14 matrix
- **AND** repository contract tests reject patch-pinned hosted CI configuration.

### Requirement: Expected disconnects and HTTP errors retain one owner

Production handoff control SHALL close failed HTTP responses. Loopback test
fixtures MAY suppress only peer-disconnect errors caused intentionally by the
test; unrelated server exceptions SHALL remain visible.

#### Scenario: A loopback client disconnects before the upstream writes

- **WHEN** an integration test intentionally closes its client connection
- **THEN** the fixture suppresses only the resulting peer-disconnect error
- **AND** any other request-handler exception remains a failing diagnostic.

### Requirement: Quality tooling leaves no checkout cache

Compilation SHALL write bytecode below an isolated temporary prefix, and Ruff
SHALL run without a persistent checkout cache. Containerized dependency
installation SHALL explicitly select its noninteractive policy, suppress
routine package-manager chatter, and emit neither root-user nor frontend
fallback warnings.

#### Scenario: A clean quality gate completes

- **WHEN** the repository-owned quality command succeeds in hosted CI
- **THEN** no bytecode, coverage file, or Ruff cache remains in the checkout
- **AND** the job log contains no pip root-user or Debian frontend warning.

### Requirement: Platform-specific fixtures model only supported host semantics

A test fixture that depends on host shell executable-bit semantics SHALL run
only on hosts that implement those semantics, while each supported operating
system SHALL continue running its product behavior matrix.

#### Scenario: Windows runs the supported product matrix

- **WHEN** the Windows matrix evaluates quality contracts
- **THEN** POSIX shell lookup fixtures are not treated as Windows product behavior
- **AND** all Windows product tests remain enabled.

### Requirement: Quality tool identity excludes informational build metadata

The quality owner SHALL require the exact configured tool name and semantic
version while permitting only an optional space-delimited informational suffix.

#### Scenario: Stable tool reports build metadata

- **WHEN** a pinned tool reports its exact name and semantic version followed by build metadata
- **THEN** the quality owner accepts that executable
- **AND** different versions, prefixes, and malformed suffixes remain rejected.

### Requirement: GitLab main validation follows release state

The GitLab metadata verification job SHALL validate a tag pipeline against its exact tag. For an untagged main pipeline, it SHALL perform ordinary GitLab provider validation when the tag named by `VERSION` already exists and SHALL prepare a release only while that tag is absent.

#### Scenario: Main advances after publication

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag already exists
- **THEN** metadata verification runs ordinary GitLab provider validation
- **AND** it does not reject the commit as an attempted duplicate release.

#### Scenario: Main carries an unpublished release candidate

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag does not exist
- **THEN** metadata verification runs release preparation
- **AND** the existing pending-release chronology requirements remain enforced.

### Requirement: Reused self-hosted checkout preserves diagnostic integrity

A GitHub job on the repository's reused self-hosted runner SHALL keep a valid
pre-checkout `HEAD` reachable only for the checkout transition and SHALL remove
that temporary reachability after checkout. The workflow SHALL NOT change
runner-global Git configuration or suppress unrelated Git diagnostics.

#### Scenario: Checkout replaces an unreferenced detached revision

- **WHEN** a trusted self-hosted job starts from a detached revision that no
  branch or tag retains
- **THEN** the workflow makes that revision reachable before checkout
- **AND** checkout does not emit the abandoned-commit warning
- **AND** an always-running post-checkout step removes the temporary ref.

#### Scenario: Hosted Windows checkout is isolated

- **WHEN** the supported Windows matrix uses its hosted runner workspace
- **THEN** it continues to use the ordinary pinned checkout action
- **AND** the self-hosted temporary-ref lifecycle is not projected into that
  job.

### Requirement: Product identity is provider-neutral

The current repository, package, runtime, service, release, documentation, and
test surfaces SHALL identify the product as Codex Responses Proxy. Provider
names SHALL appear only in provider profiles, endpoints, or provider-specific
wire policies. Publication commands SHALL NOT contain a personal key path or
maintainer identity default, and SHALL fail immediately when explicit signing
inputs are unavailable.

#### Scenario: A new Responses provider is added

- **WHEN** another third-party Responses endpoint is admitted
- **THEN** it is represented as a provider profile or adapter
- **AND** no product, package, runtime, service, or environment namespace changes.

#### Scenario: Publication runs on another workstation

- **WHEN** an operator supplies provider identity and a public key available in
  an existing standard OpenSSH agent
- **THEN** the direct projector or tagger can sign without a maintainer-specific
  path, password prompt, Keychain bridge, private PTY, or temporary agent.

### Requirement: Provider identities are independent

GitLab SHALL retain accepted commits in its verified identity domain. GitHub
SHALL use its verified identity domain for an equivalent projection.

#### Scenario: Forge emails differ

- **WHEN** the two Forges require different verified emails
- **THEN** their commit IDs differ
- **AND** their corresponding trees are equal.

### Requirement: Projection continuity is append-only

A provider projection SHALL preserve messages, dates, ordered trees, and parent
topology after its admitted base and SHALL only fast-forward the target.

#### Scenario: GitHub already has an admitted base

- **WHEN** accepted source advances after the mapped GitHub tip
- **THEN** only missing descendants are projected
- **AND** the old GitHub tip remains an ancestor of the new tip.

### Requirement: Projection requires one lineage match

The projector SHALL require exactly one identity-neutral source match for an
existing provider tip before creating commits or updating refs.

#### Scenario: A target match is absent or ambiguous

- **WHEN** the provider tip has zero or multiple source matches
- **THEN** projection fails before any ref update
- **AND** it offers no force or rewrite escape.

### Requirement: Projection failures retain bounded diagnostics

The publication runner SHALL return a failed child status without adding a
Python exception traceback.

#### Scenario: A projection child rejects its invocation

- **WHEN** the child exits nonzero with its own diagnostic
- **THEN** the runner returns that status
- **AND** it emits no `Traceback` or `CalledProcessError` text.

### Requirement: Unpublished canonical descendants may converge

Accepted descendants not present on either Forge SHALL be replayed onto the
exact GitLab tip only after that tip has one identity-neutral accepted match.

#### Scenario: Accepted and GitLab histories are disconnected

- **WHEN** the histories match uniquely before unpublished accepted commits
- **THEN** only those descendants are replayed and re-signed
- **AND** duplicate-history merges and force updates remain forbidden.

### Requirement: Active GitLab signing key advances explicitly

New GitLab commits and tags SHALL use the selected registered fingerprint while
predecessor trust anchors remain available for immutable history.

#### Scenario: The active key changes

- **WHEN** a registered successor key is selected
- **THEN** runner, projection, tag command, agent, and trust input agree
- **AND** older reachable commits remain verifiable.

### Requirement: Forge history matching is linear

The GitHub projector SHALL compute each canonical and projected commit's
identity-neutral fingerprint at most once per invocation and SHALL join those
indexes without weakening publication admission.

#### Scenario: A long admitted projection gains one descendant

- **WHEN** one canonical commit follows an existing GitHub projection
- **THEN** matching work grows with the combined canonical and projected history
- **AND** it does not recompute fingerprints for every source-target pair
- **AND** the target still advances only by an ordinary fast-forward push.

### Requirement: Forge fingerprint oracle canonicalizes exact UTC spelling

The independent Git-command oracle SHALL treat strict-ISO `Z` and `+00:00`
date lines as the same exact UTC instant while preserving every other
identity-neutral fingerprint byte.

#### Scenario: Hosted Git renders zero offset explicitly

- **WHEN** a supported hosted Git version emits an author or committer date
  ending in `+00:00`
- **THEN** the oracle canonicalizes only that complete zero-offset date line to
  `Z`
- **AND** tree, message, parent, nonzero offset, and ordering bytes remain
  unchanged.

### Requirement: Quality execution is repository-owned

Local and hosted verification SHALL resolve lint, type, and test tools from the
committed `uv.lock` environment rather than ambient global packages.

#### Scenario: Clean hosted checkout

- **WHEN** either Forge verifies the release from a clean checkout
- **THEN** it installs the pinned `uv` bootstrap
- **AND** the repository quality command resolves all remaining tools from the
  committed lock.

### Requirement: Private release assets use authenticated reads

GitLab Release asset verification SHALL fetch private project assets through an
authenticated provider API and hash the returned bytes without text
transformation.

#### Scenario: Private GitLab project asset

- **WHEN** anonymous direct download is unavailable but `glab` is authenticated
- **THEN** the verifier reads the asset through `glab api`
- **AND** compares its byte digest with the canonical release artifact.

### Requirement: Native platform parsers retain host-independent contracts

A platform-native process parser SHALL have deterministic synthetic contracts
for its wire representation and platform-derived defaults on every supported
test host. Those contracts SHALL cover valid decoding and malformed native
payload rejection without loading or calling a foreign operating-system
symbol. A real operating-system integration MAY remain restricted to the
platform that implements the native system call.

#### Scenario: Linux verifies Darwin argv decoding

- **WHEN** a Linux quality job executes the supported product suite
- **THEN** synthetic valid and incomplete `kern.procargs2` payloads exercise
  successful decoding and fail-closed rejection without loading or calling
  Linux `libc.sysctl`
- **AND** the real child-process integration remains Darwin-only
- **AND** branch coverage stays strictly above the repository floor.

#### Scenario: Every host verifies Darwin default paths

- **WHEN** a supported test host evaluates platform-derived state and log roots
- **THEN** the Darwin defaults are verified through injected platform identity
- **AND** the test does not depend on the host that runs the suite.

### Requirement: One locked verification projection

Local verification, GitLab CI, and GitHub Actions SHALL invoke the same small
session graph backed by the committed dependency lock. Provider files MUST NOT
duplicate tool versions, interpreter loops, coverage policy, or quality command
sequences.

#### Scenario: Verification metadata drifts

- **WHEN** project metadata, the dependency lock, session graph, or a Forge
  projection disagree
- **THEN** a fast contract gate fails before behavior, coverage, packaging, or
  publication work begins.

### Requirement: Strict coverage and pristine success output

The complete supported behavior suite SHALL maintain statement coverage and
branch coverage each strictly greater than 95 percent. Passing tests, quality
gates, builds, and expected operational-failure checks MUST emit no unexpected
warning, traceback, error banner, skipped required test, or false completion
message.

#### Scenario: A green job is reported

- **WHEN** a local or hosted full gate exits successfully
- **THEN** both coverage measures exceed 95 percent and every required check ran
- **AND** the success log contains one concise receipt rather than traceback,
  warning, or a full coverage table.

### Requirement: Native executable acceptance

Each supported operating-system release SHALL be built and smoke-tested on
that operating system. Cross-compilation or another platform's result MUST NOT
be treated as native runtime evidence.

#### Scenario: A platform asset is published

- **WHEN** a release archive for a supported OS and architecture is admitted
- **THEN** its executable passed black-box help, version, status, manifest, and
  service-start checks in a pristine native environment
- **AND** Python was absent from the product execution path.
